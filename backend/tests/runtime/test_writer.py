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
from app.runtime.bus import EventBus
from app.runtime.writer import JobWriter

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


async def test_writer_survives_db_error(env: Any, caplog: pytest.LogCaptureFixture) -> None:
    _, sf = env
    w = JobWriter(sf, EventBus())
    w.start()
    with caplog.at_level(logging.ERROR):
        w.submit(("event", 999, {"type": "log", "level": "info", "msg": "bad fk"}))
        await asyncio.sleep(0.4)
        w.submit(("event", 1, {"type": "log", "level": "info", "msg": "ok"}))
        await w.stop()
    assert await _count(sf, JobEvent) == 1
    assert "writer batch failed" in caplog.text


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
