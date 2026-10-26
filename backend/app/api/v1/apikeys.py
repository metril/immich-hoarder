from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page, paginate
from app.auth.apikeys import create_api_key
from app.auth.authz import require_scope
from app.auth.deps import current_principal
from app.auth.principal import Principal
from app.db.engine import get_session
from app.db.models import ApiKey, User
from app.schemas.apikeys import ApiKeyCreated, ApiKeyIn, ApiKeyOut

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


def _out(k: ApiKey) -> ApiKeyOut:
    return ApiKeyOut(
        id=k.id, name=k.name, prefix=k.prefix, scopes=list(k.scopes or []), expires_at=k.expires_at
    )


@router.get("", response_model=Page[ApiKeyOut])
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


@router.post("", response_model=ApiKeyCreated, status_code=201)
async def create_key(
    body: ApiKeyIn,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> ApiKeyCreated:
    require_scope(p, "keys:write")
    scopes = sorted(set(body.scopes))
    if "admin" in scopes and not p.is_admin:
        raise HTTPException(403, "admin scope requires an admin")
    if p.scopes is not None and not p.is_admin and not set(scopes) <= p.scopes:
        raise HTTPException(403, "cannot grant scopes beyond the calling key")
    user = await session.get(User, p.user_id)
    assert user is not None
    key, raw = await create_api_key(session, user, body.name, scopes, body.expires_at)
    return ApiKeyCreated(**_out(key).model_dump(), key=raw)


@router.delete("/{key_id}", status_code=204)
async def revoke_key(
    key_id: int,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> Response:
    require_scope(p, "keys:write")
    key = await session.get(ApiKey, key_id)
    if key is None or (key.user_id != p.user_id and not p.is_admin):
        raise HTTPException(404, "not found")
    key.revoked = True
    await session.flush()
    return Response(status_code=204)
