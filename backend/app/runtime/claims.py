"""Cross-job coordination: file and album claims, upload permits and shared rate slots.

``ClaimTable`` and ``RateTable`` are plain, single-threaded state machines. The parent runs one
``Coordinator`` on the event loop, reached over one duplex Pipe per worker; ``RemoteClaims`` is
the worker side. ``LocalClaims`` is the in-process default (CLI, tests) with the same semantics.

Lock order is file claim -> upload permit -> album claim, and the holder of a later resource
never waits for an earlier one, so claims cannot deadlock.
"""

import contextlib
import itertools
import logging
import threading
import time
from collections.abc import Callable, Hashable, Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Any, Protocol

log = logging.getLogger(__name__)

FILE, ALBUM, PERMIT = "file", "album", "permit"
CLAIM_TIMEOUT_S = 120.0
DEFAULT_PERMITS = 8
_MASK64 = (1 << 64) - 1
_POLL_S = 0.2
_FAIL_OPEN = 0  # claim id handed out when coordination is unavailable; releasing it is a no-op


class ClaimCancelled(Exception):
    """The job was cancelled while waiting for a claim."""


def _ham(a: int, b: int) -> int:
    return ((a ^ b) & _MASK64).bit_count()


@dataclass(eq=False)
class _Entry:
    cid: int
    owner: int
    rid: int
    kind: str
    key: Hashable
    params: tuple[Any, ...]
    grant: Callable[[int], None]
    active: bool = False


@dataclass
class _Gate:
    active: list[_Entry] = field(default_factory=list)
    waiting: list[_Entry] = field(default_factory=list)


class ClaimTable:
    """Grant/queue/release bookkeeping. Not thread-safe; callers serialise access."""

    def __init__(self, permit_limit: int = DEFAULT_PERMITS) -> None:
        self.permit_limit = permit_limit
        self._ids = itertools.count(1)
        self._gates: dict[tuple[str, Hashable], _Gate] = {}
        self._by_cid: dict[int, _Entry] = {}
        self._by_req: dict[tuple[int, int], _Entry] = {}

    def _blocked(self, e: _Entry, active: list[_Entry]) -> bool:
        if e.kind == ALBUM:
            return bool(active)
        if e.kind == PERMIT:
            return len(active) >= self.permit_limit
        sha1, phash, distance = e.params
        for a in active:
            if a.params[0] == sha1:
                return True
            if distance is not None and phash is not None and a.params[1] is not None:
                if _ham(phash, a.params[1]) <= distance:
                    return True
        return False

    def _activate(self, e: _Entry, gate: _Gate) -> None:
        e.active = True
        gate.active.append(e)
        try:
            e.grant(e.cid)
        except Exception:
            log.exception("claim grant callback failed")

    def acquire(
        self,
        kind: str,
        owner: int,
        rid: int,
        key: Hashable,
        params: tuple[Any, ...],
        grant: Callable[[int], None],
    ) -> int:
        """Queue a claim; ``grant(claim_id)`` is called when it is granted, possibly at once."""
        e = _Entry(next(self._ids), owner, rid, kind, key, params, grant)
        self._by_cid[e.cid] = e
        self._by_req[(owner, rid)] = e
        gate = self._gates.setdefault((kind, key), _Gate())
        if self._blocked(e, gate.active):
            gate.waiting.append(e)
        else:
            self._activate(e, gate)
        return e.cid

    def release(self, cid: int) -> None:
        """Free a claim (idempotent) and wake whatever it was blocking."""
        e = self._by_cid.pop(cid, None)
        if e is None:
            return
        self._by_req.pop((e.owner, e.rid), None)
        gate = self._gates.get((e.kind, e.key))
        if gate is None:
            return
        (gate.active if e.active else gate.waiting).remove(e)
        self._drain(e.kind, e.key, gate)

    def _drain(self, kind: str, key: Hashable, gate: _Gate) -> None:
        for w in list(gate.waiting):
            if not self._blocked(w, gate.active):
                gate.waiting.remove(w)
                self._activate(w, gate)
        if not gate.active and not gate.waiting:
            self._gates.pop((kind, key), None)

    def abandon(self, owner: int, rid: int) -> None:
        """The requester gave up: drop a waiting request, or free it if already granted."""
        e = self._by_req.get((owner, rid))
        if e is not None:
            self.release(e.cid)

    def expire(self, owner: int, rid: int) -> bool:
        """Grant a still-waiting request fail-open (timeout); True when it was waiting."""
        e = self._by_req.get((owner, rid))
        if e is None or e.active:
            return False
        gate = self._gates[(e.kind, e.key)]
        gate.waiting.remove(e)
        log.warning("claim wait timed out (job %s, %s); granting anyway", owner, e.kind)
        self._activate(e, gate)
        return True

    def sweep(self, owner: int) -> None:
        """Free everything an owner holds or waits for."""
        for e in [e for e in self._by_cid.values() if e.owner == owner]:
            self.release(e.cid)

    def drop_waiting(self, owner: int) -> None:
        for e in [e for e in self._by_cid.values() if e.owner == owner and not e.active]:
            self.release(e.cid)

    def held(self, owner: int | None = None) -> int:
        return sum(1 for e in self._by_cid.values() if e.active and owner in (None, e.owner))

    def waiting(self) -> int:
        return sum(1 for e in self._by_cid.values() if not e.active)


