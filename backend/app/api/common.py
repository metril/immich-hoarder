from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.authz import require_perm
from app.auth.principal import Principal
from app.core.crypto import SecretBox
from app.db.models import Perm


async def get_obj(
    session: AsyncSession, model: type[Any], obj_id: int, p: Principal, perm: Perm = Perm.use
) -> Any:
    obj = await session.get(model, obj_id)
    if obj is None:
        raise HTTPException(404, "not found")
    await require_perm(session, obj, p, perm)
    return obj


def secret_box(request: Request) -> SecretBox:
    return SecretBox(request.app.state.settings.master_key.get_secret_value())
