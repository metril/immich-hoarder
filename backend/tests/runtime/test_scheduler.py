import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.crypto import SecretBox
from app.db.engine import make_engine
from app.db.models import Base, ImmichTarget, Source, User
from app.runtime.scheduler import CroniterTrigger, SourceScheduler
from app.runtime.supervisor import JobConflict

_NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)  # a Sunday
KEY = "test-master-key-0123456789abcdef-xyz"


class FakeSup:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self.exc: Exception | None = None

    async def enqueue(
        self, source_id: int, triggered_by: int | None, log_level: str | None
    ) -> None:
        self.calls.append((source_id, triggered_by, log_level))
        if self.exc:
            raise self.exc


@pytest.fixture
async def sf(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    eng = make_engine(f"sqlite+aiosqlite:///{tmp_path / 's.db'}")
    async with eng.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    f = async_sessionmaker(eng, expire_on_commit=False)
    async with f() as s:
        u = User(sub="u")
        s.add(u)
        await s.flush()
        t = ImmichTarget(
            owner_id=u.id, name="t", url="http://i", api_key_enc=SecretBox(KEY).encrypt(b"k")
        )
        s.add(t)
        await s.commit()
    yield f
    await eng.dispose()


async def add(sf: async_sessionmaker[AsyncSession], **kw: Any) -> int:
    async with sf() as s:
        u = await s.get(User, 1)
        t = await s.get(ImmichTarget, 1)
        assert u and t
        src = Source(owner_id=u.id, name="s", url="http://s", extractor="x", target_id=t.id, **kw)
        s.add(src)
        await s.commit()
        return src.id


async def test_start_registers_enabled_scheduled_sources(sf: Any) -> None:
    a = await add(sf, schedule_cron="*/5 * * * *")
    await add(sf)  # unscheduled
    sch = SourceScheduler(FakeSup(), sf)  # type: ignore[arg-type]
    await sch.start()
    try:
        assert sch.running
        assert sch.job_ids() == {f"source-{a}"}
        job = sch._sched.get_job(f"source-{a}")
        assert job.misfire_grace_time == 300
        assert job.coalesce is True
        assert job.max_instances == 1
    finally:
        sch.shutdown(wait=False)


async def test_sync_on_patch_and_delete(sf: Any) -> None:
    a = await add(sf)
    sch = SourceScheduler(FakeSup(), sf)  # type: ignore[arg-type]
    await sch.start()
    try:
        assert sch.job_ids() == set()
        async with sf() as s:
            src = await s.get(Source, a)
            assert src
            src.schedule_cron = "0 3 * * *"
            await s.commit()
        await sch.sync_source(a)
        assert sch.job_ids() == {f"source-{a}"}
        async with sf() as s:
            src = await s.get(Source, a)
            assert src
            src.schedule_cron = "0 4 * * *"
            await s.commit()
        await sch.sync_source(a)
        nxt = sch._sched.get_job(f"source-{a}").trigger.get_next_fire_time(None, _NOW)
        assert nxt == datetime(2026, 10, 26, 4, 0, tzinfo=UTC)
        async with sf() as s:
            src = await s.get(Source, a)
            assert src
            await s.delete(src)
            await s.commit()
        await sch.sync_source(a)
        assert sch.job_ids() == set()
    finally:
        sch.shutdown(wait=False)


async def test_disabled_or_ephemeral_not_scheduled(sf: Any) -> None:
    await add(sf, schedule_cron="* * * * *", enabled=False)
    await add(sf, schedule_cron="* * * * *", ephemeral=True)
    sch = SourceScheduler(FakeSup(), sf)  # type: ignore[arg-type]
    await sch.start()
    try:
        assert sch.job_ids() == set()
    finally:
        sch.shutdown(wait=False)


async def test_fire_conflict_skipped(sf: Any, caplog: pytest.LogCaptureFixture) -> None:
    sup = FakeSup()
    sch = SourceScheduler(sup, sf)  # type: ignore[arg-type]
    await sch.start()
    try:
        sup.exc = JobConflict(7)
        with caplog.at_level(logging.INFO):
            await sch._fire(7)
        assert sup.calls == [(7, None, None)]
        assert any(r.levelno == logging.INFO for r in caplog.records)
        sup.exc = RuntimeError("boom")
        with caplog.at_level(logging.INFO):
            await sch._fire(7)
        assert any(r.levelno == logging.ERROR and not r.exc_info for r in caplog.records)
    finally:
        sch.shutdown(wait=False)


def test_croniter_trigger_sunday_zero() -> None:
    nxt = CroniterTrigger("0 0 * * 0").get_next_fire_time(None, _NOW)
    assert nxt == datetime(2026, 11, 1, 0, 0, tzinfo=UTC)
    assert nxt.weekday() == 6


def test_croniter_trigger_aliases() -> None:
    assert CroniterTrigger("@daily").get_next_fire_time(None, _NOW) == datetime(
        2026, 10, 26, 0, 0, tzinfo=UTC
    )
    nxt = CroniterTrigger("0 0 * * 7").get_next_fire_time(None, _NOW)
    assert nxt is not None and nxt.weekday() == 6


async def test_two_schedulers_keep_separate_supervisors(sf: Any) -> None:
    s1, s2 = FakeSup(), FakeSup()
    a = SourceScheduler(s1, sf)  # type: ignore[arg-type]
    b = SourceScheduler(s2, sf)  # type: ignore[arg-type]
    await a._fire(1)
    await b._fire(2)
    assert s1.calls == [(1, None, None)]
    assert s2.calls == [(2, None, None)]


async def test_invalid_stored_cron_removes_job(sf: Any, caplog: pytest.LogCaptureFixture) -> None:
    a = await add(sf, schedule_cron="0 3 * * *")
    sch = SourceScheduler(FakeSup(), sf)  # type: ignore[arg-type]
    await sch.start()
    try:
        assert sch.job_ids() == {f"source-{a}"}
        async with sf() as s:
            src = await s.get(Source, a)
            assert src
            src.schedule_cron = "bad cron"
            await s.commit()
        with caplog.at_level(logging.ERROR):
            await sch.sync_source(a)
        assert sch.job_ids() == set()
        assert any("bad cron" in r.getMessage() for r in caplog.records)
    finally:
        sch.shutdown(wait=False)


async def test_maintenance_jobs_registered(
    sf: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    from pydantic import SecretStr

    from app.core.config import Settings
    from app.db.models import Setting

    async with sf() as s:
        s.add(Setting(key="runtime", value={"backup_cron": "30 2 * * *"}))
        await s.commit()
    cfg = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 's.db'}",
        master_key=SecretStr(KEY),
        session_secret=SecretStr("test-session-secret-0123456789abcdef"),
    )
    sched = SourceScheduler(FakeSup(), sf, cfg)  # type: ignore[arg-type]
    await sched.start()
    try:
        got = {j.id: str(j.trigger) for j in sched._sched.get_jobs()}
        assert {"maintenance-prune", "maintenance-backup"} <= got.keys()
        assert got["maintenance-prune"] == "croniter[0 4 * * *]"
        assert got["maintenance-backup"] == "croniter[30 2 * * *]"
    finally:
        sched.shutdown()