class RateTable:
    """Per-key shared request spacing: each caller gets the next free slot."""

    def __init__(self) -> None:
        self._next: dict[str, float] = {}

    def slot(self, key: str, interval: float, now: float | None = None) -> float:
        now = time.monotonic() if now is None else now
        t = max(now, self._next.get(key, 0.0))
        self._next[key] = t + max(0.0, interval)
        return t - now

    def push(self, key: str, delay: float, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        self._next[key] = max(self._next.get(key, 0.0), now + delay)


class Claims(Protocol):
    """Worker-thread facing API used by the pipeline, albums and the gallery-dl runner."""

    def claim_file(
        self,
        target_id: int,
        sha1: bytes,
        phash: int | None,
        distance: int | None,
        cancel: threading.Event,
    ) -> int: ...

    def release_file(self, claim_id: int) -> None: ...

    def upload_permit(
        self, target_id: int, cancel: threading.Event
    ) -> AbstractContextManager[None]: ...

    def album(
        self, target_id: int, name: str, cancel: threading.Event
    ) -> AbstractContextManager[None]: ...

    def rate_slot(self, key: str, interval: float) -> float: ...

    def rate_push(self, key: str, delay: float) -> None: ...


_NEVER = threading.Event()


class LocalClaims:
    """In-process claims with the same semantics as the coordinator (one process, any threads)."""

    def __init__(self, permit_limit: int | None = None, timeout_s: float = CLAIM_TIMEOUT_S) -> None:
        self._lock = threading.Lock()
        self._table = ClaimTable(permit_limit or 1 << 30)
        self._rates = RateTable()
        self._rid = itertools.count(1)
        self._timeout = timeout_s

    def _acquire(
        self, kind: str, key: Hashable, params: tuple[Any, ...], cancel: threading.Event
    ) -> int:
        rid = next(self._rid)
        ev = threading.Event()
        box: list[int] = []

        def grant(cid: int) -> None:
            box.append(cid)
            ev.set()

        with self._lock:
            self._table.acquire(kind, 0, rid, key, params, grant)
        deadline = time.monotonic() + self._timeout
        while not ev.wait(_POLL_S):
            if cancel.is_set():
                with self._lock:
                    self._table.abandon(0, rid)
                raise ClaimCancelled
            if time.monotonic() >= deadline:
                with self._lock:
                    self._table.expire(0, rid)
        return box[0]

    def _free(self, cid: int) -> None:
        with self._lock:
            self._table.release(cid)

    def claim_file(
        self,
        target_id: int,
        sha1: bytes,
        phash: int | None,
        distance: int | None,
        cancel: threading.Event,
    ) -> int:
        return self._acquire(FILE, target_id, (sha1, phash, distance), cancel)

    def release_file(self, claim_id: int) -> None:
        self._free(claim_id)

    @contextlib.contextmanager
    def upload_permit(self, target_id: int, cancel: threading.Event) -> Iterator[None]:
        cid = self._acquire(PERMIT, target_id, (), cancel)
        try:
            yield
        finally:
            self._free(cid)

    @contextlib.contextmanager
    def album(self, target_id: int, name: str, cancel: threading.Event) -> Iterator[None]:
        cid = self._acquire(ALBUM, (target_id, name), (), cancel)
        try:
            yield
        finally:
            self._free(cid)

    def rate_slot(self, key: str, interval: float) -> float:
        with self._lock:
            return self._rates.slot(key, interval)

    def rate_push(self, key: str, delay: float) -> None:
        with self._lock:
            self._rates.push(key, delay)


# -- parent side ---------------------------------------------------------------------------


class Coordinator:
    """Event-loop owner of the claim tables; one duplex Pipe per running job."""

    def __init__(
        self,
        loop: Any,
        permit_limit: int = DEFAULT_PERMITS,
        timeout_s: float = CLAIM_TIMEOUT_S,
    ) -> None:
        self._loop = loop
        self.table = ClaimTable(permit_limit)
        self.rates = RateTable()
        self.timeout_s = timeout_s
        self._conns: dict[int, Any] = {}
        self._timers: dict[tuple[int, int], Any] = {}

    def set_permit_limit(self, n: int) -> None:
        if n != self.table.permit_limit:
            self.table.permit_limit = n
            for key, gate in list(self.table._gates.items()):
                if key[0] == PERMIT:
                    self.table._drain(PERMIT, key[1], gate)

    def attach(self, job_id: int, conn: Any) -> None:
        self._conns[job_id] = conn
        self._loop.add_reader(conn.fileno(), self._readable, job_id)

    def detach(self, job_id: int) -> None:
        """Forget a job: free its claims and close its pipe (idempotent)."""
        self._close(job_id)
        self.table.sweep(job_id)
        self._cancel_timers(job_id)

    def sweep(self, job_id: int) -> None:
        self.table.sweep(job_id)
        self._cancel_timers(job_id)

    def on_message(self, msg: tuple[Any, ...]) -> None:
        """Writer post-commit observer: a worker's ``release`` frees its file claim."""
        if msg[0] == "release":
            self.table.release(msg[1])

    def _close(self, job_id: int) -> None:
        conn = self._conns.pop(job_id, None)
        if conn is None:
            return
        with contextlib.suppress(Exception):
            self._loop.remove_reader(conn.fileno())
        with contextlib.suppress(Exception):
            conn.close()

    def _cancel_timers(self, job_id: int) -> None:
        for k in [k for k in self._timers if k[0] == job_id]:
            self._timers.pop(k).cancel()

    def _eof(self, job_id: int) -> None:
        """Pipe closed: the worker is gone or finishing. Held claims wait for the sweep."""
        self._close(job_id)
        self.table.drop_waiting(job_id)
        for k in [k for k in self._timers if k[0] == job_id]:
            self._timers.pop(k).cancel()

    def _readable(self, job_id: int) -> None:
        conn = self._conns.get(job_id)
        if conn is None:
            return
        try:
            while conn.poll(0):
                self._handle(job_id, conn.recv())
        except (EOFError, OSError):
            self._eof(job_id)

    def _handle(self, job_id: int, msg: Any) -> None:
        try:
            op = msg[0]
            if op == "claim":
                _, rid, kind, key, params = msg
                self._claim(job_id, rid, kind, key, tuple(params))
            elif op == "abandon":
                self._timer_off(job_id, msg[1])
                self.table.abandon(job_id, msg[1])
            elif op == "rel":
                self.table.release(msg[1])
            elif op == "slot":
                _, rid, key, interval = msg
                self._send(job_id, ("grant", rid, self.rates.slot(str(key), float(interval))))
            elif op == "push":
                self.rates.push(str(msg[1]), float(msg[2]))
        except Exception:
            log.exception("coordinator: bad message from job %s", job_id)

    def _claim(self, job_id: int, rid: int, kind: str, key: Any, params: tuple[Any, ...]) -> None:
        if kind not in (FILE, ALBUM, PERMIT):
            raise ValueError(kind)
        hkey: Hashable = tuple(key) if isinstance(key, list) else key

        granted: list[int] = []

        def grant(cid: int) -> None:
            granted.append(cid)
            self._timer_off(job_id, rid)
            if not self._send(job_id, ("grant", rid, cid)):
                self._loop.call_soon(self.table.release, cid)

        self.table.acquire(kind, job_id, rid, hkey, params, grant)
        if not granted:
            self._timers[(job_id, rid)] = self._loop.call_later(
                self.timeout_s, self._expire, job_id, rid
            )

    def _expire(self, job_id: int, rid: int) -> None:
        self._timers.pop((job_id, rid), None)
        self.table.expire(job_id, rid)

    def _timer_off(self, job_id: int, rid: int) -> None:
        t = self._timers.pop((job_id, rid), None)
        if t is not None:
            t.cancel()

    def _send(self, job_id: int, msg: tuple[Any, ...]) -> bool:
        conn = self._conns.get(job_id)
        if conn is None:
            return False
        try:
            conn.send(msg)
        except (OSError, ValueError):
            self._loop.call_soon(self._eof, job_id)
            return False
        return True


# -- worker side ---------------------------------------------------------------------------


@dataclass(eq=False)
class _Pending:
    event: threading.Event = field(default_factory=threading.Event)
    value: Any = _FAIL_OPEN


class RemoteClaims:
    """Worker end of the Pipe: one demux thread, a send lock, blocking calls with cancel."""

    def __init__(self, conn: Any, queue: Any) -> None:
        self._conn = conn
        self._q = queue
        self._send_lock = threading.Lock()
        self._plock = threading.Lock()
        self._pending: dict[int, _Pending] = {}
        self._rid = itertools.count(1)
        self._dead = False
        threading.Thread(target=self._demux, name="claims-demux", daemon=True).start()

    def _demux(self) -> None:
        while True:
            try:
                _, rid, value = self._conn.recv()
            except (EOFError, OSError):
                break
            except Exception:
                log.exception("claims: bad reply")
                continue
            with self._plock:
                p = self._pending.get(rid)
            if p is not None:
                p.value = value
                p.event.set()
        self._dead = True  # coordinator gone: every waiter fails open
        with self._plock:
            pend = list(self._pending.values())
        for p in pend:
            p.event.set()

    def _send(self, msg: tuple[Any, ...]) -> bool:
        if self._dead:
            return False
        try:
            with self._send_lock:
                self._conn.send(msg)
        except (OSError, ValueError):
            self._dead = True
            return False
        return True

    def _call(self, build: Callable[[int], tuple[Any, ...]], cancel: threading.Event) -> Any:
        rid = next(self._rid)
        p = _Pending()
        with self._plock:
            self._pending[rid] = p
        try:
            if not self._send(build(rid)):
                return _FAIL_OPEN
            while not p.event.wait(_POLL_S):
                if cancel.is_set():
                    self._send(("abandon", rid))
                    raise ClaimCancelled
            return p.value
        finally:
            with self._plock:
                self._pending.pop(rid, None)

    def claim_file(
        self,
        target_id: int,
        sha1: bytes,
        phash: int | None,
        distance: int | None,
        cancel: threading.Event,
    ) -> int:
        return int(
            self._call(lambda r: ("claim", r, FILE, target_id, (sha1, phash, distance)), cancel)
        )

    def release_file(self, claim_id: int) -> None:
        if claim_id != _FAIL_OPEN:  # ordered after the job's earlier record on the same queue
            self._q.put(("release", claim_id))

    @contextlib.contextmanager
    def _held(self, kind: str, key: Hashable, cancel: threading.Event) -> Iterator[None]:
        cid = int(self._call(lambda r: ("claim", r, kind, key, ()), cancel))
        try:
            yield
        finally:
            if cid != _FAIL_OPEN:
                self._send(("rel", cid))

    def upload_permit(
        self, target_id: int, cancel: threading.Event
    ) -> AbstractContextManager[None]:
        return self._held(PERMIT, target_id, cancel)

    def album(
        self, target_id: int, name: str, cancel: threading.Event
    ) -> AbstractContextManager[None]:
        return self._held(ALBUM, (target_id, name), cancel)

    def rate_slot(self, key: str, interval: float) -> float:
        return float(self._call(lambda r: ("slot", r, key, interval), _NEVER) or 0.0)

    def rate_push(self, key: str, delay: float) -> None:
        self._send(("push", key, delay))
