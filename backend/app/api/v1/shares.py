from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_obj
from app.auth.authz import require_owner_or_admin, require_scope
from app.auth.deps import current_principal
from app.auth.principal import Principal
from app.db.engine import get_session
from app.db.models import PrincipalType, Share, User
from app.schemas.shares import ShareEntry, SharesBody


async def delete_shares(session: AsyncSession, share_type: str, obj_id: int) -> None:
    await session.execute(
        delete(Share).where(Share.resource_type == share_type, Share.resource_id == obj_id)
    )


async def _user_exists(session: AsyncSession, principal_id: str) -> bool:
    if not principal_id.isascii() or not principal_id.isdigit():
        return False
    return await session.get(User, int(principal_id)) is not None


async def _with_names(session: AsyncSession, entries: list[ShareEntry]) -> list[ShareEntry]:
    ids = [
        int(e.principal_id)
        for e in entries
        if e.principal_type == PrincipalType.user
        and e.principal_id.isascii()
        and e.principal_id.isdigit()
    ]
    names: dict[int, str | None] = {}
    if ids:
        names = {
            uid: name
            for uid, name in (
                await session.execute(select(User.id, User.name).where(User.id.in_(ids)))
            ).all()
        }
    out: list[ShareEntry] = []
    for e in entries:
        pname: str | None
        if e.principal_type == PrincipalType.group:
            pname = e.principal_id
        else:
            pname = names.get(int(e.principal_id)) if e.principal_id.isdigit() else None
        out.append(e.model_copy(update={"principal_name": pname}))
    return out


def shares_router(model: type[Any], resource: str) -> APIRouter:
    router = APIRouter()
    stype: str = model.share_type

    @router.get("/{obj_id}/shares", response_model=SharesBody, name=f"get_{resource}_shares")
    async def get_shares(
        obj_id: int,
        p: Principal = Depends(current_principal),
        session: AsyncSession = Depends(get_session, scope="function"),
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
            shares=await _with_names(
                session,
                [
                    ShareEntry(
                        principal_type=s.principal_type, principal_id=s.principal_id, perm=s.perm
                    )
                    for s in rows
                ],
            ),
        )

    @router.put("/{obj_id}/shares", response_model=SharesBody, name=f"put_{resource}_shares")
    async def put_shares(
        obj_id: int,
        body: SharesBody,
        p: Principal = Depends(current_principal),
        session: AsyncSession = Depends(get_session, scope="function"),
    ) -> SharesBody:
        require_scope(p, f"{resource}:write")
        obj = await get_obj(session, model, obj_id, p)
        await require_owner_or_admin(session, obj, p)
        await delete_shares(session, stype, obj_id)
        seen: dict[tuple[str, str], ShareEntry] = {}
        for e in body.shares:  # last entry wins per principal
            seen[(e.principal_type.value, e.principal_id)] = e
        for e in seen.values():
            if e.principal_type == PrincipalType.user and not await _user_exists(
                session, e.principal_id
            ):
                raise HTTPException(422, "unknown user")
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
        return SharesBody(
            visibility=body.visibility, shares=await _with_names(session, list(seen.values()))
        )

    return router
