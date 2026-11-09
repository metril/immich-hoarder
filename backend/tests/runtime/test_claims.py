import asyncio
import multiprocessing as mp
import queue
import threading
import time
from typing import Any

import pytest

from app.runtime.claims import (
    ALBUM,
    FILE,
    PERMIT,
    ClaimCancelled,
    ClaimTable,
    Coordinator,
    LocalClaims,
    RateTable,
    RemoteClaims,
)

S1, S2 = b"\x01" * 20, b"\x02" * 20


def grab(t: ClaimTable, owner: int, rid: int, kind: str, key: Any, params: tuple[Any, ...] = ()):
    got: list[int] = []
    t.acquire(kind, owner, rid, key, params, got.append)
    return got


def test_same_sha1_blocks_until_release() -> None:
    t = ClaimTable()
    a = grab(t, 1, 1, FILE, 7, (S1, 0, None))
    b = grab(t, 2, 1, FILE, 7, (S1, 0, None))
    c = grab(t, 2, 2, FILE, 7, (S2, 1 << 40, None))  # different content: free
    d = grab(t, 2, 3, FILE, 8, (S1, 0, None))  # other target: free
    assert a and c and d and not b
    t.release(a[0])
    assert b
    t.release(a[0])  # idempotent
    assert t.held() == 3


def test_phash_distance_is_claimants_and_phash_none_never_conflicts() -> None:
    t = ClaimTable()
    a = grab(t, 1, 1, FILE, 7, (S1, 0b1111, 3))
    near = grab(t, 2, 1, FILE, 7, (S2, 0b0001, 3))  # distance 3 <= 3
    far = grab(t, 2, 2, FILE, 7, (b"\x03" * 20, 0xFFFF, 3))
    nodist = grab(t, 2, 3, FILE, 7, (b"\x04" * 20, 0b1111 ^ 1, None))  # no pHash dedupe
    nophash = grab(t, 2, 4, FILE, 7, (b"\x05" * 20, None, 3))
    assert a and far and nodist and nophash and not near
    t.release(a[0])
    assert near


def test_waiters_wake_in_order_and_no_missed_wakeup() -> None:
    t = ClaimTable()
    first = grab(t, 1, 1, FILE, 7, (S1, 0, None))
    w = [grab(t, 2, i, FILE, 7, (S1, 0, None)) for i in range(3)]
    t.release(first[0])
    assert [bool(x) for x in w] == [True, False, False]
    t.release(w[0][0])
    assert [bool(x) for x in w] == [True, True, False]
    t.release(w[1][0])
    assert all(w)


def test_abandon_waiting_and_granted() -> None:
    t = ClaimTable()
    a = grab(t, 1, 1, FILE, 7, (S1, 0, None))
    b = grab(t, 2, 1, FILE, 7, (S1, 0, None))
    t.abandon(2, 1)
    t.release(a[0])
    assert not b and t.held() == 0 and t.waiting() == 0
    c = grab(t, 3, 1, FILE, 7, (S1, 0, None))
    t.abandon(3, 1)  # already granted: freed
    assert c and t.held() == 0


def test_expire_grants_fail_open() -> None:
    t = ClaimTable()
    grab(t, 1, 1, FILE, 7, (S1, 0, None))
    b = grab(t, 2, 1, FILE, 7, (S1, 0, None))
    assert t.expire(2, 1) and b
    assert not t.expire(2, 1)
    t.release(b[0])
    assert t.held() == 1


def test_sweep_frees_held_and_waiting_and_wakes_others() -> None:
    t = ClaimTable()
    held = grab(t, 1, 1, FILE, 7, (S1, 0, None))
    other_held = grab(t, 2, 1, ALBUM, ("a", 1), ())
    mine_wait = grab(t, 1, 2, ALBUM, ("a", 1), ())
    waiter = grab(t, 3, 1, FILE, 7, (S1, 0, None))
    assert held and other_held and not mine_wait and not waiter
    t.sweep(1)
    assert waiter and t.held(1) == 0 and t.waiting() == 0
    t.release(other_held[0])
    assert not mine_wait  # the dropped waiter is never granted


def test_permits_cap_per_target_and_limit_change() -> None:
    t = ClaimTable(permit_limit=2)
    p = [grab(t, 1, i, PERMIT, 7) for i in range(3)]
    other = grab(t, 1, 9, PERMIT, 8)
    assert [bool(x) for x in p] == [True, True, False] and other
    t.release(p[0][0])
    assert p[2]


def test_rate_slots_space_and_push() -> None:
    r = RateTable()
    assert r.slot("reddit", 1.0, now=10.0) == 0
    assert r.slot("reddit", 1.0, now=10.0) == pytest.approx(1.0)
    assert r.slot("reddit", 1.0, now=10.5) == pytest.approx(1.5)
    assert r.slot("other", 1.0, now=10.0) == 0
    r.push("reddit", 60, now=11.0)
    assert r.slot("reddit", 1.0, now=12.0) == pytest.approx(59.0)
    r.push("reddit", 1, now=12.0)  # never shortens
    assert r.slot("reddit", 1.0, now=12.0) == pytest.approx(60.0)


# -- LocalClaims -------------------------------------------------------------------------


