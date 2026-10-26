import sqlite3
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.crypto import SecretBox
from app.db.engine import make_engine
from app.db.models import Base, ImmichTarget, Job, JobEvent, JobItem, JobStatus, Source, User
from app.runtime.maintenance import backup_sqlite, prune_ephemeral_sources, prune_jobs

KEY = "test-master-key-0123456789abcdef-xyz"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest.fixture
async def sf(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    eng = make_engine(f"sqlite+aiosqlite:///{tmp_path / 'm.db'}")
    async with eng.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    f = async_sessionmaker(eng, expire_on_commit=False)
    async with f() as s:
        u = User(sub="u")
        s.add(u)
        await s.flush()
        s.add(
            ImmichTarget(
                owner_id=u.id, name="t", url="http://i", api_key_enc=SecretBox(KEY).encrypt(b"k")
            )
        )
        await s.commit()
    yield f
    await eng.dispose()


async def _src(s: AsyncSession, **kw: Any) -> Source:
    src = Source(owner_id=1, name="s", url="http://s", extractor="x", target_id=1, **kw)
    s.add(src)
    await s.flush()
    return src


async def test_prune_cascades_and_keeps_recent_and_active(
    sf: async_sessionmaker[AsyncSession],
) -> None:
    old = _now() - timedelta(days=40)
    async with sf() as s:
        a, b, c, d = [await _src(s) for _ in range(4)]
        j_old = Job(source_id=a.id, status=JobStatus.succeeded, finished_at=old)
        j_fail = Job(source_id=b.id, status=JobStatus.failed, finished_at=old)
        j_new = Job(source_id=c.id, status=JobStatus.succeeded, finished_at=_now())
        j_run = Job(source_id=d.id, status=JobStatus.running, started_at=old)
        s.add_all([j_old, j_fail, j_new, j_run])
        await s.flush()
        s.add(JobEvent(job_id=j_old.id, level="info", type="t"))
        s.add(JobItem(job_id=j_old.id, url="u", outcome="ok"))
        await s.commit()
        keep = {j_new.id, j_run.id}
    async with sf() as s:
        assert await prune_jobs(s, 30) == 2
        await s.commit()
    async with sf() as s:
        assert set((await s.scalars(select(Job.id))).all()) == keep
        assert await s.scalar(select(func.count()).select_from(JobEvent)) == 0
        assert await s.scalar(select(func.count()).select_from(JobItem)) == 0


async def test_ephemeral_cleanup(sf: async_sessionmaker[AsyncSession]) -> None:
    old = _now() - timedelta(days=2)
    async with sf() as s:
        gone = await _src(s, ephemeral=True)
        with_job = await _src(s, ephemeral=True)
        fresh = await _src(s, ephemeral=True)
        normal = await _src(s)
        s.add(Job(source_id=with_job.id, status=JobStatus.queued))
        await s.flush()
        gone.created_at = old
        with_job.created_at = old
        normal.created_at = old
        keep = {with_job.id, fresh.id, normal.id}
        await s.commit()
    async with sf() as s:
        assert await prune_ephemeral_sources(s) == 1
        await s.commit()
    async with sf() as s:
        assert set((await s.scalars(select(Source.id))).all()) == keep


def test_backup_vacuum_into_and_rotation(tmp_path: Path) -> None:
    db = tmp_path / "live.db"
    con = sqlite3.connect(db)
    con.execute("create table t(x)")
    con.execute("insert into t values (42)")
    con.commit()
    con.close()
    bdir = tmp_path / "bk"
    bdir.mkdir()
    for i in range(3):
        (bdir / f"hoarder-2020010{i}-000000.db").write_bytes(b"x")
    (bdir / "other.txt").write_text("keep me")
    out = backup_sqlite(f"sqlite+aiosqlite:///{db}", bdir, keep=2)
    assert out is not None and out.parent == bdir
    assert sqlite3.connect(out).execute("select x from t").fetchone() == (42,)
    names = sorted(p.name for p in bdir.glob("hoarder-*.db"))
    assert len(names) == 2 and out.name in names
    assert (bdir / "other.txt").exists()


def test_backup_rejects_odd_dir(tmp_path: Path) -> None:
    db = tmp_path / "live.db"
    sqlite3.connect(db).close()
    bad = tmp_path / "o'brien"
    with pytest.raises(ValueError):
        backup_sqlite(f"sqlite+aiosqlite:///{db}", bad, keep=1)


def test_backup_skipped_on_postgres_url(tmp_path: Path) -> None:
    assert backup_sqlite("postgresql://u:p@h/db", tmp_path / "bk", keep=3) is None
    assert not (tmp_path / "bk").exists()
