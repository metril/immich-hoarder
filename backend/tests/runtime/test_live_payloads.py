import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.v1.streams import dashboard_stream, job_stream
from app.db.engine import make_engine
from app.db.models import (
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
from app.schemas.jobs import JobOut

SF = async_sessionmaker[AsyncSession]


@pytest.fixture
async def sf(tmp_path: Path) -> AsyncIterator[SF]:
    eng = make_engine(f"sqlite+aiosqlite:///{tmp_path / 'w.db'}")
    async with eng.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    f = async_sessionmaker(eng, expire_on_commit=False)
    async with f() as s:
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
    yield f
    await eng.dispose()


async def _run(sf: SF, bus: EventBus, *msgs: Any) -> None:
    w = JobWriter(sf, bus)
    w.start()
    for m in msgs:
        w.submit(m)
    await w.stop()


async def _never() -> bool:
    return False


async def test_live_log_event_has_id_ts_normalized_level(sf: SF) -> None:
    bus = EventBus()
    with bus.subscribe(1) as sub:
        await _run(sf, bus, ("event", 1, {"type": "log", "level": "warning", "msg": "x"}))
        ev = await asyncio.wait_for(sub.__anext__(), 2)
    async with sf() as s:
        row = (await s.scalars(select(JobEvent))).one()
    assert ev["level"] == "warn" and ev["id"] == row.id and ev["job_id"] == 1
    assert ev["ts"].endswith("+00:00") and ev["ts"].startswith(row.ts.isoformat()[:19])
    assert ev["msg"] == "x" and ev["type"] == "log"


async def test_live_item_event_has_id(sf: SF) -> None:
    bus = EventBus()
    with bus.subscribe(1) as sub:
        await _run(sf, bus, ("event", 1, {"type": "item.linked", "url": "http://x/1"}))
        ev = await asyncio.wait_for(sub.__anext__(), 2)
    async with sf() as s:
        row = (await s.scalars(select(JobItem))).one()
    assert ev["id"] == row.id and ev["job_id"] == 1 and ev["type"] == "item.linked"


async def test_replay_matches_live_shape(sf: SF) -> None:
    bus = EventBus()
    live: list[dict[str, Any]] = []
    with bus.subscribe(1) as sub:
        await _run(
            sf,
            bus,
            ("event", 1, {"type": "log", "level": "critical", "msg": "m"}),
            ("event", 1, {"type": "item.failed", "url": "u", "reason": "r"}),
        )
        while not sub.empty():
            live.append(await sub.__anext__())
    async with sf() as s:
        job = await s.get(Job, 1)
    assert job
    gen = job_stream(bus, lambda: sf(), job, _never)  # type: ignore[arg-type,return-value]
    got = []
    for _ in range(4):
        got.append(json.loads((await gen.__anext__())["data"]))
    await gen.aclose()
    log_live = next(e for e in live if e["type"] == "log")
    item_live = next(e for e in live if e["type"] == "item.failed")
    assert got[0] == log_live and log_live["level"] == "error"
    assert got[1] == {**item_live, "immich_asset_id": None}


async def test_phase_persisted_and_in_jobout(sf: SF) -> None:
    await _run(
        sf,
        EventBus(),
        ("event", 1, {"type": "phase", "name": "extracting"}),
        ("event", 1, {"type": "phase", "name": "draining"}),
    )
    async with sf() as s:
        job = await s.get(Job, 1)
    assert job and job.phase == "draining"
    assert JobOut.of(job, "s").phase == "draining"


async def test_dashboard_forwards_phase() -> None:
    bus = EventBus()

    async def visible() -> set[int] | None:
        return {10}

    async def src(job_id: int) -> int | None:
        return {1: 10, 2: 20}[job_id]

    gen = dashboard_stream(bus, visible, src, _never)
    task = asyncio.ensure_future(gen.__anext__())
    await asyncio.sleep(0.05)
    bus.publish(2, {"type": "phase", "job_id": 2, "name": "x"})
    bus.publish(1, {"type": "phase", "job_id": 1, "name": "extracting"})
    got = await asyncio.wait_for(task, 3)
    assert got["event"] == "phase" and json.loads(got["data"])["job_id"] == 1
    await gen.aclose()
