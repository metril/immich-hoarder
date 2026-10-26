from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
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
    session: AsyncSession = Depends(get_session, scope="function"),
) -> Page[UserOut]:
    rows, nxt = await paginate(session, select(User), cursor, limit)
    return Page(items=[UserOut.model_validate(r) for r in rows], next_cursor=nxt)


@router.patch("/{user_id}", response_model=UserOut)
async def patch_user(
    user_id: int,
    body: UserPatch,
    _p: Principal = Depends(require_admin),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> UserOut:
    u = await session.get(User, user_id)
    if u is None:
        raise HTTPException(404, "not found")
    if body.disabled and u.role == Role.admin and not u.disabled:
        # Lock the enabled admin rows so the check and the update are one atomic step on
        # Postgres (FOR UPDATE); SQLite serialises writers, and omits the clause.
        enabled = (
            await session.scalars(
                select(User.id)
                .where(User.role == Role.admin, User.disabled.is_(False))
                .with_for_update()
            )
        ).all()
        if not [i for i in enabled if i != u.id]:
            raise HTTPException(409, "last admin")
    if body.disabled is not None:
        u.disabled = body.disabled
    await session.flush()
    return UserOut.model_validate(u)
