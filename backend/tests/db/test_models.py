from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, delete, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import engine as eng
from app.db.migrate import alembic_config, upgrade_head_async
from app.db.models import (
    AssetSeen,
    Base,
    ImmichTarget,
    Job,
    JobEvent,
    Perm,
    PrincipalType,
    Share,
    Source,
    User,
)


@pytest.fixture
async def session(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    url = f"sqlite+aiosqlite:///{tmp_path / 'm.db'}"
    await upgrade_head_async(url)
    engine = eng.make_engine(url)
    async with AsyncSession(engine) as s:
        yield s
        await s.rollback()
    await engine.dispose()


def test_migration_matches_models(tmp_path: Path) -> None:
    db = tmp_path / "a.db"
    url = f"sqlite+aiosqlite:///{db}"
    command.upgrade(alembic_config(url), "head")
    sync = create_engine(f"sqlite:///{db}")
    with sync.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True})
        assert compare_metadata(ctx, Base.metadata) == []
    sync.dispose()


def test_downgrade_base(tmp_path: Path) -> None:
    db = tmp_path / "d.db"
    cfg = alembic_config(f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    sync = create_engine(f"sqlite:///{db}")
    assert set(inspect(sync).get_table_names()) <= {"alembic_version"}
    sync.dispose()


async def _seed(s: AsyncSession) -> tuple[int, int]:
    u = User(sub="u1")
    s.add(u)
    await s.flush()
    t = ImmichTarget(owner_id=u.id, name="t", url="http://i", api_key_enc=b"x")
    s.add(t)
    await s.flush()
    src = Source(owner_id=u.id, name="s", url="http://s", extractor="x", target_id=t.id)
    s.add(src)
    await s.flush()
    return t.id, src.id


async def test_assets_seen_unique(session: AsyncSession) -> None:
    target_id, source_id = await _seed(session)
    kw = dict(target_id=target_id, source_id=source_id, url_hash=b"\x01" * 16, seen_at=1)
    session.add(AssetSeen(**kw))
    await session.flush()
    session.add(AssetSeen(**kw))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_share_unique(session: AsyncSession) -> None:
    kw = dict(
        resource_type="source",
        resource_id=1,
        principal_type=PrincipalType.user,
        principal_id="u",
        perm=Perm.use,
    )
    session.add(Share(**kw))
    await session.flush()
    session.add(Share(**kw))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_fk_policies(session: AsyncSession) -> None:
    target_id, source_id = await _seed(session)
    job = Job(source_id=source_id)
    session.add(job)
    await session.flush()
    session.add(JobEvent(job_id=job.id, level="info", type="t"))
    session.add(
        AssetSeen(target_id=target_id, source_id=source_id, url_hash=b"\x02" * 16, seen_at=1)
    )
    await session.flush()
    await session.execute(delete(Source).where(Source.id == source_id))
    assert (await session.execute(select(Job))).all() == []
    assert (await session.execute(select(JobEvent))).all() == []
    seen = (await session.execute(select(AssetSeen))).scalars().all()
    assert len(seen) == 1 and seen[0].source_id is None
    await session.rollback()
    target_id, _ = await _seed(session)
    with pytest.raises(IntegrityError):
        await session.execute(text("DELETE FROM immich_targets WHERE id = :i"), {"i": target_id})
