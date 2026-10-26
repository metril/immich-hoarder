import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_admin
from app.auth.principal import Principal
from app.core.config import Settings
from app.db.engine import get_session
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
    session: AsyncSession = Depends(get_session),
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
    _p: Principal = Depends(require_admin), session: AsyncSession = Depends(get_session)
) -> dict[str, int]:
    rt = await load_runtime_settings(session)
    jobs = await prune_jobs(session, rt.retention_days)
    eph = await prune_ephemeral_sources(session)
    return {"jobs": jobs, "ephemeral_sources": eph}
