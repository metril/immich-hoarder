import asyncio
import logging
from pathlib import Path
from typing import Any, Literal

import yaml
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy import exists, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import secret_box
from app.auth.deps import require_admin
from app.auth.principal import Principal
from app.core.config import Settings
from app.core.crypto import SecretBox
from app.db.engine import get_session
from app.db.models import Job, JobStatus, User
from app.runtime.configio import export_config, import_config
from app.runtime.maintenance import (
    backup_sqlite,
    cancel_pending_restore,
    list_backups,
    pending_path,
    prune_ephemeral_sources,
    prune_jobs,
    resolve_backup,
    stage_restore,
)
from app.runtime.settings import load_runtime_settings
from app.schemas.admin import BackupInfo, BackupList, BackupOut, ImportResult, PruneOut, RestoreOut

log = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/backup", status_code=201, response_model=BackupOut)
async def create_backup(
    request: Request,
    _p: Principal = Depends(require_admin),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> BackupOut:
    settings: Settings = request.app.state.settings
    rt = await load_runtime_settings(session)
    try:
        path = await asyncio.to_thread(
            backup_sqlite, settings.database_url, settings.backup_dir, rt.backup_keep
        )
    except ValueError as e:
        raise HTTPException(500, str(e)) from None
    except (OSError, DBAPIError) as e:
        log.error("backup failed: %s", type(e).__name__)
        raise HTTPException(507, "backup failed") from None
    if path is None:
        raise HTTPException(409, "backups are not supported for this database")
    return BackupOut(file=path.name)


@router.get(
    "/backups",
    response_model=BackupList,
    summary="List backups",
    description="Lists SQLite backups newest first, and whether a restore is staged.",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Admin access required"},
    },
)
async def get_backups(request: Request, _p: Principal = Depends(require_admin)) -> BackupList:
    settings: Settings = request.app.state.settings
    rows = await asyncio.to_thread(list_backups, settings.backup_dir)
    pending = pending_path(settings.database_url)
    return BackupList(
        items=[BackupInfo.model_validate(r) for r in rows],
        restore_pending=bool(pending and pending.exists()),
    )


_AUTH: dict[int | str, dict[str, Any]] = {
    401: {"description": "Not authenticated"},
    403: {"description": "Admin access required"},
}


def _backup_or_404(settings: Settings, name: str) -> Path:
    p = resolve_backup(settings.backup_dir, name)
    if p is None:
        raise HTTPException(404, "backup not found")
    return p


# Declared before /backups/{name} so the literal path wins.
@router.delete(
    "/backups/pending-restore",
    status_code=204,
    summary="Cancel a staged restore",
    description="Discards a restore staged by the restore endpoint, so the next startup keeps "
    "the current database.",
    responses={**_AUTH, 404: {"description": "No restore is pending"}},
)
async def cancel_restore(request: Request, _p: Principal = Depends(require_admin)) -> Response:
    settings: Settings = request.app.state.settings
    if not await asyncio.to_thread(cancel_pending_restore, settings.database_url):
        raise HTTPException(404, "no restore is pending")
    return Response(status_code=204)


