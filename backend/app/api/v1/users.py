import asyncio
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from sqlalchemy import delete, func, or_, select, update
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
from app.api.v1.auth import sync_local_admin_setting
from app.auth.deps import current_principal, require_admin_scope
from app.auth.local import hash_password
from app.auth.principal import LOCAL_PREFIX, Principal
from app.db.engine import get_session
from app.db.models import (
    ApiKey,
    Credential,
    ImmichTarget,
    PrincipalType,
    Role,
    Share,
    Source,
    User,
)
from app.schemas.users import (
    LocalUserCreate,
    OwnedCounts,
    PasswordReset,
    UserInUse,
    UserOut,
    UserPatch,
    UserRef,
)

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


async def _ensure_other_admin(session: AsyncSession, u: User) -> None:
    """409 unless another enabled admin exists.

    Locks the enabled admin rows so the check and the change are one atomic step on
    Postgres (FOR UPDATE); SQLite serialises writers, and omits the clause.
    """
    enabled = (
        await session.scalars(
            select(User.id)
            .where(User.role == Role.admin, User.disabled.is_(False))
            .with_for_update()
        )
    ).all()
    if not [i for i in enabled if i != u.id]:
        raise HTTPException(409, "last admin")


def _local(u: User | None) -> User:
    if u is None:
        raise HTTPException(404, "not found")
    if not u.sub.startswith(LOCAL_PREFIX):
        raise HTTPException(409, "not a local user")
    return u


@router.post(
    "/local",
    status_code=201,
    response_model=UserOut,
    summary="Create a local user",
    description="Creates a local (password) account. Requires an admin with the `users:write` "
    "or `admin` scope. 409 when the username is already taken.",
    responses={
        401: _R401,
        403: _R403,
        409: {"description": "A user with that username already exists"},
        422: _R422,
    },
)
async def create_local_user(
    body: LocalUserCreate,
    _p: Principal = _WRITE,
    session: AsyncSession = Depends(get_session, scope="function"),
) -> UserOut:
    sub = f"{LOCAL_PREFIX}{body.username}"
    if (await session.scalars(select(User.id).where(User.sub == sub))).first() is not None:
        raise HTTPException(409, "user already exists")
    u = User(
        sub=sub,
        name=body.username,
        role=body.role,
        groups=[],
        password_hash=await asyncio.to_thread(hash_password, body.password),
        must_change_password=body.must_change_password,
    )
    session.add(u)
    await session.flush()
    return UserOut.model_validate(u)


@router.post(
    "/{user_id}/password",
    response_model=UserOut,
    summary="Reset a local user's password",
    description="Sets a new password for a local user and revokes all of their sessions. "
    "Requires an admin with the `users:write` or `admin` scope. 409 for non-local users.",
    responses={
        401: _R401,
        403: _R403,
        404: _R404,
        409: {"description": "The user is not a local account"},
        422: _R422,
    },
)
async def reset_password(
    user_id: int,
    body: PasswordReset,
    _p: Principal = _WRITE,
    session: AsyncSession = Depends(get_session, scope="function"),
) -> UserOut:
    u = _local(await session.get(User, user_id))
    u.password_hash = await asyncio.to_thread(hash_password, body.new_password)
    u.must_change_password = body.must_change_password
    u.session_gen += 1
    await sync_local_admin_setting(session, u)
    await session.flush()
    return UserOut.model_validate(u)


async def _owned_counts(session: AsyncSession, uid: int) -> OwnedCounts:
    async def n(model: type[ImmichTarget] | type[Credential] | type[Source]) -> int:
        q = select(func.count()).select_from(model).where(model.owner_id == uid)
        return int(await session.scalar(q) or 0)

    return OwnedCounts(
        targets=await n(ImmichTarget), credentials=await n(Credential), sources=await n(Source)
    )


@router.delete(
    "/{user_id}",
    status_code=204,
    summary="Delete a local user",
    description="Deletes a local user and their API keys and shares. Owned targets, credentials "
    "and sources block the delete (409 with counts) unless `reassign_to` names another user, "
    "who then takes them over. The last enabled admin cannot be deleted. Requires an admin "
    "with the `users:write` or `admin` scope.",
    responses={
        401: _R401,
        403: _R403,
        404: _R404,
        409: {
            "model": UserInUse,
            "description": "Last enabled admin, not a local user, or the user still owns "
            "resources (body lists the counts)",
        },
        422: _R422,
    },
)
async def delete_user(
    user_id: int,
    reassign_to: Annotated[
        int | None, Query(description="User id that takes over the owned resources.")
    ] = None,
    _p: Principal = _WRITE,
    session: AsyncSession = Depends(get_session, scope="function"),
) -> Response:
    u = _local(await session.get(User, user_id))
    if u.role == Role.admin and not u.disabled:
        await _ensure_other_admin(session, u)
    counts = await _owned_counts(session, u.id)
    if counts.targets + counts.credentials + counts.sources:
        if reassign_to is None:
            return JSONResponse(
                UserInUse(detail="user owns resources", owned=counts).model_dump(), status_code=409
            )
        if reassign_to == u.id:
            raise HTTPException(422, "cannot reassign to the deleted user")
        dest = await session.get(User, reassign_to)
        if dest is None or dest.disabled:
            raise HTTPException(422, "reassign_to must be an existing enabled user")
        for model in (ImmichTarget, Credential, Source):
            await session.execute(
                update(model).where(model.owner_id == u.id).values(owner_id=dest.id)
            )
    await session.execute(
        delete(Share).where(
            Share.principal_type == PrincipalType.user, Share.principal_id == str(u.id)
        )
    )
    await session.execute(delete(ApiKey).where(ApiKey.user_id == u.id))
    await session.delete(u)
    await session.flush()
    return Response(status_code=204)


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
        await _ensure_other_admin(session, u)
    if body.disabled is not None:
        u.disabled = body.disabled
    await session.flush()
    return UserOut.model_validate(u)