def test_local_claims_serialise_same_content_and_cancel() -> None:
    c = LocalClaims()
    never = threading.Event()
    cid = c.claim_file(1, S1, None, None, never)
    cancel = threading.Event()
    err: list[BaseException] = []

    def waiter() -> None:
        try:
            c.claim_file(1, S1, None, None, cancel)
        except ClaimCancelled as e:
            err.append(e)

    th = threading.Thread(target=waiter)
    th.start()
    time.sleep(0.3)
    assert th.is_alive()
    cancel.set()
    th.join(2)
    assert err and not th.is_alive()
    c.release_file(cid)
    assert c.claim_file(1, S1, None, None, never)  # the abandoned waiter left no claim behind


def test_local_claims_timeout_fails_open() -> None:
    c = LocalClaims(timeout_s=0.3)
    ev = threading.Event()
    c.claim_file(1, S1, None, None, ev)
    t0 = time.monotonic()
    assert c.claim_file(1, S1, None, None, ev)
    assert 0.25 < time.monotonic() - t0 < 3


def test_local_permit_released_on_exception() -> None:
    c = LocalClaims(permit_limit=1)
    ev = threading.Event()
    with pytest.raises(RuntimeError), c.upload_permit(1, ev):
        raise RuntimeError
    with c.upload_permit(1, ev):
        pass


def test_local_album_is_exclusive() -> None:
    c = LocalClaims()
    ev = threading.Event()
    order: list[str] = []

    def second() -> None:
        with c.album(1, "x", ev):
            order.append("b")

    with c.album(1, "x", ev):
        th = threading.Thread(target=second)
        th.start()
        time.sleep(0.3)
        order.append("a")
    th.join(2)
    assert order == ["a", "b"]


# -- Coordinator + RemoteClaims over a real Pipe ----------------------------------------


class Rig:
    def __init__(self, loop: asyncio.AbstractEventLoop, timeout_s: float = 30) -> None:
        self.co = Coordinator(loop, permit_limit=1, timeout_s=timeout_s)
        self.q: Any = queue.Queue()
        self.ends: list[Any] = []

    def worker(self, job_id: int) -> RemoteClaims:
        parent, child = mp.Pipe(duplex=True)
        self.ends.append(child)
        self.co.attach(job_id, parent)
        return RemoteClaims(child, self.q)


async def run(fn: Any, *a: Any) -> Any:
    return await asyncio.to_thread(fn, *a)


async def until(cond: Any, timeout: float = 5) -> None:
    end = time.monotonic() + timeout
    while not cond():
        assert time.monotonic() < end
        await asyncio.sleep(0.01)


async def test_remote_cross_job_claim_released_by_commit_message() -> None:
    rig = Rig(asyncio.get_running_loop())
    w1, w2 = rig.worker(1), rig.worker(2)
    ev = threading.Event()
    cid = await run(w1.claim_file, 1, S1, 5, 3, ev)
    t2 = asyncio.create_task(run(w2.claim_file, 1, S2, 4, 3, ev))  # pHash distance 1
    await asyncio.sleep(0.3)
    assert not t2.done()
    await run(w1.release_file, cid)
    assert rig.q.get_nowait() == ("release", cid)
    assert not t2.done()  # only the commit-ordered message frees it
    rig.co.on_message(("release", cid))
    assert await asyncio.wait_for(t2, 5)


async def test_remote_cancel_abandons_and_eof_sweep() -> None:
    rig = Rig(asyncio.get_running_loop())
    w1, w2 = rig.worker(1), rig.worker(2)
    never = threading.Event()
    cancel = threading.Event()
    await run(w1.claim_file, 1, S1, None, None, never)
    t2 = asyncio.create_task(run(w2.claim_file, 1, S1, None, None, cancel))
    await until(lambda: rig.co.table.waiting() == 1)
    cancel.set()
    with pytest.raises(ClaimCancelled):
        await t2
    await until(lambda: rig.co.table.waiting() == 0)
    assert rig.co.table.held(1) == 1
    rig.co.detach(1)  # SIGKILLed job: sweep frees everything it held
    assert rig.co.table.held() == 0


async def test_remote_permit_album_and_slots() -> None:
    rig = Rig(asyncio.get_running_loop())
    w1, w2 = rig.worker(1), rig.worker(2)
    ev = threading.Event()

    def holder() -> None:
        with w1.upload_permit(1, ev):
            time.sleep(0.4)

    th = asyncio.create_task(run(holder))
    await until(lambda: rig.co.table.held() == 1)
    t0 = time.monotonic()
    await run(lambda: w2.upload_permit(1, ev).__enter__())
    assert time.monotonic() - t0 > 0.2  # limit is 1: waited for w1's permit
    await th
    assert await run(w1.rate_slot, "reddit", 1.0) == 0
    assert await run(w2.rate_slot, "reddit", 1.0) == pytest.approx(1.0, abs=0.2)
    await run(w1.rate_push, "reddit", 30.0)
    await until(lambda: rig.co.rates.slot("reddit", 0) > 20)


async def test_remote_timeout_fails_open_and_dead_pipe_does_not_block() -> None:
    rig = Rig(asyncio.get_running_loop(), timeout_s=0.3)
    w1, w2 = rig.worker(1), rig.worker(2)
    ev = threading.Event()
    await run(w1.claim_file, 1, S1, None, None, ev)
    assert await asyncio.wait_for(run(w2.claim_file, 1, S1, None, None, ev), 5)
    rig.co.detach(2)  # coordinator closes its end: worker 2 fails open instead of hanging
    await until(lambda: w2._dead)
    assert await run(w2.claim_file, 1, S2, None, None, ev) == 0
    assert await run(w2.rate_slot, "x", 1.0) == 0.0
