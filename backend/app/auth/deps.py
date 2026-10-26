import hmac

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.apikeys import verify_api_key
from app.auth.oidc import BearerVerifier, TokenError
from app.auth.principal import Principal, resolve_role, upsert_user
from app.core.config import Settings
from app.db.engine import get_session
from app.db.models import Role, User

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_COOKIE = "ih_csrf"
CSRF_HEADER = "X-CSRF-Token"


def _unauth(detail: str = "unauthorized") -> HTTPException:
    return HTTPException(401, detail, headers={"WWW-Authenticate": "Bearer"})


def _principal(user: User, settings: Settings, scopes: frozenset[str] | None) -> Principal:
    if user.disabled or resolve_role(user.groups, settings) is None:
        raise _unauth()
    return Principal(user.id, user.role, frozenset(user.groups or []), scopes)


def check_csrf(request: Request) -> None:
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get(CSRF_HEADER, "")
    if not cookie or not hmac.compare_digest(cookie.encode(), header.encode()):
        raise HTTPException(403, "CSRF token missing or invalid")


async def current_principal(
    request: Request, session: AsyncSession = Depends(get_session)
) -> Principal:
    settings: Settings = request.app.state.settings

    raw_key = request.headers.get("X-API-Key")
    auth = request.headers.get("Authorization", "")
    if not raw_key and auth.lower().startswith("bearer ") and auth[7:].strip().startswith("ih_"):
        raw_key = auth[7:].strip()  # API key presented as a bearer token; never tried as a JWT
    if raw_key:
        key = await verify_api_key(session, raw_key)
        user = await session.get(User, key.user_id) if key else None
        if key is None or user is None:
            raise _unauth()
        p = _principal(user, settings, frozenset(key.scopes or []))
        if p.role != Role.admin:  # cap scopes at the user's current role
            p = Principal(p.user_id, p.role, p.groups, p.scopes and p.scopes - {"admin"})
        return p

    if auth.lower().startswith("bearer "):
        verifier: BearerVerifier = request.app.state.verifier
        try:
            claims = await verifier.verify(auth[7:].strip())
        except TokenError:
            raise _unauth() from None
        user = await upsert_user(session, claims, settings)
        await session.commit()  # persist group changes even if access is denied below
        return _principal(user, settings, None)

    uid = request.session.get("user_id")
    if uid is not None:
        user = await session.get(User, uid)
        if user is None:
            raise _unauth()
        p = _principal(user, settings, None)
        if request.method in UNSAFE:
            check_csrf(request)
        return p
    raise _unauth()


async def require_admin(p: Principal = Depends(current_principal)) -> Principal:
    if not p.is_admin:
        raise HTTPException(403, "admin required")
    return p
