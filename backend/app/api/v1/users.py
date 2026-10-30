from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.pagination import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    Q_DESCRIPTION,
    SORT_DESCRIPTION,
    Page,
    apply_q,
    paginate,
)
from app.auth.deps import current_principal, require_admin_scope
from app.auth.principal import Principal
from app.db.engine import get_session
from app.db.models import Role, User
from app.schemas.users import UserOut, UserPatch, UserRef

router = APIRouter(prefix="/users", tags=["users"])

_R401 = {"description": "Missing or invalid credentials"}
_R403 = {"description": "Caller is not an admin, or lacks the required admin scope"}
_R404 = {"description": "User not found"}
_R409 = {"description": "Would disable the last enabled admin"}
_R422 = {"description": "Validation error"}
_READ = Depends(require_admin_scope("users:read"))
_WRITE = Depends(require_admin_scope("users:write"))
_R400 = {"description": "Cursor was issued for a different sort"}
UserSort = Literal["id", "-id", "sub", "-sub", "created_at", "-created_at"]


@router.get(
    "",
    response_model=Page[UserOut],
    summary="List users",
    description="Keyset-paginated user list. Requires an admin with the `users:read` or "
    "`admin` scope. `q` matches sub, name and email.",
    responses={400: _R400, 401: _R401, 403: _R403, 422: _R422},
)
async def list_users(
    cursor: str | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    q: Annotated[str | None, Query(max_length=100, description=Q_DESCRIPTION)] = None,
    sort: Annotated[UserSort | None, Query(description=SORT_DESCRIPTION)] = None,
    _p: Principal = _READ,
    session: AsyncSession = Depends(get_session, scope="function"),
) -> Page[UserOut]:
    stmt = apply_q(select(User), q, User.sub, User.name, User.email)
    cols = {"sub": User.sub, "created_at": User.created_at}
    rows, nxt = await paginate(session, stmt, cursor, limit, sort=sort, sort_cols=cols)
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


@router.patch(
    "/{user_id}",
    response_model=UserOut,
    summary="Update a user",
    description="Enables or disables a user. Requires an admin with the `users:write` or "
    "`admin` scope. The last enabled admin cannot be disabled.",
    responses={401: _R401, 403: _R403, 404: _R404, 409: _R409, 422: _R422},
)
async def patch_user(
    user_id: int,
    body: UserPatch,
    _p: Principal = _WRITE,
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
