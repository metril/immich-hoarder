from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_obj, secret_box
from app.api.pagination import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    Q_DESCRIPTION,
    SORT_DESCRIPTION,
    Page,
    apply_q,
    paginate,
)
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
from app.db.models import Credential, CredentialKind, Perm, Source
from app.rip.settings import load_rip_settings
from app.runtime.notify import check_notify_url
from app.runtime.settings import _apprise_ok
from app.schemas.credentials import CredentialIn, CredentialOut, CredentialPatch

router = APIRouter(prefix="/credentials", tags=["credentials"])

NameSort = Literal["id", "-id", "name", "-name", "created_at", "-created_at"]


async def _check_apprise(session: AsyncSession, url: str) -> None:
    """Reject invalid or SSRF-prone apprise URLs without echoing them."""
    try:
        check_notify_url(url, allow_private=(await load_rip_settings(session)).allow_private_hosts)
        if not _apprise_ok(url):
            raise ValueError("invalid notification url")
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


@router.get(
    "",
    response_model=Page[CredentialOut],
    summary="List credentials",
    description="Keyset-paginated list of credentials visible to the caller. "
    "Requires `credentials:read`. "
    "`q` matches name, site.",
    responses={
        400: {"description": "Cursor was issued for a different sort"},
        401: {"description": "Missing or invalid credentials"},
        403: {"description": "Missing `credentials:read` scope"},
        422: {"description": "Validation error"},
    },
)
async def list_credentials(
    cursor: str | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    q: Annotated[str | None, Query(max_length=100, description=Q_DESCRIPTION)] = None,
    sort: Annotated[NameSort | None, Query(description=SORT_DESCRIPTION)] = None,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> Page[CredentialOut]:
    require_scope(p, "credentials:read")
    stmt = apply_q(
        visible_to(select(Credential), Credential, p), q, Credential.name, Credential.site
    )
    rows, nxt = await paginate(
        session,
        stmt,
        cursor,
        limit,
        sort=sort,
        sort_cols={"name": Credential.name, "created_at": Credential.created_at},
    )
    ed, us = await access_flags(session, Credential, p, [r.id for r in rows])
    return Page(items=[CredentialOut.of(r, r.id in ed, r.id in us) for r in rows], next_cursor=nxt)


@router.post("", response_model=CredentialOut, status_code=201)
async def create_credential(
    body: CredentialIn,
    p: Principal = Depends(current_principal),
    box: SecretBox = Depends(secret_box),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> CredentialOut:
    require_scope(p, "credentials:write")
    if body.kind == CredentialKind.apprise:
        await _check_apprise(session, body.secret)
    c = Credential(
        name=body.name,
        site=body.site,
        kind=body.kind,
        secret_enc=box.encrypt(body.secret.encode()),
        owner_id=p.user_id,
        visibility=body.visibility,
    )
    session.add(c)
    await session.flush()
    return CredentialOut.of(c, True, True)


@router.get("/{obj_id}", response_model=CredentialOut)
async def get_credential(
    obj_id: int,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> CredentialOut:
    require_scope(p, "credentials:read")
    c: Credential = await get_obj(session, Credential, obj_id, p)
    return CredentialOut.of(c, await can_edit(session, c, p), await can_use(session, c, p))


@router.patch("/{obj_id}", response_model=CredentialOut)
async def patch_credential(
    obj_id: int,
    body: CredentialPatch,
    p: Principal = Depends(current_principal),
    box: SecretBox = Depends(secret_box),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> CredentialOut:
    require_scope(p, "credentials:write")
    c: Credential = await get_obj(session, Credential, obj_id, p, Perm.edit)
    data = body.model_dump(exclude_unset=True, exclude_none=True)
    if data.get("kind", c.kind) == CredentialKind.apprise and ("secret" in data or "kind" in data):
        await _check_apprise(session, data.get("secret") or box.decrypt(c.secret_enc).decode())
    if "secret" in data:
        c.secret_enc = box.encrypt(data.pop("secret").encode())
    for k, v in data.items():
        setattr(c, k, v)
    await session.flush()
    return CredentialOut.of(c, True, True)


@router.delete("/{obj_id}", status_code=204)
async def delete_credential(
    obj_id: int,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> Response:
    require_scope(p, "credentials:write")
    c: Credential = await get_obj(session, Credential, obj_id, p)
    await require_owner_or_admin(session, c, p)
    used = await session.execute(select(Source.id).where(Source.credential_id == obj_id).limit(1))
    if used.first() is not None:
        raise HTTPException(409, "in use")
    await delete_shares(session, Credential.share_type, obj_id)
    await session.delete(c)
    await session.flush()
    return Response(status_code=204)


router.include_router(shares_router(Credential, "credentials"))
