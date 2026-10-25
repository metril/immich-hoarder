from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_obj
from app.api.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page, paginate
from app.api.v1.shares import delete_shares, shares_router
from app.auth.authz import require_owner_or_admin, require_scope, visible_to
from app.auth.deps import current_principal
from app.auth.principal import Principal
from app.core.extractors import UnsupportedURL, validate_url
from app.db.engine import get_session
from app.db.models import BackfillMode, Credential, ImmichTarget, Perm, Source, User
from app.rip.filters import validate_backfill
from app.rip.settings import load_rip_settings
from app.schemas.sources import SourceIn, SourceOut, SourcePatch

router = APIRouter(prefix="/sources", tags=["sources"])


async def _check_refs(
    session: AsyncSession, owner_id: int, target_id: int, credential_id: int | None
) -> None:
    """The source owner (not the caller) must have `use` on the target and credential."""
    owner = await session.get(User, owner_id)
    if owner is None:
        raise HTTPException(422, "invalid owner")
    if owner.disabled:
        raise HTTPException(403, "source owner is disabled")
    op = Principal(owner.id, owner.role, frozenset(owner.groups or []), None)
    checks: list[tuple[type[ImmichTarget] | type[Credential], int | None]] = [
        (ImmichTarget, target_id),
        (Credential, credential_id),
    ]
    for model, ref in checks:
        if ref is None:
            continue
        stmt = visible_to(select(model.id).where(model.id == ref), model, op, Perm.use)
        if (await session.execute(stmt)).first() is None:
            raise HTTPException(403, f"no access to {model.share_type}")


async def _extractor_for(session: AsyncSession, url: str) -> str:
    rip = await load_rip_settings(session)
    try:
        return validate_url(url, allow_private=rip.allow_private_hosts)
    except UnsupportedURL as e:
        raise HTTPException(422, str(e)) from None


@router.get("", response_model=Page[SourceOut])
async def list_sources(
    cursor: str | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    include_ephemeral: bool = False,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session),
) -> Page[SourceOut]:
    require_scope(p, "sources:read")
    stmt = visible_to(select(Source), Source, p)
    if not include_ephemeral:
        stmt = stmt.where(Source.ephemeral.is_(False))
    rows, nxt = await paginate(session, stmt, cursor, limit)
    return Page(items=[SourceOut.of(r) for r in rows], next_cursor=nxt)


@router.post("", response_model=SourceOut, status_code=201)
async def create_source(
    body: SourceIn,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session),
) -> SourceOut:
    require_scope(p, "sources:write")
    await _check_refs(session, p.user_id, body.target_id, body.credential_id)
    extractor = await _extractor_for(session, body.url)
    s = Source(
        **body.model_dump(),
        extractor=extractor,
        owner_id=p.user_id,
    )
    session.add(s)
    await session.flush()
    return SourceOut.of(s)


@router.get("/{obj_id}", response_model=SourceOut)
async def get_source(
    obj_id: int,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session),
) -> SourceOut:
    require_scope(p, "sources:read")
    return SourceOut.of(await get_obj(session, Source, obj_id, p))


@router.patch("/{obj_id}", response_model=SourceOut)
async def patch_source(
    obj_id: int,
    body: SourcePatch,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session),
) -> SourceOut:
    require_scope(p, "sources:write")
    s: Source = await get_obj(session, Source, obj_id, p, Perm.edit)
    data = body.model_dump(exclude_unset=True)
    for col in (
        "name",
        "url",
        "target_id",
        "album_template",
        "backfill_mode",
        "allow_animated",
        "filters",
        "notify",
        "gdl_options",
        "enabled",
        "ephemeral",
    ):
        if col in data and data[col] is None:
            raise HTTPException(422, f"{col} cannot be null")
    mode = data.get("backfill_mode", s.backfill_mode)
    value = data["backfill_value"] if "backfill_value" in data else s.backfill_value
    if "backfill_mode" in data and "backfill_value" not in data and mode != s.backfill_mode:
        value = None if mode == BackfillMode.full else value
    try:
        validate_backfill(mode, value)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    for k, v in data.items():
        setattr(s, k, v)
    s.backfill_value = value
    if "url" in data:
        s.extractor = await _extractor_for(session, s.url)
    await _check_refs(session, s.owner_id, s.target_id, s.credential_id)
    await session.flush()
    return SourceOut.of(s)


@router.delete("/{obj_id}", status_code=204)
async def delete_source(
    obj_id: int,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session),
) -> Response:
    require_scope(p, "sources:write")
    s: Source = await get_obj(session, Source, obj_id, p)
    await require_owner_or_admin(session, s, p)
    await delete_shares(session, Source.share_type, obj_id)
    await session.delete(s)
    await session.flush()
    return Response(status_code=204)


router.include_router(shares_router(Source, "sources"))
