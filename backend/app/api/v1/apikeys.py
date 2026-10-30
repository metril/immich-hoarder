from collections.abc import Sequence

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page, paginate
from app.auth.apikeys import _naive, _now, create_api_key
from app.auth.authz import require_scope
from app.auth.deps import current_principal
from app.auth.principal import Principal
from app.db.engine import get_session
from app.db.models import ApiKey, User
from app.schemas.apikeys import ApiKeyCreated, ApiKeyIn, ApiKeyOut, ApiKeyPatch

router = APIRouter(prefix="/api-keys", tags=["api-keys"])

_R401 = {"description": "Missing or invalid credentials"}
_R403 = {"description": "Missing scope, or scopes cannot be granted by the caller"}
_R404 = {"description": "Key not found, or owned by another user"}
_R409 = {"description": "Key is revoked or expired"}
_R422 = {"description": "Validation error"}


def _out(k: ApiKey) -> ApiKeyOut:
    return ApiKeyOut(
        id=k.id, name=k.name, prefix=k.prefix, scopes=list(k.scopes or []), expires_at=k.expires_at
    )


def _check_grantable(p: Principal, scopes: Sequence[str]) -> None:
    if "admin" in scopes and not p.is_admin:
        raise HTTPException(403, "admin scope requires an admin")
    if p.scopes is not None and not p.is_admin and not set(scopes) <= p.scopes:
        raise HTTPException(403, "cannot grant scopes beyond the calling key")


async def _owned(
    session: AsyncSession, p: Principal, key_id: int, *, owner_only: bool = False
) -> ApiKey:
    key = await session.get(ApiKey, key_id)
    if key is None or (key.user_id != p.user_id and (owner_only or not p.is_admin)):
        raise HTTPException(404, "not found")
    return key


def _require_live(key: ApiKey) -> None:
    if key.revoked:
        raise HTTPException(409, "key is revoked")
    if key.expires_at is not None and _naive(key.expires_at) <= _now():
        raise HTTPException(409, "key is expired")


@router.get(
    "",
    response_model=Page[ApiKeyOut],
    summary="List API keys",
    description="Lists active keys (all for admins, own otherwise). Requires `keys:read`.",
    responses={401: _R401, 403: _R403, 422: _R422},
)
async def list_keys(
    cursor: str | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> Page[ApiKeyOut]:
    require_scope(p, "keys:read")
    stmt = select(ApiKey).where(ApiKey.revoked.is_(False))
    if not p.is_admin:
        stmt = stmt.where(ApiKey.user_id == p.user_id)
    rows, nxt = await paginate(session, stmt, cursor, limit)
    return Page(items=[_out(k) for k in rows], next_cursor=nxt)


@router.post(
    "",
    response_model=ApiKeyCreated,
    status_code=201,
    summary="Create an API key",
    description="Creates a key for the caller. The plaintext key is returned once. "
    "Requires `keys:write`; granted scopes may not exceed the caller's own.",
    responses={401: _R401, 403: _R403, 422: _R422},
)
async def create_key(
    body: ApiKeyIn,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> ApiKeyCreated:
    require_scope(p, "keys:write")
    scopes = sorted(set(body.scopes))
    _check_grantable(p, scopes)
    user = await session.get(User, p.user_id)
    assert user is not None
    key, raw = await create_api_key(session, user, body.name, scopes, body.expires_at)
    return ApiKeyCreated(**_out(key).model_dump(), key=raw)


@router.get(
    "/{key_id}",
    response_model=ApiKeyOut,
    summary="Get an API key",
    description="Returns one key's metadata (never the secret). Requires `keys:read`. "
    "Non-admins can only see their own keys.",
    responses={401: _R401, 403: _R403, 404: _R404, 422: _R422},
)
async def get_key(
    key_id: int,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> ApiKeyOut:
    require_scope(p, "keys:read")
    return _out(await _owned(session, p, key_id))


@router.patch(
    "/{key_id}",
    response_model=ApiKeyOut,
    summary="Edit an API key",
    description="Renames a key and/or replaces its scopes. Requires `keys:write`; "
    "scopes may not exceed the caller's own. Admins may edit any key. "
    "Revoked or expired keys cannot be edited.",
    responses={401: _R401, 403: _R403, 404: _R404, 409: _R409, 422: _R422},
)
async def update_key(
    key_id: int,
    body: ApiKeyPatch,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> ApiKeyOut:
    require_scope(p, "keys:write")
    key = await _owned(session, p, key_id)
    _require_live(key)
    if body.name is not None:
        key.name = body.name
    if body.scopes is not None:
        scopes: list[str] = sorted(set(body.scopes))
        _check_grantable(p, scopes)
        key.scopes = scopes
    await session.flush()
    return _out(key)


@router.post(
    "/{key_id}/rotate",
    response_model=ApiKeyCreated,
    status_code=201,
    summary="Rotate an API key",
    description="Issues a new key with the same name, scopes and expiry, and revokes the old "
    "one atomically. The new plaintext key is returned once. Requires `keys:write`. "
    "Only the key's owner may rotate it (admins get 404). "
    "Revoked or expired keys cannot be rotated.",
    responses={401: _R401, 403: _R403, 404: _R404, 409: _R409, 422: _R422},
)
async def rotate_key(
    key_id: int,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> ApiKeyCreated:
    require_scope(p, "keys:write")
    old = await _owned(session, p, key_id, owner_only=True)
    _require_live(old)
    scopes = list(old.scopes or [])
    _check_grantable(p, scopes)
    owner = await session.get(User, old.user_id)
    assert owner is not None
    new, raw = await create_api_key(session, owner, old.name, scopes, old.expires_at)
    old.revoked = True
    await session.flush()
    return ApiKeyCreated(**_out(new).model_dump(), key=raw)


@router.delete(
    "/{key_id}",
    status_code=204,
    summary="Revoke an API key",
    description="Revokes a key immediately. Requires `keys:write`.",
    responses={401: _R401, 403: _R403, 404: _R404, 422: _R422},
)
async def revoke_key(
    key_id: int,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> Response:
    require_scope(p, "keys:write")
    key = await _owned(session, p, key_id)
    key.revoked = True
    await session.flush()
    return Response(status_code=204)
