import asyncio

from alembic import context
from sqlalchemy.engine import Connection

from app.db.engine import make_engine
from app.db.models import Base

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    url = config.attributes.get("database_url")
    if url:
        return str(url)
    from app.core.config import get_settings

    return get_settings().database_url


def _configure(connection: Connection | None, **kw: object) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
        compare_type=True,
        **kw,  # type: ignore[arg-type]
    )


def _run(connection: Connection) -> None:
    _configure(connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_online() -> None:
    engine = make_engine(_url())
    async with engine.connect() as conn:
        await conn.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    _configure(None, url=_url(), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    existing = config.attributes.get("connection")
    if existing is not None:
        _run(existing)
    else:
        asyncio.run(run_online())
