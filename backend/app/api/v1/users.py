from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page, paginate
from app.auth.deps import current_principal, require_admin
from app.auth.principal import Principal
from app.db.engine import get_session
from app.db.models import Role, User
from app.schemas.users import UserOut, UserPatch, UserRef

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


DIRECTORY_LIMIT = 20


@router.get("/directory", response_model=list[UserRef])
async def user_directory(
    q: str = Query(min_length=2, max_length=100),
    _p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> list[UserRef]:
    """Minimal id/name lookup (name substring or exact email); any authenticated user."""
    term = q.strip()
    if len(term) < 2:
        raise HTTPException(422, "q must be at least 2 characters")
    rows = (
        await session.scalars(
            select(User)
            .where(
                User.disabled.is_(False),
                or_(
                    User.name.icontains(term, autoescape=True),
                    func.lower(User.email) == term.lower(),
                ),
            )
            .order_by(func.lower(User.name).nulls_last(), User.id)
            .limit(DIRECTORY_LIMIT)
        )
    ).all()
    return [UserRef(id=u.id, name=u.name) for u in rows]


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
