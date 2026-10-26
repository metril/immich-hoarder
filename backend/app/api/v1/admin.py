import asyncio
import logging
from typing import Any, Literal

import yaml
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import secret_box
from app.auth.deps import require_admin
from app.auth.principal import Principal
from app.core.config import Settings
from app.core.crypto import SecretBox
from app.db.engine import get_session
from app.db.models import User
from app.runtime.configio import export_config, import_config
from app.runtime.maintenance import (
    backup_sqlite,
    list_backups,
    prune_ephemeral_sources,
    prune_jobs,
)
from app.runtime.settings import load_runtime_settings

log = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/backup", status_code=201)
async def create_backup(
    request: Request,
    _p: Principal = Depends(require_admin),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> dict[str, str]:
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
    return {"file": path.name}


@router.get("/backups")
async def get_backups(
    request: Request, _p: Principal = Depends(require_admin)
) -> dict[str, list[dict[str, object]]]:
    settings: Settings = request.app.state.settings
    return {"items": await asyncio.to_thread(list_backups, settings.backup_dir)}


@router.post("/maintenance/prune")
async def run_prune(
    _p: Principal = Depends(require_admin),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> dict[str, int]:
    rt = await load_runtime_settings(session)
    jobs = await prune_jobs(session, rt.retention_days)
    eph = await prune_ephemeral_sources(session)
    return {"jobs": jobs, "ephemeral_sources": eph}


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


@router.post("/import")
async def import_yaml(
    request: Request,
    dry_run: bool = False,
    p: Principal = Depends(require_admin),
    session: AsyncSession = Depends(get_session, scope="function"),
    box: SecretBox = Depends(secret_box),
) -> dict[str, Any]:
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
    return {**res.as_dict(), "applied": applied}
