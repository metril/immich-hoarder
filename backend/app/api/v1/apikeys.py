from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.apikeys import create_api_key
from app.auth.deps import current_principal
from app.auth.principal import SCOPES, Principal
from app.db.engine import get_session
from app.db.models import ApiKey, User
from app.schemas.apikeys import ApiKeyCreated, ApiKeyIn, ApiKeyOut

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


def _out(k: ApiKey) -> ApiKeyOut:
    return ApiKeyOut(
        id=k.id, name=k.name, prefix=k.prefix, scopes=list(k.scopes or []), expires_at=k.expires_at
    )


@router.get("", response_model=list[ApiKeyOut])
async def list_keys(
    p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
) -> list[ApiKeyOut]:
    stmt = select(ApiKey).where(ApiKey.revoked.is_(False)).order_by(ApiKey.id)
    if not p.is_admin:
        stmt = stmt.where(ApiKey.user_id == p.user_id)
    return [_out(k) for k in (await session.execute(stmt)).scalars()]


@router.post("", response_model=ApiKeyCreated, status_code=201)
async def create_key(
    body: ApiKeyIn,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session),
) -> ApiKeyCreated:
    scopes = sorted(set(body.scopes))
    if bad := set(scopes) - SCOPES:
        raise HTTPException(422, f"unknown scopes: {sorted(bad)}")
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
    session: AsyncSession = Depends(get_session),
) -> Response:
    key = await session.get(ApiKey, key_id)
    if key is None or (key.user_id != p.user_id and not p.is_admin):
        raise HTTPException(404, "not found")
    key.revoked = True
    await session.flush()
    return Response(status_code=204)
