from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page, paginate
from app.auth.deps import require_admin
from app.auth.principal import Principal
from app.db.engine import get_session
from app.db.models import User
from app.schemas.users import UserOut, UserPatch

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=Page[UserOut])
async def list_users(
    cursor: str | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    _p: Principal = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Page[UserOut]:
    rows, nxt = await paginate(session, select(User), cursor, limit)
    return Page(items=[UserOut.model_validate(r) for r in rows], next_cursor=nxt)


@router.patch("/{user_id}", response_model=UserOut)
async def patch_user(
    user_id: int,
    body: UserPatch,
    _p: Principal = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> UserOut:
    u = await session.get(User, user_id)
    if u is None:
        raise HTTPException(404, "not found")
    for k, v in body.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(u, k, v)
    await session.flush()
    return UserOut.model_validate(u)
