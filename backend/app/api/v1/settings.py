from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_admin
from app.auth.principal import Principal
from app.db.engine import get_session
from app.db.models import Setting

router = APIRouter(prefix="/settings", tags=["settings"])


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
    _p: Principal = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    for k, v in body.items():
        row = await session.get(Setting, k)
        if row is None:
            session.add(Setting(key=k, value=v))
        else:
            row.value = v
    await session.flush()
    return await _all(session)
