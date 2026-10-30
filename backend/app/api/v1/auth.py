import asyncio
import hmac
import secrets
from typing import Any

from authlib.integrations.base_client import OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import (
    CSRF_COOKIE,
    SESSION_MAX_AGE,
    check_csrf,
    current_principal,
    local_login_allowed,
)
from app.auth.local import LoginLimiter, hash_password, verify_password
from app.auth.oidc import OidcConfig
from app.auth.principal import LOCAL_PREFIX, Principal, resolve_role, upsert_user
from app.db.engine import get_session
from app.db.models import Role, Setting, User
from app.schemas.auth import AuthStatus, LocalCredentials, MeOut, SelfPasswordIn, SetupIn

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _client(request: Request) -> Any:
    oauth = request.app.state.oauth
    if oauth is None:
        raise HTTPException(503, "OIDC is not configured")
    return oauth.oidc


def _redirect_uri(request: Request) -> str:
    base = request.app.state.auth_cfg.public_url or str(request.base_url)
    return f"{base.rstrip('/')}/api/v1/auth/callback"


def _set_csrf(request: Request, resp: Response) -> None:
    resp.set_cookie(
        CSRF_COOKIE,
        secrets.token_urlsafe(32),
        max_age=SESSION_MAX_AGE,
        httponly=False,
        samesite="lax",
        secure=request.url.scheme == "https",
    )


async def get_local_admin(session: AsyncSession) -> dict[str, str] | None:
    row = await session.get(Setting, "local_admin")
    v = row.value if row is not None else None
    if isinstance(v, dict) and v.get("username") and v.get("password_hash"):
        return v
    return None


async def sync_local_admin_setting(session: AsyncSession, u: User) -> None:
    """Keep the legacy local_admin setting row's hash in step when u is that account."""
    row = await session.get(Setting, "local_admin")
    if (
        row is not None
        and isinstance(row.value, dict)
        and u.sub == f"{LOCAL_PREFIX}{row.value.get('username')}"
    ):
        row.value = {**row.value, "password_hash": u.password_hash}


async def _has_local_login(session: AsyncSession) -> bool:
    if await get_local_admin(session) is not None:
        return True
    q = select(User.id).where(User.sub.like(f"{LOCAL_PREFIX}%"), User.password_hash.is_not(None))
    return (await session.execute(q.limit(1))).first() is not None


async def has_enabled_admin(session: AsyncSession, *, local_only: bool = False) -> bool:
    q = select(User.id).where(User.role == Role.admin, User.disabled.is_(False))
    if local_only:
        q = q.where(User.sub.like(f"{LOCAL_PREFIX}%"))
    return (await session.execute(q.limit(1))).first() is not None


async def save_local_admin(session: AsyncSession, username: str, password: str) -> User:
    """Create/replace the local admin credentials and its user row.

    Bumps the session generation (revoking existing sessions) and disables the
    previous local row when the username changes.
    """
    prev = await get_local_admin(session)
    value = {
        "username": username,
        "password_hash": await asyncio.to_thread(hash_password, password),
    }
    row = await session.get(Setting, "local_admin")
    if row is None:
        session.add(Setting(key="local_admin", value=value))
    else:
        row.value = value
    if prev is not None and prev["username"] != username:
        old = (
            await session.execute(
                select(User).where(User.sub == f"{LOCAL_PREFIX}{prev['username']}")
            )
        ).scalar_one_or_none()
        if old is not None:
            old.disabled = True
            old.session_gen += 1
    sub = f"{LOCAL_PREFIX}{username}"
    user = (await session.execute(select(User).where(User.sub == sub))).scalar_one_or_none()
    if user is None:
        user = User(sub=sub, role=Role.admin, groups=[], name=username)
        session.add(user)
    else:
        user.session_gen += 1
    user.password_hash = value["password_hash"]  # the setting row is kept in step (fallback)
    user.must_change_password = False
    user.role = Role.admin
    user.disabled = False
    await session.flush()
    return user


def _login(request: Request, user: User) -> Response:
    request.session.clear()
    request.session["user_id"] = user.id
    request.session["sg"] = user.session_gen
    resp = Response(
        MeOut(
            id=user.id,
            email=user.email,
            name=user.name,
            role=user.role,
            groups=[],
            must_change_password=user.must_change_password,
        ).model_dump_json(),
        media_type="application/json",
    )
    _set_csrf(request, resp)
    return resp


@router.get("/status", response_model=AuthStatus)
async def status(
    request: Request, session: AsyncSession = Depends(get_session, scope="function")
) -> AuthStatus:
    app = request.app
    return AuthStatus(
        setup_required=await _setup_open(request, session),
        oidc_enabled=app.state.oidc_cfg.active,
        local_login_enabled=local_login_allowed(app) and await _has_local_login(session),
        break_glass=app.state.settings.break_glass,
        reset_token_required=_reset_mode(request),
    )


def _reset_mode(request: Request) -> bool:
    """Break-glass reset is armed (a one-time token was issued and is still unused)."""
    s = request.app.state.settings
    return bool(s.break_glass and s.break_glass_reset and request.app.state.reset_token)


async def _setup_open(request: Request, session: AsyncSession) -> bool:
    """Normal first-run setup (reset mode is gated separately by the token)."""
    s, cfg = request.app.state.settings, request.app.state.oidc_cfg
    if s.break_glass:
        return await get_local_admin(session) is None
    return not cfg.active and not await has_enabled_admin(session)


