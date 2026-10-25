from pathlib import Path

from sqlalchemy import text

from app.db.engine import make_engine, normalize_url
from app.db.migrate import upgrade_head_async


async def test_pragmas_applied(tmp_path: Path) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'p.db'}"
    await upgrade_head_async(url)
    engine = make_engine(url)
    try:
        async with engine.connect() as c:
            assert (await c.execute(text("PRAGMA journal_mode"))).scalar() == "wal"
            assert (await c.execute(text("PRAGMA page_size"))).scalar() == 65536
            assert (await c.execute(text("PRAGMA foreign_keys"))).scalar() == 1
            assert (await c.execute(text("PRAGMA synchronous"))).scalar() == 1
            assert (await c.execute(text("PRAGMA mmap_size"))).scalar() == 268435456
            assert (await c.execute(text("PRAGMA cache_size"))).scalar() == -65536
            assert (await c.execute(text("PRAGMA busy_timeout"))).scalar() == 5000
    finally:
        await engine.dispose()


def test_normalize_url() -> None:
    assert normalize_url("postgresql://u@h/d") == "postgresql+asyncpg://u@h/d"
    assert normalize_url("postgres://u@h/d") == "postgresql+asyncpg://u@h/d"
    assert normalize_url("sqlite+aiosqlite:///x.db") == "sqlite+aiosqlite:///x.db"
