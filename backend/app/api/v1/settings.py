import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_admin
from app.auth.principal import Principal
from app.db.engine import get_session
from app.db.models import Setting
from app.schemas.settings import SettingsDoc

log = logging.getLogger(__name__)
router = APIRouter(prefix="/settings", tags=["settings"])


async def _all(session: AsyncSession) -> SettingsDoc:
    rows: dict[str, Any] = {
        s.key: s.value for s in (await session.execute(select(Setting))).scalars()
    }
    return SettingsDoc.model_validate(
        {k: v for k, v in rows.items() if k in SettingsDoc.model_fields}
    )


@router.get("", response_model=SettingsDoc, response_model_exclude_unset=True)
async def get_settings(
    _p: Principal = Depends(require_admin),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> SettingsDoc:
    return await _all(session)


@router.put("", response_model=SettingsDoc, response_model_exclude_unset=True)
async def put_settings(
    body: SettingsDoc,
    request: Request,
    _p: Principal = Depends(require_admin),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> SettingsDoc:
    # only keys present in the request are written; a null value is ignored
    changed = {
        k: v for k, v in body.model_dump(mode="json", exclude_unset=True).items() if v is not None
    }
    for k, v in changed.items():
        row = await session.get(Setting, k)
        if row is None:
            session.add(Setting(key=k, value=v))
        else:
            row.value = v
    await session.flush()
    await session.commit()
    sched = getattr(request.app.state, "scheduler", None)
    if sched is not None and "runtime" in changed:
        try:
            await sched.sync_maintenance()
        except Exception as e:
            log.error("maintenance reschedule failed: %s", type(e).__name__)
    return await _all(session)
