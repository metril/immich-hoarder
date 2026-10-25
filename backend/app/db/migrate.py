import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config

BACKEND_DIR = Path(__file__).resolve().parents[2]


def alembic_config(url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["database_url"] = url
    return cfg


def upgrade_head(url: str) -> None:
    command.upgrade(alembic_config(url), "head")


async def upgrade_head_async(url: str) -> None:
    # env.py drives its own event loop, so run in a worker thread
    await asyncio.to_thread(upgrade_head, url)
