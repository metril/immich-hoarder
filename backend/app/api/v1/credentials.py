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
from app.db.models import Credential, CredentialKind, Perm, Source
from app.rip.settings import load_rip_settings
from app.runtime.notify import check_notify_url
from app.runtime.settings import _apprise_ok
from app.schemas.credentials import CredentialIn, CredentialOut, CredentialPatch

router = APIRouter(prefix="/credentials", tags=["credentials"])


async def _check_apprise(session: AsyncSession, url: str) -> None:
    """Reject invalid or SSRF-prone apprise URLs without echoing them."""
    try:
        check_notify_url(url, allow_private=(await load_rip_settings(session)).allow_private_hosts)
        if not _apprise_ok(url):
            raise ValueError("invalid notification url")
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


@router.get("", response_model=Page[CredentialOut])
async def list_credentials(
    cursor: str | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> Page[CredentialOut]:
    require_scope(p, "credentials:read")
    rows, nxt = await paginate(
        session, visible_to(select(Credential), Credential, p), cursor, limit
    )
    return Page(items=[CredentialOut.of(r) for r in rows], next_cursor=nxt)


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
    return CredentialOut.of(c)


@router.get("/{obj_id}", response_model=CredentialOut)
async def get_credential(
    obj_id: int,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> CredentialOut:
    require_scope(p, "credentials:read")
    return CredentialOut.of(await get_obj(session, Credential, obj_id, p))


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
    return CredentialOut.of(c)


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
