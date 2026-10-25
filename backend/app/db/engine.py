from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def normalize_url(url: str) -> str:
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix) :]
    return url


_MASK64 = (1 << 64) - 1


def _hamming_udf(a: int | None, b: int | None) -> int | None:
    if a is None or b is None:
        return None
    return ((a ^ b) & _MASK64).bit_count()


def _apply_sqlite_pragmas(dbapi_conn: Any, _record: Any) -> None:
    cur = dbapi_conn.cursor()
    # page_size must be set before WAL is enabled / first table is created
    cur.execute("PRAGMA page_size=65536")
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA mmap_size=268435456")
    cur.execute("PRAGMA cache_size=-65536")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.close()
    dbapi_conn.create_function("hamming", 2, _hamming_udf, deterministic=True)


def make_engine(url: str) -> AsyncEngine:
    url = normalize_url(url)
    engine = create_async_engine(url)
    if make_url(url).get_backend_name() == "sqlite":
        event.listen(engine.sync_engine, "connect", _apply_sqlite_pragmas)
    return engine


def make_sync_engine(url: str) -> Engine:
    u = make_url(normalize_url(url))
    backend = u.get_backend_name()
    if backend == "sqlite":
        u = u.set(drivername="sqlite+pysqlite")
        engine = create_engine(u, connect_args={"check_same_thread": False})
        event.listen(engine, "connect", _apply_sqlite_pragmas)
        return engine
    if backend == "postgresql":
        u = u.set(drivername="postgresql+psycopg")
        if "ssl" in u.query:  # asyncpg-style -> libpq/psycopg
            ssl = str(u.query["ssl"])
            mode = {"true": "require", "false": "disable"}.get(ssl.lower(), ssl)
            u = u.difference_update_query(["ssl"]).update_query_dict({"sslmode": mode})
    return create_engine(u)


def init_engine(url: str) -> AsyncEngine:
    global _engine, _sessionmaker
    _engine = make_engine(url)
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    if _sessionmaker is None:
        raise RuntimeError("database engine is not initialised")
    async with _sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_scope() as session:
        yield session
