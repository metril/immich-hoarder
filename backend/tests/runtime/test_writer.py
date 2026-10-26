import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.db.engine import make_engine
from app.db.models import (
    AssetSeen,
    Base,
    ImmichTarget,
    Job,
    JobEvent,
    JobItem,
    JobStatus,
    Source,
    User,
)
from app.runtime import writer as writer_mod
from app.runtime.bus import EventBus
from app.runtime.writer import IpcBridge, JobWriter, make_ipc_queue

ASSET = str(uuid.uuid4())


@pytest.fixture
async def env(
    tmp_path: Path,
) -> AsyncIterator[tuple[AsyncEngine, async_sessionmaker[AsyncSession]]]:
    eng = make_engine(f"sqlite+aiosqlite:///{tmp_path / 'w.db'}")
    async with eng.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    sf = async_sessionmaker(eng, expire_on_commit=False)
    async with sf() as s:
        u = User(sub="u")
        s.add(u)
        await s.flush()
        t = ImmichTarget(owner_id=u.id, name="t", url="http://i", api_key_enc=b"x")
        s.add(t)
        await s.flush()
        src = Source(owner_id=u.id, name="s", url="http://s", extractor="x", target_id=t.id)
        s.add(src)
        await s.flush()
        s.add(Job(source_id=src.id, status=JobStatus.running))
        await s.commit()
    yield eng, sf
    await eng.dispose()


async def _count(sf: async_sessionmaker[AsyncSession], model: Any) -> int:
    async with sf() as s:
        return (await s.execute(select(func.count()).select_from(model))).scalar_one()


async def test_writer_batches_into_one_transaction(env: Any) -> None:
    eng, sf = env
    commits = 0

    def on_commit(_c: Any) -> None:
        nonlocal commits
        commits += 1

    event.listen(eng.sync_engine, "commit", on_commit)
    w = JobWriter(sf, EventBus())
    w.start()
    for i in range(20):
        w.submit(("event", 1, {"type": "log", "level": "warning", "msg": str(i)}))
    await w.stop()
    assert commits == 1
    assert await _count(sf, JobEvent) == 20


async def test_item_events_become_job_items(env: Any) -> None:
    _, sf = env
    w = JobWriter(sf, EventBus())
    w.start()
    w.submit(("event", 1, {"type": "item.uploaded", "url": "http://x/1", "immich_asset_id": ASSET}))
    w.submit(("event", 1, {"type": "item.linked", "url": "http://x/2", "duplicate": True}))
    w.submit(("event", 1, {"type": "item.failed", "url": "u" * 3000, "reason": "r" * 2000}))
    await w.stop()
    async with sf() as s:
        rows = (await s.execute(select(JobItem).order_by(JobItem.id))).scalars().all()
    assert [r.outcome for r in rows] == ["uploaded", "linked", "failed"]
    assert rows[0].immich_asset_id == ASSET
    assert len(rows[2].url) == 2048 and rows[2].reason is not None and len(rows[2].reason) == 1000
    assert await _count(sf, JobEvent) == 0


async def test_progress_updates_counters_not_events(env: Any) -> None:
    _, sf = env
    bus = EventBus()
    w = JobWriter(sf, bus)
    w.start()
    with bus.subscribe(1) as sub:
        w.submit(("event", 1, {"type": "progress", "counters": {"a": 1}}))
        w.submit(("event", 1, {"type": "progress", "counters": {"a": 5}}))
        w.submit(("event", 1, {"type": "phase", "name": "done"}))
        await w.stop()
        got = [await asyncio.wait_for(sub.__anext__(), 1) for _ in range(3)]
    assert [e["type"] for e in got] == ["progress", "progress", "phase"]
    async with sf() as s:
        job = await s.get(Job, 1)
        assert job is not None and job.counters == {"a": 5}
    assert await _count(sf, JobEvent) == 1


