import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import secret_box
from app.api.v1.auth import get_local_admin, has_enabled_admin, save_local_admin
from app.auth.deps import require_admin
from app.auth.local import verify_password
from app.auth.oidc import discover
from app.auth.principal import Principal
from app.auth.settings import (
    AuthSettings,
    OidcStored,
    merge_oidc,
    reload_auth,
    stored_to_api,
)
from app.db.engine import get_session
from app.db.models import Setting
from app.rip.settings import RipSettings
from app.runtime.settings import NotifySettings, RuntimeSettings, load_model
from app.schemas.auth import LocalPasswordIn, OidcTestIn, OidcTestOut
from app.schemas.settings import SettingsDoc

log = logging.getLogger(__name__)
router = APIRouter(prefix="/settings", tags=["settings"])


_MODELS: dict[str, type[BaseModel]] = {
    "rip": RipSettings,
    "runtime": RuntimeSettings,
    "notify": NotifySettings,
    "auth": AuthSettings,
}


async def _all(session: AsyncSession) -> SettingsDoc:
    rows: dict[str, Any] = {
        s.key: s.value for s in (await session.execute(select(Setting))).scalars()
    }
    ok: dict[str, Any] = {}
    for k, model in _MODELS.items():
        if k not in rows:
            continue
        try:
            model.model_validate(rows[k])
        except ValidationError:
            log.warning("invalid %s settings stored; omitted", k)  # detail may echo secrets
            continue
        ok[k] = rows[k]
    if "oidc" in rows:
        try:
            # client_secret stays unset so it is never serialised back
            ok["oidc"] = stored_to_api(OidcStored.model_validate(rows["oidc"])).model_dump(
                exclude={"client_secret"}
            )
        except ValidationError:
            log.warning("invalid oidc settings stored; omitted")
    return SettingsDoc.model_validate(ok)


@router.get("", response_model=SettingsDoc, response_model_exclude_unset=True)
async def get_settings(
    _p: Principal = Depends(require_admin),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> SettingsDoc:
    return await _all(session)


@router.put("", response_model=SettingsDoc, response_model_exclude_unset=True)
async def put_settings(
    body: SettingsDoc,
    request: Request,
    _p: Principal = Depends(require_admin),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> SettingsDoc:
    # only keys present in the request are written; a null value is ignored
    changed = {
        k: v for k, v in body.model_dump(mode="json", exclude_unset=True).items() if v is not None
    }
    await _prepare_auth(body, changed, request, session)
    for k, v in changed.items():
        row = await session.get(Setting, k)
        if row is None:
            session.add(Setting(key=k, value=v))
        else:
            row.value = v
    await session.flush()
    await session.commit()
    if "oidc" in changed or "auth" in changed:
        await reload_auth(request.app, session)
    sched = getattr(request.app.state, "scheduler", None)
    if sched is not None and "runtime" in changed:
        try:
            await sched.sync_maintenance()
        except Exception as e:
            log.error("maintenance reschedule failed: %s", type(e).__name__)
    return await _all(session)


async def _prepare_auth(
    body: SettingsDoc, changed: dict[str, Any], request: Request, session: AsyncSession
) -> None:
    """Validate and rewrite the oidc/auth keys in ``changed`` (encrypts the client secret)."""
    old = await load_model(session, "oidc", OidcStored)
    stored = old
    if body.oidc is not None:
        stored = merge_oidc(body.oidc, old, secret_box(request))
        if stored.enabled and not (stored.issuer and stored.client_id and stored.client_secret_enc):
            raise HTTPException(422, "OIDC needs an issuer, client ID and client secret")
        changed["oidc"] = stored.model_dump()
    auth = await load_model(session, "auth", AuthSettings)
    if body.auth is not None:
        auth = body.auth
    if request.app.state.settings.break_glass:
        return
    if body.auth is not None and not auth.local_enabled:
        if not (stored.enabled and stored.issuer):
            raise HTTPException(422, "enable OIDC before disabling local accounts")
        try:
            await discover(stored.issuer)
        except ValueError as e:
            raise HTTPException(422, f"OIDC test failed: {e}") from None
    elif body.oidc is not None and not stored.enabled and not auth.local_enabled:
        raise HTTPException(422, "re-enable local accounts before disabling OIDC")
    if (
        body.oidc is not None
        and not stored.enabled
        and not await has_enabled_admin(session, local_only=True)
    ):
        raise HTTPException(422, "create a local admin before disabling OIDC")


@router.post("/oidc/test", response_model=OidcTestOut)
async def test_oidc(
    body: OidcTestIn,
    _p: Principal = Depends(require_admin),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> OidcTestOut:
    issuer = (body.issuer or "").strip() or (await load_model(session, "oidc", OidcStored)).issuer
    if not issuer:
        return OidcTestOut(ok=False, error="no issuer configured")
    if not issuer.startswith(("http://", "https://")):
        return OidcTestOut(ok=False, error="issuer must be an http(s) URL")
    try:
        await discover(issuer)
    except ValueError as e:
        return OidcTestOut(ok=False, error=str(e))
    return OidcTestOut(ok=True)


@router.put("/local-admin", status_code=204)
async def set_local_admin_password(
    body: LocalPasswordIn,
    request: Request,
    _p: Principal = Depends(require_admin),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> Response:
    """Change the local admin password (current password required), or create the account."""
    existing = await get_local_admin(session)
    if existing is not None:
        ok = body.current_password is not None and await asyncio.to_thread(
            verify_password, body.current_password, existing["password_hash"]
        )
        if not ok:
            raise HTTPException(403, "current password is incorrect")
        username = existing["username"]
    else:
        username = body.username or "admin"
    user = await save_local_admin(session, username, body.new_password)
    await session.commit()
    if request.session.get("user_id") is not None:  # keep the caller signed in
        request.session["user_id"] = user.id
        request.session["sg"] = user.session_gen
    return Response(status_code=204)