@router.get(
    "/backups/{name}",
    summary="Download a backup",
    description="Streams a SQLite backup file as an attachment. The download is audit-logged.",
    response_class=FileResponse,
    responses={
        **_AUTH,
        200: {
            "description": "The SQLite database file",
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            },
        },
        404: {"description": "No backup with that name"},
        422: {"description": "Validation error"},
    },
)
async def download_backup(
    name: str,
    request: Request,
    p: Principal = Depends(require_admin),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> FileResponse:
    path = _backup_or_404(request.app.state.settings, name)
    log.info("backup %s downloaded by admin %s", path.name, await _actor(session, p))
    return FileResponse(path, media_type="application/octet-stream", filename=path.name)


@router.delete(
    "/backups/{name}",
    status_code=204,
    summary="Delete a backup",
    description="Permanently deletes one backup file. The deletion is audit-logged.",
    responses={
        **_AUTH,
        404: {"description": "No backup with that name"},
        422: {"description": "Validation error"},
    },
)
async def delete_backup(
    name: str,
    request: Request,
    p: Principal = Depends(require_admin),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> Response:
    path = _backup_or_404(request.app.state.settings, name)
    path.unlink(missing_ok=True)
    log.info("backup %s deleted by admin %s", path.name, await _actor(session, p))
    return Response(status_code=204)


@router.post(
    "/backups/{name}/restore",
    status_code=202,
    response_model=RestoreOut,
    summary="Restore a backup",
    description="Validates the backup (integrity check, known migration revision) and stages it. "
    "The live database is not touched: the staged file replaces it at the next startup, and the "
    "previous database is kept as pre-restore-<timestamp>.db. All sessions are signed out after "
    "a restore. Pass restart=true to shut the app down gracefully after responding so the "
    "container's restart policy brings it back.",
    responses={
        **_AUTH,
        404: {"description": "No backup with that name"},
        409: {"description": "A job is active, or the database is not SQLite"},
        422: {"description": "Backup is corrupt or from a newer app version"},
        507: {"description": "Could not write the staged file"},
    },
)
async def restore_backup(
    name: str,
    request: Request,
    background: BackgroundTasks,
    restart: bool = False,
    p: Principal = Depends(require_admin),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> RestoreOut:
    settings: Settings = request.app.state.settings
    if pending_path(settings.database_url) is None:
        raise HTTPException(409, "restore is not supported for this database")
    path = _backup_or_404(settings, name)
    active = await session.scalar(
        select(exists().where(Job.status.in_((JobStatus.queued, JobStatus.running))))
    )
    if active:
        raise HTTPException(409, "a job is active; wait for it to finish or cancel it")
    try:
        await asyncio.to_thread(stage_restore, settings.database_url, path)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    except OSError as e:
        log.error("staging restore failed: %s", type(e).__name__)
        raise HTTPException(507, "could not stage the restore") from None
    log.warning(
        "restore of %s staged by admin %s (restart=%s)",
        path.name,
        await _actor(session, p),
        restart,
    )
    if restart:
        background.add_task(request.app.state.shutdown)
    return RestoreOut(restart_required=True, restarting=restart)


@router.post("/maintenance/prune", response_model=PruneOut)
async def run_prune(
    _p: Principal = Depends(require_admin),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> PruneOut:
    rt = await load_runtime_settings(session)
    jobs = await prune_jobs(session, rt.retention_days)
    eph = await prune_ephemeral_sources(session)
    return PruneOut(jobs=jobs, ephemeral_sources=eph)


MAX_IMPORT_BYTES = 5 * 1024 * 1024


async def _actor(session: AsyncSession, p: Principal) -> str:
    u = await session.get(User, p.user_id)
    return u.sub if u else str(p.user_id)


@router.get("/export")
async def export_yaml(
    secrets: Literal["omit", "encrypted"] = "omit",
    p: Principal = Depends(require_admin),
    session: AsyncSession = Depends(get_session, scope="function"),
    box: SecretBox = Depends(secret_box),
) -> Response:
    doc = await export_config(session, box if secrets == "encrypted" else None)
    log.info("config export by admin %s (secrets=%s)", await _actor(session, p), secrets)
    return Response(
        yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), media_type="application/yaml"
    )


async def _read_limited(request: Request) -> bytes:
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > MAX_IMPORT_BYTES:
        raise HTTPException(413, "import body too large")
    buf = bytearray()
    async for chunk in request.stream():
        buf += chunk
        if len(buf) > MAX_IMPORT_BYTES:
            raise HTTPException(413, "import body too large")
    return bytes(buf)


@router.post(
    "/import",
    response_model=ImportResult,
    openapi_extra={
        "requestBody": {
            "content": {"application/yaml": {"schema": {"type": "string"}}},
            "required": True,
        }
    },
)
async def import_yaml(
    request: Request,
    dry_run: bool = False,
    p: Principal = Depends(require_admin),
    session: AsyncSession = Depends(get_session, scope="function"),
    box: SecretBox = Depends(secret_box),
) -> ImportResult:
    raw = await _read_limited(request)
    try:
        doc = yaml.safe_load(raw.decode())
    except (yaml.YAMLError, UnicodeDecodeError):
        raise HTTPException(422, "invalid yaml") from None
    if not isinstance(doc, dict):
        raise HTTPException(422, "yaml root must be a mapping")
    if doc.get("version") != 1 or isinstance(doc.get("version"), bool):
        raise HTTPException(422, "unsupported version (expected 1)")
    actor = await _actor(session, p)
    res = await import_config(session, p, box, doc)
    applied = not dry_run and not res.errors
    if applied:
        await session.commit()
        sched = getattr(request.app.state, "scheduler", None)
        if sched is not None:
            try:
                for sid in res.new_source_ids:
                    await sched.sync_source(sid)
                if res.runtime_changed:
                    await sched.sync_maintenance()
            except Exception as e:  # already committed; never turn it into a 500
                log.error("scheduler sync after import failed: %s", type(e).__name__)
    else:
        await session.rollback()
    log.info(
        "config import by admin %s (dry_run=%s applied=%s errors=%d)",
        actor,
        dry_run,
        applied,
        len(res.errors),
    )
    return ImportResult(**res.as_dict(), applied=applied)
