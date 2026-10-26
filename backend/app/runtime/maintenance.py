"""Retention pruning and SQLite backups."""

import logging
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, exists
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import make_sync_engine, normalize_url
from app.db.models import Job, JobStatus, Source

log = logging.getLogger(__name__)

_FINISHED = (JobStatus.succeeded, JobStatus.failed, JobStatus.cancelled)
_EPHEMERAL_GRACE = timedelta(hours=1)  # source is created just before its job is enqueued
_SAFE_DIR = re.compile(r"^[A-Za-z0-9_./ +=@,-]+$")
_PREFIX, _SUFFIX = "hoarder-", ".db"


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def prune_jobs(session: AsyncSession, retention_days: int) -> int:
    """Delete finished jobs older than the cutoff; events/items go via FK cascade."""
    cutoff = _utcnow() - timedelta(days=retention_days)
    res = await session.execute(
        delete(Job).where(Job.status.in_(_FINISHED), Job.finished_at < cutoff)
    )
    return int(res.rowcount or 0)  # type: ignore[attr-defined]


async def prune_ephemeral_sources(session: AsyncSession) -> int:
    """Delete ephemeral sources that no longer have any job."""
    res = await session.execute(
        delete(Source).where(
            Source.ephemeral.is_(True),
            Source.created_at < _utcnow() - _EPHEMERAL_GRACE,
            ~exists().where(Job.source_id == Source.id),
        )
    )
    return int(res.rowcount or 0)  # type: ignore[attr-defined]


def backup_sqlite(db_url: str, backup_dir: Path, keep: int) -> Path | None:
    """VACUUM INTO a timestamped file, then retain the newest ``keep`` (0 = no rotation)."""
    url = make_url(normalize_url(db_url))
    if url.get_backend_name() != "sqlite":
        log.info("backups skipped: only SQLite databases are backed up by the app")
        return None
    if not url.database or url.database == ":memory:":
        log.info("backups skipped: in-memory database")
        return None
    if not _SAFE_DIR.fullmatch(str(backup_dir)):
        raise ValueError("unsupported characters in backup directory")
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    dest = backup_dir / f"{_PREFIX}{stamp}{_SUFFIX}"
    n = 0
    while dest.exists():
        n += 1
        dest = backup_dir / f"{_PREFIX}{stamp}-{n}{_SUFFIX}"
    quoted = str(dest).replace("'", "''")
    engine = make_sync_engine(db_url)
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.exec_driver_sql(f"VACUUM INTO '{quoted}'")
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    finally:
        engine.dispose()
    if keep > 0:
        files = sorted(
            backup_dir.glob(f"{_PREFIX}*{_SUFFIX}"), key=lambda p: (p.stat().st_mtime, p.name)
        )
        for old in files[:-keep]:
            old.unlink(missing_ok=True)
    return dest


def list_backups(backup_dir: Path) -> list[dict[str, object]]:
    if not backup_dir.is_dir():
        return []
    out: list[dict[str, object]] = []
    for p in sorted(backup_dir.glob(f"{_PREFIX}*{_SUFFIX}"), key=lambda p: p.name, reverse=True):
        st = p.stat()
        out.append(
            {
                "file": p.name,
                "size": st.st_size,
                "mtime": datetime.fromtimestamp(st.st_mtime, UTC).isoformat(),
            }
        )
    return out