async def test_record_upserts_assets_seen_idempotent(env: Any) -> None:
    _, sf = env
    w = JobWriter(sf, EventBus())
    w.start()
    p = {
        "target_id": 1,
        "source_id": 1,
        "key": b"k" * 16,
        "sha1": b"s" * 20,
        "phash": 0xFFFF_0000_1234_5678,
        "immich_asset_id": ASSET,
    }
    w.submit(("record", p))
    w.submit(("record", p))
    await w.stop()
    async with sf() as s:
        rows = (await s.execute(select(AssetSeen))).scalars().all()
    assert len(rows) == 1
    assert rows[0].immich_asset_id == uuid.UUID(ASSET).bytes
    assert rows[0].phash is not None and rows[0].phash < 0


async def test_status_updates_job_and_publishes(env: Any) -> None:
    _, sf = env
    bus = EventBus()
    w = JobWriter(sf, bus)
    w.start()
    with bus.subscribe(None) as dash:
        w.submit(("status", 1, "failed", {"error": "boom", "counters": {"x": 1}}))
        await w.stop()
        ev = await asyncio.wait_for(dash.__anext__(), 1)
    assert ev == {"type": "status", "job_id": 1, "status": "failed"}
    async with sf() as s:
        job = await s.get(Job, 1)
        assert job is not None
        assert job.status == JobStatus.failed and job.error == "boom" and job.counters == {"x": 1}


async def test_stop_flushes_pending(env: Any) -> None:
    _, sf = env
    w = JobWriter(sf, EventBus())
    w.start()
    for _ in range(5):
        w.submit(("event", 1, {"type": "phase", "name": "x"}))
    await w.stop()
    assert await _count(sf, JobEvent) == 5


