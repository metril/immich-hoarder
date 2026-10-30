"""Retention pruning and SQLite backups."""

import logging
import os
import re
import shutil
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import NamedTuple

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
_BACKUP_NAME = re.compile(rf"{re.escape(_PREFIX)}\d{{8}}-\d{{6}}(-\d+)?{re.escape(_SUFFIX)}")
PENDING_NAME = "restore-pending.db"


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


def resolve_backup(backup_dir: Path, name: str) -> Path | None:
    """Return the backup file for ``name`` or None; never escapes ``backup_dir``."""
    if not _BACKUP_NAME.fullmatch(name):
        return None
    p = backup_dir / name
    try:
        if p.is_symlink() or not p.is_file():
            return None
        if p.resolve().parent != backup_dir.resolve():
            return None
    except OSError:
        return None
    return p


def sqlite_file(db_url: str) -> Path | None:
    url = make_url(normalize_url(db_url))
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return None
    return Path(url.database)


def pending_path(db_url: str) -> Path | None:
    db = sqlite_file(db_url)
    return db.parent / PENDING_NAME if db else None


def _check_db_file(path: Path) -> str | None:
    """integrity_check the file; return its alembic revision (or None if absent)."""
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = con.execute("PRAGMA integrity_check").fetchall()
        if rows != [("ok",)]:
            raise ValueError("backup failed integrity check")
        try:
            row = con.execute("SELECT version_num FROM alembic_version").fetchone()
        except sqlite3.DatabaseError:
            return None
        return str(row[0]) if row else None
    finally:
        con.close()


def _known_revisions() -> set[str]:
    from alembic.script import ScriptDirectory

    from app.db.migrate import alembic_config

    script = ScriptDirectory.from_config(alembic_config("sqlite://"))
    return {r.revision for r in script.walk_revisions()}


def stage_restore(db_url: str, backup: Path) -> Path:
    """Validate ``backup`` and atomically stage it for the next startup."""
    pending = pending_path(db_url)
    if pending is None:
        raise RuntimeError("restore is not supported for this database")
    try:
        rev = _check_db_file(backup)
    except sqlite3.DatabaseError:
        raise ValueError("backup is not a valid database") from None
    if rev is None or rev not in _known_revisions():
        raise ValueError("backup was made by a newer or unknown version")
    tmp = pending.with_name(pending.name + ".tmp")
    try:
        shutil.copyfile(backup, tmp)
        os.replace(tmp, pending)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return pending


def cancel_pending_restore(db_url: str) -> bool:
    pending = pending_path(db_url)
    if pending is None or not pending.exists():
        return False
    pending.unlink(missing_ok=True)
    return True


def _drop_sidecars(db: Path) -> None:
    for suffix in ("-wal", "-shm"):
        Path(str(db) + suffix).unlink(missing_ok=True)


class RestoreResult(NamedTuple):
    saved: Path | None  # the pre-restore DB, or None when there was no original to keep
    session_floor: int  # highest session_gen in the replaced DB (0 if none)


def _max_session_gen(db: Path) -> int:
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            row = con.execute("SELECT max(session_gen) FROM users").fetchone()
            return int(row[0] or 0)
        finally:
            con.close()
    except sqlite3.Error:
        return 0


def apply_pending_restore(db_url: str) -> RestoreResult | None:
    """Swap a staged restore in. Call at startup before any connection is open.

    Returns a RestoreResult when a restore was applied, else None.
    On any failure the original DB is put back and the pending file is removed.
    """
    db = sqlite_file(db_url)
    pending = pending_path(db_url)
    if db is None or pending is None or not pending.exists():
        return None
    try:
        _check_db_file(pending)
    except (sqlite3.DatabaseError, ValueError) as e:
        log.error("pending restore rejected (%s); keeping current database", type(e).__name__)
        pending.unlink(missing_ok=True)
        return None
    saved = db.with_name(f"pre-restore-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.db")
    moved = False
    floor = _max_session_gen(db) if db.exists() else 0
    try:
        if db.exists():
            try:  # fold any WAL into the main file so the saved copy is complete
                con = sqlite3.connect(db)
                try:
                    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                finally:
                    con.close()
            except sqlite3.Error:
                pass
            os.replace(db, saved)
            moved = True
        os.replace(pending, db)
        _drop_sidecars(db)
    except BaseException as e:
        log.error("applying pending restore failed (%s); restoring original", type(e).__name__)
        try:
            if moved:
                os.replace(saved, db)
        finally:
            pending.unlink(missing_ok=True)
        if not isinstance(e, Exception):
            raise
        return None
    log.warning("restored database from staged backup; previous database saved as %s", saved.name)
    return RestoreResult(saved if moved else None, floor)


def revert_restore(db_url: str, saved: Path) -> None:
    """Undo an applied restore (e.g. its migrations failed) by putting ``saved`` back."""
    db = sqlite_file(db_url)
    if db is None or not saved.exists():
        return
    _drop_sidecars(db)
    os.replace(saved, db)
    _drop_sidecars(db)


def discard_database(db_url: str) -> None:
    """Delete the live DB file (used when a restore without an original fails to migrate)."""
    db = sqlite_file(db_url)
    if db is None:
        return
    db.unlink(missing_ok=True)
    _drop_sidecars(db)
