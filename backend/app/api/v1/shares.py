from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_obj
from app.auth.authz import require_owner_or_admin, require_scope
from app.auth.deps import current_principal
from app.auth.principal import Principal
from app.db.engine import get_session
from app.db.models import Share
from app.schemas.shares import ShareEntry, SharesBody


async def delete_shares(session: AsyncSession, share_type: str, obj_id: int) -> None:
    await session.execute(
        delete(Share).where(Share.resource_type == share_type, Share.resource_id == obj_id)
    )


def shares_router(model: type[Any], resource: str) -> APIRouter:
    router = APIRouter()
    stype: str = model.share_type

    @router.get("/{obj_id}/shares", response_model=SharesBody)
    async def get_shares(
        obj_id: int,
        p: Principal = Depends(current_principal),
        session: AsyncSession = Depends(get_session),
    ) -> SharesBody:
        require_scope(p, f"{resource}:read")
        obj = await get_obj(session, model, obj_id, p)
        await require_owner_or_admin(session, obj, p)
        rows = (
            await session.execute(
                select(Share)
                .where(Share.resource_type == stype, Share.resource_id == obj_id)
                .order_by(Share.id)
            )
        ).scalars()
        return SharesBody(
            visibility=obj.visibility,
            shares=[
                ShareEntry(
                    principal_type=s.principal_type, principal_id=s.principal_id, perm=s.perm
                )
                for s in rows
            ],
        )

    @router.put("/{obj_id}/shares", response_model=SharesBody)
    async def put_shares(
        obj_id: int,
        body: SharesBody,
        p: Principal = Depends(current_principal),
        session: AsyncSession = Depends(get_session),
    ) -> SharesBody:
        require_scope(p, f"{resource}:write")
        obj = await get_obj(session, model, obj_id, p)
        await require_owner_or_admin(session, obj, p)
        await delete_shares(session, stype, obj_id)
        seen: dict[tuple[str, str], ShareEntry] = {}
        for e in body.shares:  # last entry wins per principal
            seen[(e.principal_type.value, e.principal_id)] = e
        for e in seen.values():
            session.add(
                Share(
                    resource_type=stype,
                    resource_id=obj_id,
                    principal_type=e.principal_type,
                    principal_id=e.principal_id,
                    perm=e.perm,
                )
            )
        obj.visibility = body.visibility
        await session.flush()
        return SharesBody(visibility=body.visibility, shares=list(seen.values()))

    return router
