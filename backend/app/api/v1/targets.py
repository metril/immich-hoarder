from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_obj, secret_box
from app.api.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page, paginate
from app.api.v1.shares import delete_shares, shares_router
from app.auth.authz import require_owner_or_admin, require_scope, visible_to
from app.auth.deps import current_principal
from app.auth.principal import Principal
from app.core.crypto import SecretBox
from app.db.engine import get_session
from app.db.models import ImmichTarget, Perm, Source
from app.schemas.targets import TargetIn, TargetOut, TargetPatch

router = APIRouter(prefix="/targets", tags=["targets"])


@router.get("", response_model=Page[TargetOut])
async def list_targets(
    cursor: str | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session),
) -> Page[TargetOut]:
    require_scope(p, "targets:read")
    rows, nxt = await paginate(
        session, visible_to(select(ImmichTarget), ImmichTarget, p), cursor, limit
    )
    return Page(items=[TargetOut.of(r) for r in rows], next_cursor=nxt)


@router.post("", response_model=TargetOut, status_code=201)
async def create_target(
    body: TargetIn,
    p: Principal = Depends(current_principal),
    box: SecretBox = Depends(secret_box),
    session: AsyncSession = Depends(get_session),
) -> TargetOut:
    require_scope(p, "targets:write")
    t = ImmichTarget(
        name=body.name,
        url=body.url,
        api_key_enc=box.encrypt(body.api_key.encode()),
        owner_id=p.user_id,
        visibility=body.visibility,
    )
    session.add(t)
    await session.flush()
    return TargetOut.of(t)


@router.get("/{obj_id}", response_model=TargetOut)
async def get_target(
    obj_id: int,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session),
) -> TargetOut:
    require_scope(p, "targets:read")
    return TargetOut.of(await get_obj(session, ImmichTarget, obj_id, p))


@router.patch("/{obj_id}", response_model=TargetOut)
async def patch_target(
    obj_id: int,
    body: TargetPatch,
    p: Principal = Depends(current_principal),
    box: SecretBox = Depends(secret_box),
    session: AsyncSession = Depends(get_session),
) -> TargetOut:
    require_scope(p, "targets:write")
    t: ImmichTarget = await get_obj(session, ImmichTarget, obj_id, p, Perm.edit)
    data = body.model_dump(exclude_unset=True, exclude_none=True)
    if "api_key" in data:
        t.api_key_enc = box.encrypt(data.pop("api_key").encode())
    for k, v in data.items():
        setattr(t, k, v)
    await session.flush()
    return TargetOut.of(t)


@router.delete("/{obj_id}", status_code=204)
async def delete_target(
    obj_id: int,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session),
) -> Response:
    require_scope(p, "targets:write")
    t: ImmichTarget = await get_obj(session, ImmichTarget, obj_id, p)
    await require_owner_or_admin(session, t, p)
    used = await session.execute(select(Source.id).where(Source.target_id == obj_id).limit(1))
    if used.first() is not None:
        raise HTTPException(409, "in use")
    await delete_shares(session, ImmichTarget.share_type, obj_id)
    await session.delete(t)
    await session.flush()
    return Response(status_code=204)


router.include_router(shares_router(ImmichTarget, "targets"))
