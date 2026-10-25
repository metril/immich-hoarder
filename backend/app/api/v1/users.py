from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page, paginate
from app.auth.deps import require_admin
from app.auth.principal import Principal
from app.db.engine import get_session
from app.db.models import Role, User
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
    if body.disabled and u.role == Role.admin and not u.disabled:
        others = await session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == Role.admin, User.disabled.is_(False), User.id != u.id)
        )
        if not others:
            raise HTTPException(409, "last admin")
    if body.disabled is not None:
        u.disabled = body.disabled
    await session.flush()
    return UserOut.model_validate(u)
