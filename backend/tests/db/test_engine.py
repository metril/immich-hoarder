from pathlib import Path

from sqlalchemy import text

from app.db.engine import make_engine
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
    finally:
        await engine.dispose()