async def test_backup_keep_zero_registers_no_backup_job(
    sf: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    from pydantic import SecretStr

    from app.core.config import Settings
    from app.db.models import Setting

    async with sf() as s:
        s.add(Setting(key="runtime", value={"backup_keep": 0}))
        await s.commit()
    cfg = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 's.db'}",
        master_key=SecretStr(KEY),
        session_secret=SecretStr("test-session-secret-0123456789abcdef"),
    )
    sched = SourceScheduler(FakeSup(), sf, cfg)  # type: ignore[arg-type]
    await sched.start()
    try:
        ids = {j.id for j in sched._sched.get_jobs()}
        assert "maintenance-prune" in ids and "maintenance-backup" not in ids
    finally:
        sched.shutdown()


async def test_stop_waits_for_inflight_maintenance(
    sf: async_sessionmaker[AsyncSession],
) -> None:
    import asyncio

    sched = SourceScheduler(FakeSup(), sf)  # type: ignore[arg-type]
    await sched.start()
    finished = asyncio.Event()

    async def slow() -> None:
        sched._track()
        await asyncio.sleep(0.3)
        finished.set()

    task = asyncio.create_task(slow())
    await asyncio.sleep(0.05)
    await sched.stop(timeout=5)
    await asyncio.sleep(0.05)
    assert finished.is_set() and not sched.running
    await task


async def test_stop_is_bounded(sf: async_sessionmaker[AsyncSession]) -> None:
    import asyncio

    sched = SourceScheduler(FakeSup(), sf)  # type: ignore[arg-type]
    await sched.start()

    async def hang() -> None:
        sched._track()
        await asyncio.sleep(60)

    task = asyncio.create_task(hang())
    await asyncio.sleep(0.05)
    await sched.stop(timeout=0.2)
    await asyncio.sleep(0.05)
    assert not sched.running
    task.cancel()
