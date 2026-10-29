import anyio.to_thread
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_obj, secret_box
from app.api.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page, paginate
from app.api.v1.shares import delete_shares, shares_router
from app.auth.authz import (
    access_flags,
    can_edit,
    can_use,
    require_owner_or_admin,
    require_scope,
    visible_to,
)
from app.auth.deps import current_principal
from app.auth.principal import Principal
from app.core.crypto import SecretBox
from app.db.engine import get_session
from app.db.models import ImmichTarget, Perm, Source
from app.immich.client import Album, ImmichClient, missing_permissions, optional_missing
from app.immich.errors import ImmichAuthError, ImmichError, ImmichUnavailable
from app.schemas.immich import AlbumList, AlbumOut, TargetTestOut
from app.schemas.targets import TargetIn, TargetOut, TargetPatch

router = APIRouter(prefix="/targets", tags=["targets"])


@router.get("", response_model=Page[TargetOut])
async def list_targets(
    cursor: str | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> Page[TargetOut]:
    require_scope(p, "targets:read")
    rows, nxt = await paginate(
        session, visible_to(select(ImmichTarget), ImmichTarget, p), cursor, limit
    )
    ed, us = await access_flags(session, ImmichTarget, p, [r.id for r in rows])
    return Page(items=[TargetOut.of(r, r.id in ed, r.id in us) for r in rows], next_cursor=nxt)


@router.post("", response_model=TargetOut, status_code=201)
async def create_target(
    body: TargetIn,
    p: Principal = Depends(current_principal),
    box: SecretBox = Depends(secret_box),
    session: AsyncSession = Depends(get_session, scope="function"),
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
    return TargetOut.of(t, True, True)


@router.get("/{obj_id}", response_model=TargetOut)
async def get_target(
    obj_id: int,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> TargetOut:
    require_scope(p, "targets:read")
    t: ImmichTarget = await get_obj(session, ImmichTarget, obj_id, p)
    return TargetOut.of(t, await can_edit(session, t, p), await can_use(session, t, p))


@router.patch("/{obj_id}", response_model=TargetOut)
async def patch_target(
    obj_id: int,
    body: TargetPatch,
    p: Principal = Depends(current_principal),
    box: SecretBox = Depends(secret_box),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> TargetOut:
    require_scope(p, "targets:write")
    t: ImmichTarget = await get_obj(session, ImmichTarget, obj_id, p, Perm.edit)
    data = body.model_dump(exclude_unset=True, exclude_none=True)
    if "api_key" in data:
        t.api_key_enc = box.encrypt(data.pop("api_key").encode())
    for k, v in data.items():
        setattr(t, k, v)
    await session.flush()
    return TargetOut.of(t, True, True)


@router.delete("/{obj_id}", status_code=204)
async def delete_target(
    obj_id: int,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session, scope="function"),
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


def _check_target(
    url: str, key_enc: bytes, box: SecretBox, transport: httpx.BaseTransport | None
) -> TargetTestOut:
    version: str | None = None
    try:
        with ImmichClient(url, box.decrypt(key_enc).decode(), transport=transport) as c:
            version = c.version()
            perms = c.key_permissions()
            missing = missing_permissions(perms)
            optional = optional_missing(perms)
    except ImmichAuthError:
        return TargetTestOut(ok=False, version=version, error="unauthorized")
    except ImmichUnavailable:
        return TargetTestOut(ok=False, version=version, error="unreachable")
    except ImmichError as e:
        return TargetTestOut(ok=False, version=version, error=f"immich error {e.status}")
    return TargetTestOut(
        ok=not missing, version=version, missing_permissions=missing, optional_missing=optional
    )


def _list_albums(
    url: str, key_enc: bytes, box: SecretBox, transport: httpx.BaseTransport | None
) -> list[Album]:
    with ImmichClient(url, box.decrypt(key_enc).decode(), transport=transport) as c:
        return c.list_albums()


@router.post("/{obj_id}/test", response_model=TargetTestOut)
async def test_target(
    obj_id: int,
    request: Request,
    p: Principal = Depends(current_principal),
    box: SecretBox = Depends(secret_box),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> TargetTestOut:
    require_scope(p, "targets:read")
    t: ImmichTarget = await get_obj(session, ImmichTarget, obj_id, p, Perm.use)
    transport = request.app.state.immich_transport
    return await anyio.to_thread.run_sync(_check_target, t.url, t.api_key_enc, box, transport)


@router.get("/{obj_id}/albums", response_model=AlbumList)
async def target_albums(
    obj_id: int,
    request: Request,
    p: Principal = Depends(current_principal),
    box: SecretBox = Depends(secret_box),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> AlbumList:
    require_scope(p, "targets:read")
    t: ImmichTarget = await get_obj(session, ImmichTarget, obj_id, p, Perm.use)
    transport = request.app.state.immich_transport
    try:
        albums = await anyio.to_thread.run_sync(_list_albums, t.url, t.api_key_enc, box, transport)
    except ImmichAuthError as e:
        raise HTTPException(502, "immich unauthorized") from e
    except (ImmichUnavailable, ImmichError) as e:
        raise HTTPException(502, "immich unavailable") from e
    albums.sort(key=lambda a: a.name.casefold())
    return AlbumList(
        items=[AlbumOut(id=a.id, name=a.name, asset_count=a.asset_count) for a in albums]
    )


router.include_router(shares_router(ImmichTarget, "targets"))
