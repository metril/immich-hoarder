import secrets
from typing import Any

from authlib.integrations.base_client import OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CSRF_COOKIE, SESSION_MAX_AGE, check_csrf, current_principal
from app.auth.principal import Principal, resolve_role, upsert_user
from app.core.config import Settings
from app.db.engine import get_session
from app.db.models import User
from app.schemas.auth import MeOut

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _client(request: Request) -> Any:
    oauth = request.app.state.oauth
    if oauth is None:
        raise HTTPException(503, "OIDC is not configured")
    return oauth.oidc


def _redirect_uri(settings: Settings) -> str:
    return f"{settings.public_url.rstrip('/')}/api/v1/auth/callback"


@router.get("/login")
@router.head("/login", include_in_schema=False)
async def login(request: Request) -> Response:
    settings: Settings = request.app.state.settings
    if request.method == "HEAD":  # availability probe; never starts an auth flow
        _client(request)
        return Response(status_code=204)
    resp: Response = await _client(request).authorize_redirect(request, _redirect_uri(settings))
    return resp


@router.get("/callback")
async def callback(
    request: Request, session: AsyncSession = Depends(get_session, scope="function")
) -> Response:
    settings: Settings = request.app.state.settings
    try:
        token = await _client(request).authorize_access_token(request)
    except OAuthError:
        raise HTTPException(401, "login failed") from None
    claims = token.get("userinfo")
    if not claims or "sub" not in claims:
        raise HTTPException(401, "login failed")
    user = await upsert_user(session, claims, settings)
    await session.commit()  # persist group changes even if login is denied
    if user.disabled or resolve_role(user.groups, settings) is None:
        request.session.clear()
        raise HTTPException(403, "access denied")
    request.session.clear()
    request.session["user_id"] = user.id
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(
        CSRF_COOKIE,
        secrets.token_urlsafe(32),
        max_age=SESSION_MAX_AGE,
        httponly=False,
        samesite="lax",
        secure=settings.public_url.startswith("https"),
    )
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
    return MeOut(id=user.id, email=user.email, name=user.name, role=p.role, groups=sorted(p.groups))