async def test_writer_survives_db_error(
    env: Any, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, sf = env
    monkeypatch.setattr(writer_mod, "BATCH_MAX", 1)
    w = JobWriter(sf, EventBus())
    w.submit(("event", 999, {"type": "log", "level": "info", "msg": "bad fk"}))
    w.submit(("event", 1, {"type": "log", "level": "info", "msg": "ok"}))
    w.start()
    with caplog.at_level(logging.ERROR):
        await w.stop()
    assert await _count(sf, JobEvent) == 1
    assert "writer" in caplog.text


async def test_batch_max_splits_transactions(env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    eng, sf = env
    commits = 0

    def on_commit(_c: Any) -> None:
        nonlocal commits
        commits += 1

    event.listen(eng.sync_engine, "commit", on_commit)
    monkeypatch.setattr(writer_mod, "BATCH_MAX", 3)
    w = JobWriter(sf, EventBus())
    for i in range(7):
        w.submit(("event", 1, {"type": "phase", "name": str(i)}))
    w.start()
    await w.stop()
    assert commits == 3
    assert await _count(sf, JobEvent) == 7


async def test_poisoned_messages_dropped_individually(env: Any) -> None:
    _, sf = env
    bus = EventBus()
    w = JobWriter(sf, bus)
    rec = {
        "target_id": 1,
        "source_id": 1,
        "key": b"p" * 16,
        "sha1": None,
        "phash": None,
        "immich_asset_id": None,
    }
    with bus.subscribe(None) as dash:
        w.submit(("event", 1, {"msg": "no type"}))
        w.submit(("status", 1, "bogus", {}))
        w.submit(("event", 999, {"type": "log", "msg": "fk violation"}))
        w.submit(("record", rec))
        w.submit(("status", 1, "succeeded", {}))
        w.start()
        await w.stop()
        got = await _drain(dash)
    assert [(e["type"], e.get("status")) for e in got] == [("status", "succeeded")]
    async with sf() as s:
        job = await s.get(Job, 1)
        assert job is not None and job.status == JobStatus.succeeded
    assert await _count(sf, AssetSeen) == 1
    assert await _count(sf, JobEvent) == 0


async def _drain(sub: Any) -> list[dict[str, Any]]:
    out = []
    while not sub.empty():
        out.append(await sub.__anext__())
    return out


async def test_log_level_defaults_to_info(env: Any) -> None:
    _, sf = env
    w = JobWriter(sf, EventBus())
    w.start()
    w.submit(("event", 1, {"type": "log", "msg": "x"}))
    await w.stop()
    async with sf() as s:
        ev = (await s.execute(select(JobEvent))).scalar_one()
    assert ev.level == "info"


async def test_record_persisted_with_final_status(env: Any) -> None:
    _, sf = env
    w = JobWriter(sf, EventBus())
    w.start()
    w.submit(
        (
            "record",
            {
                "target_id": 1,
                "source_id": 1,
                "key": b"r" * 16,
                "sha1": None,
                "phash": None,
                "immich_asset_id": None,
            },
        )
    )
    w.submit(("status", 1, "succeeded", {}))
    await w.stop()
    assert await _count(sf, AssetSeen) == 1
    async with sf() as s:
        job = await s.get(Job, 1)
        assert job is not None and job.status == JobStatus.succeeded


async def test_publish_error_does_not_kill_writer(
    env: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, sf = env
    bus = EventBus()
    real = bus.publish
    calls = 0

    def flaky(job_id: int | None, ev: dict[str, Any]) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("boom")
        real(job_id, ev)

    monkeypatch.setattr(bus, "publish", flaky)
    monkeypatch.setattr(writer_mod, "BATCH_MAX", 1)
    w = JobWriter(sf, bus)
    with bus.subscribe(1) as sub:
        w.submit(("event", 1, {"type": "phase", "name": "a"}))
        w.submit(("event", 1, {"type": "phase", "name": "b"}))
        w.start()
        await w.stop()
        got = await _drain(sub)
    assert [e["name"] for e in got] == ["b"]
    assert await _count(sf, JobEvent) == 2


async def test_start_idempotent_and_submit_after_stop_dropped(
    env: Any, caplog: pytest.LogCaptureFixture
) -> None:
    _, sf = env
    w = JobWriter(sf, EventBus())
    w.start()
    first = w._task
    w.start()
    assert w._task is first
    await w.stop()
    with caplog.at_level(logging.WARNING):
        w.submit(("event", 1, {"type": "phase", "name": "late"}))
    assert "after stop" in caplog.text
    assert w._queue.empty()


async def test_stop_timeout_cancels(env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    _, sf = env
    w = JobWriter(sf, EventBus())

    async def slow(_batch: Any) -> None:
        await asyncio.sleep(30)

    monkeypatch.setattr(w, "_flush", slow)
    w.start()
    w.submit(("event", 1, {"type": "phase", "name": "x"}))
    await asyncio.sleep(0)
    await w.stop(timeout=0.2)
    assert w._task is None


def test_make_ipc_queue_bounded() -> None:
    seen: list[int] = []

    class Ctx:
        def Queue(self, maxsize: int) -> str:  # noqa: N802
            seen.append(maxsize)
            return "q"

    assert make_ipc_queue(Ctx()) == "q"
    assert seen == [10000]


async def test_ipc_bridge_survives_get_error(caplog: pytest.LogCaptureFixture) -> None:
    class Q:
        n = 0

        def get(self) -> Any:
            self.n += 1
            if self.n == 1:
                raise OSError("corrupt")
            return None

        def put(self, _m: Any, timeout: float | None = None) -> None: ...

    b = IpcBridge(Q(), None, asyncio.get_running_loop())  # type: ignore[arg-type]
    with caplog.at_level(logging.ERROR):
        b.start()
        await asyncio.to_thread(b._thread.join, 2)
    assert not b._thread.is_alive()
    assert "ipc bridge" in caplog.text


async def test_ipc_bridge_forwards_and_stops() -> None:
    import queue

    from app.runtime.writer import IpcBridge

    q: queue.Queue[Any] = queue.Queue()
    got: list[Any] = []

    class W:
        def submit(self, m: Any) -> None:
            got.append(m)

    loop = asyncio.get_running_loop()
    b = IpcBridge(q, W(), loop)  # type: ignore[arg-type]
    b.start()
    q.put(("status", 1, "running", {}))
    await asyncio.sleep(0.2)
    await asyncio.to_thread(b.stop)
    assert got == [("status", 1, "running", {})]


async def test_ipc_bridge_stop_drains_everything() -> None:
    import queue

    q: queue.Queue[Any] = queue.Queue()
    got: list[Any] = []

    class W:
        def submit(self, m: Any) -> None:
            got.append(m)

    loop = asyncio.get_running_loop()
    b = IpcBridge(q, W(), loop)  # type: ignore[arg-type]
    for i in range(50):
        q.put(("status", i, "running", {}))
    b.start()
    await asyncio.to_thread(b.stop)
    await asyncio.sleep(0.1)  # let call_soon_threadsafe callbacks run
    assert len(got) == 50


async def test_ipc_bridge_stop_logs_full_queue(caplog: pytest.LogCaptureFixture) -> None:
    import queue

    class Q:
        def get(self) -> Any:
            return None

        def put(self, _m: Any, timeout: float | None = None) -> None:
            raise queue.Full

    b = IpcBridge(Q(), None, asyncio.get_running_loop())  # type: ignore[arg-type]
    b.start()
    with caplog.at_level(logging.ERROR):
        await asyncio.to_thread(b.stop)
    assert "ipc bridge: stop sentinel not queued" in caplog.text


async def test_writer_task_restarts_after_crash(
    env: Any, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _, sf = env
    monkeypatch.setattr(writer_mod, "RESTART_MIN_INTERVAL", 0.05)
    w = JobWriter(sf, EventBus())
    boom = [True]

    def hook() -> None:
        if boom:
            boom.pop()
            raise RuntimeError("crash")

    w._hook = hook
    with caplog.at_level(logging.ERROR):
        w.start()
        await asyncio.sleep(0.2)
        w.submit(("event", 1, {"type": "phase", "name": "after"}))
        await w.stop()
    assert await _count(sf, JobEvent) == 1
    assert "restarting" in caplog.text


async def test_restart_after_stop_ignores_stale_sentinel(env: Any) -> None:
    _, sf = env
    w = JobWriter(sf, EventBus())
    w.start()
    await w.stop()
    w._queue.put_nowait(None)  # stale sentinel
    w.start()
    w.submit(("event", 1, {"type": "phase", "name": "again"}))
    await w.stop()
    assert await _count(sf, JobEvent) == 1


async def test_done_listener_runs_after_commit(env: Any) -> None:
    _, sf = env
    w = JobWriter(sf, EventBus())
    seen: list[tuple[int, dict[str, Any], int]] = []

    async def cb(job_id: int, result: dict[str, Any]) -> None:
        seen.append((job_id, result, await _count(sf, JobEvent)))

    w.add_done_listener(cb)
    w.start()
    w.submit(("event", 1, {"type": "phase", "name": "x"}))
    w.submit(("done", 1, {"status": "succeeded", "error": None, "counters": {}}))
    w.submit(("done", 1, {"status": "bogus"}))  # malformed: dropped
    await w.stop()
    assert seen == [(1, {"status": "succeeded", "error": None, "counters": {}}, 1)]


async def test_stop_cancels_pending_respawn_timer(
    env: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, sf = env
    monkeypatch.setattr(writer_mod, "RESTART_MIN_INTERVAL", 30.0)
    w = JobWriter(sf, EventBus())

    def hook() -> None:
        raise RuntimeError("crash")

    w._hook = hook
    w.start()
    await asyncio.sleep(0.2)
    assert w._respawn_timer is not None
    timer = w._respawn_timer
    await w.stop()
    assert w._respawn_timer is None
    assert timer.cancelled()


async def test_status_never_leaves_terminal_state(env: Any) -> None:
    _, sf = env
    w = JobWriter(sf, EventBus())
    w.start()
    w.submit(("status", 1, "succeeded", {}))
    await asyncio.sleep(0.4)
    w.submit(("status", 1, "running", {}))
    w.submit(("status", 1, "cancelled", {}))
    await w.stop()
    async with sf() as s:
        job = await s.get(Job, 1)
    assert job is not None and job.status == JobStatus.succeeded
