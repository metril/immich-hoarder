from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_admin
from app.auth.principal import Principal
from app.db.engine import get_session
from app.db.models import Setting
from app.rip.settings import RipSettings
from app.runtime.settings import NotifySettings, RuntimeSettings

router = APIRouter(prefix="/settings", tags=["settings"])

SCHEMAS: dict[str, type[BaseModel]] = {
    "rip": RipSettings,
    "runtime": RuntimeSettings,
    "notify": NotifySettings,
}


async def _all(session: AsyncSession) -> dict[str, Any]:
    return {s.key: s.value for s in (await session.execute(select(Setting))).scalars()}


@router.get("")
async def get_settings(
    _p: Principal = Depends(require_admin), session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    return await _all(session)


@router.put("")
async def put_settings(
    body: dict[str, Any],
    request: Request,
    _p: Principal = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    unknown = sorted(set(body) - SCHEMAS.keys())
    if unknown:
        raise HTTPException(422, f"unknown settings keys: {', '.join(unknown)}")
    for k, v in body.items():
        try:
            SCHEMAS[k].model_validate(v)
        except ValidationError as e:
            raise HTTPException(
                422, e.errors(include_url=False, include_context=False, include_input=False)
            ) from None
    for k, v in body.items():
        row = await session.get(Setting, k)
        if row is None:
            session.add(Setting(key=k, value=v))
        else:
            row.value = v
    await session.flush()
    await session.commit()
    sched = getattr(request.app.state, "scheduler", None)
    if sched is not None and "runtime" in body:
        await sched.sync_maintenance()
    return await _all(session)