@router.post("/setup", response_model=MeOut)
async def setup(
    body: SetupIn,
    request: Request,
    session: AsyncSession = Depends(get_session, scope="function"),
) -> Response:
    app = request.app
    async with app.state.setup_lock:
        if _reset_mode(request):
            tok = app.state.reset_token
            if not (
                body.reset_token and hmac.compare_digest(body.reset_token.encode(), tok.encode())
            ):
                raise HTTPException(403, "invalid reset token")
        elif not await _setup_open(request, session):
            raise HTTPException(409, "already set up")
        user = await save_local_admin(session, body.username, body.password)
        await session.commit()
        if _reset_mode(request):
            app.state.reset_token = None  # one use per process
    return _login(request, user)


@router.post("/local/login", response_model=MeOut)
async def local_login(
    body: LocalCredentials,
    request: Request,
    session: AsyncSession = Depends(get_session, scope="function"),
) -> Response:
    if not local_login_allowed(request.app):
        raise HTTPException(404, "not found")
    limiter: LoginLimiter = request.app.state.login_limiter
    key = request.client.host if request.client else "-"
    if wait := limiter.retry_after(key):
        raise HTTPException(429, "too many attempts", headers={"Retry-After": str(wait)})
    user = (
        await session.execute(select(User).where(User.sub == f"{LOCAL_PREFIX}{body.username}"))
    ).scalar_one_or_none()
    stored = user.password_hash if user is not None else None
    if user is not None and stored is None:  # not migrated yet: the setting row still holds it
        admin = await get_local_admin(session)
        if admin is not None and secrets.compare_digest(
            admin["username"].encode(), body.username.encode()
        ):
            stored = admin["password_hash"]
    # always one scrypt run (dummy hash for unknown users) so timing doesn't reveal usernames
    ok = await asyncio.to_thread(verify_password, body.password, stored)
    if not ok or user is None or user.disabled:
        limiter.failed(key)
        raise HTTPException(401, "invalid credentials")
    limiter.succeeded(key)
    return _login(request, user)


@router.get("/login")
@router.head("/login", include_in_schema=False)
async def login(request: Request) -> Response:
    if request.method == "HEAD":  # availability probe; never starts an auth flow
        _client(request)
        return Response(status_code=204)
    resp: Response = await _client(request).authorize_redirect(request, _redirect_uri(request))
    return resp


@router.get("/callback")
async def callback(
    request: Request, session: AsyncSession = Depends(get_session, scope="function")
) -> Response:
    cfg: OidcConfig = request.app.state.oidc_cfg
    try:
        token = await _client(request).authorize_access_token(request)
    except OAuthError:
        raise HTTPException(401, "login failed") from None
    claims = token.get("userinfo")
    if not claims or "sub" not in claims:
        raise HTTPException(401, "login failed")
    user = await upsert_user(session, claims, cfg)
    await session.commit()  # persist group changes even if login is denied
    if user.disabled or resolve_role(user.groups, cfg) is None:
        request.session.clear()
        raise HTTPException(403, "access denied")
    request.session.clear()
    request.session["user_id"] = user.id
    request.session["sg"] = user.session_gen
    resp = RedirectResponse("/", status_code=303)
    _set_csrf(request, resp)
    return resp


@router.post("/logout", status_code=204)
async def logout(request: Request) -> Response:
    if request.session.get("user_id") is not None:
        check_csrf(request)
    request.session.clear()
    resp = Response(status_code=204)
    resp.delete_cookie(CSRF_COOKIE)
    return resp


@router.get("/me", response_model=MeOut)
async def me(
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> MeOut:
    user = await session.get(User, p.user_id)
    assert user is not None
    return MeOut(
        id=user.id,
        email=user.email,
        name=user.name,
        role=p.role,
        groups=sorted(p.groups),
        must_change_password=user.must_change_password,
    )


@router.post(
    "/password",
    response_model=MeOut,
    summary="Change your own password",
    description="Changes the signed-in local user's password (current password required), "
    "clears the must-change flag and revokes other sessions; the caller stays signed in.",
    responses={
        401: {"description": "Not signed in"},
        403: {"description": "Current password is incorrect, or the account is not local"},
        422: {"description": "Validation error"},
    },
)
async def change_own_password(
    body: SelfPasswordIn,
    request: Request,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> MeOut:
    user = await session.get(User, p.user_id)
    assert user is not None
    stored = user.password_hash
    if stored is None:
        admin = await get_local_admin(session)
        if admin is not None and user.sub == f"{LOCAL_PREFIX}{admin['username']}":
            stored = admin["password_hash"]
    if not user.sub.startswith(LOCAL_PREFIX) or not await asyncio.to_thread(
        verify_password, body.current_password, stored
    ):
        raise HTTPException(403, "current password is incorrect")
    user.password_hash = await asyncio.to_thread(hash_password, body.new_password)
    user.must_change_password = False
    user.session_gen += 1
    await sync_local_admin_setting(session, user)
    await session.commit()
    if request.session.get("user_id") is not None:
        request.session["sg"] = user.session_gen
    return MeOut(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        groups=sorted(p.groups),
        must_change_password=False,
    )
