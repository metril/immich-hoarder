import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from app.api.v1.auth import save_local_admin
from app.auth.local import LoginLimiter, hash_password, verify_password
from app.auth.settings import reload_auth
from app.core.config import Settings
from app.db.engine import session_scope
from app.db.models import Role, Setting, User
from app.main import create_app

API = "/api/v1"
PW = "correct horse battery"


def test_hash_roundtrip_and_salt() -> None:
    h = hash_password(PW)
    assert verify_password(PW, h) and not verify_password("nope", h)
    assert hash_password(PW) != h
    assert not verify_password(PW, None) and not verify_password(PW, "garbage")


def test_limiter_backoff() -> None:
    lim = LoginLimiter()
    for _ in range(LoginLimiter.FREE):
        assert lim.retry_after("a") == 0
        lim.failed("a")
    assert lim.retry_after("a") > 0 and lim.retry_after("b") == 0
    lim.succeeded("a")
    assert lim.retry_after("a") == 0


async def _setup(c: httpx.AsyncClient, user: str = "root") -> httpx.Response:
    return await c.post(f"{API}/auth/setup", json={"username": user, "password": PW})


async def test_status_and_setup_closed_with_oidc(client: httpx.AsyncClient) -> None:
    # OIDC configured by the fixture: setup is closed without break glass
    st = (await client.get(f"{API}/auth/status")).json()
    assert st == {
        "setup_required": False,
        "oidc_enabled": True,
        "local_login_enabled": False,
        "break_glass": False,
        "reset_token_required": False,
    }
    assert (await _setup(client)).status_code == 409


async def test_setup_login_flow(plain: httpx.AsyncClient) -> None:
    c = plain
    assert (await c.get(f"{API}/auth/status")).json()["setup_required"] is True
    r = await _setup(c)
    assert r.status_code == 200 and r.json()["role"] == "admin"
    assert (await c.get(f"{API}/auth/me")).json()["name"] == "root"
    assert (await _setup(c, "second")).status_code == 409  # only once
    st = (await c.get(f"{API}/auth/status")).json()
    assert st["setup_required"] is False and st["local_login_enabled"] is True
    # admin authz works for the local principal
    h = {"X-CSRF-Token": c.cookies["ih_csrf"]}
    assert (await c.get(f"{API}/settings", headers=h)).status_code == 200


async def test_login_success_fail_and_backoff(plain: httpx.AsyncClient) -> None:
    await _setup(plain)
    plain.cookies.clear()
    bad = {"username": "root", "password": "wrong"}
    assert (await plain.post(f"{API}/auth/local/login", json=bad)).status_code == 401
    assert (
        await plain.post(f"{API}/auth/local/login", json={**bad, "username": "x"})
    ).status_code == 401
    ok = await plain.post(f"{API}/auth/local/login", json={"username": "root", "password": PW})
    assert ok.status_code == 200
    plain.cookies.clear()
    for _ in range(LoginLimiter.FREE):
        await plain.post(f"{API}/auth/local/login", json=bad)
    r = await plain.post(f"{API}/auth/local/login", json={"username": "root", "password": PW})
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0


async def _admin(c: httpx.AsyncClient) -> dict[str, str]:
    await _setup(c)
    return {"X-CSRF-Token": c.cookies["ih_csrf"]}


async def test_disable_local_requires_oidc(plain: httpx.AsyncClient) -> None:
    h = await _admin(plain)
    r = await plain.put(f"{API}/settings", json={"auth": {"local_enabled": False}}, headers=h)
    assert r.status_code == 422


async def test_disabled_local_is_404(client: httpx.AsyncClient, app: FastAPI) -> None:
    async with session_scope() as s:
        s.add(Setting(key="auth", value={"public_url": None, "local_enabled": False}))
        await s.flush()
        await reload_auth(app, s)
    r = await client.post(f"{API}/auth/local/login", json={"username": "a", "password": "b"})
    assert r.status_code == 404


async def test_password_change(plain: httpx.AsyncClient) -> None:
    h = await _admin(plain)
    url = f"{API}/settings/local-admin"
    r = await plain.put(
        url, json={"current_password": "bad", "new_password": "new password 1"}, headers=h
    )
    assert r.status_code == 403
    r = await plain.put(
        url, json={"current_password": PW, "new_password": "new password 1"}, headers=h
    )
    assert r.status_code == 204
    plain.cookies.clear()
    assert (
        await plain.post(f"{API}/auth/local/login", json={"username": "root", "password": PW})
    ).status_code == 401
    assert (
        await plain.post(
            f"{API}/auth/local/login", json={"username": "root", "password": "new password 1"}
        )
    ).status_code == 200


async def test_break_glass_setup_and_reset(settings: Settings) -> None:
    settings.break_glass = True
    app = create_app(settings)
    app.state.runtime_enabled = False
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as c,
    ):
        st = (await c.get(f"{API}/auth/status")).json()
        assert st["break_glass"] is True and st["setup_required"] is True
        assert (await _setup(c)).status_code == 200
        # admin exists and no reset flag: closed
        assert (await c.get(f"{API}/auth/status")).json()["setup_required"] is False
        assert (await _setup(c, "other")).status_code == 409
    settings.break_glass_reset = True
    app = create_app(settings)
    app.state.runtime_enabled = False
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as c,
    ):
        tok = app.state.reset_token
        assert (await c.get(f"{API}/auth/status")).json()["reset_token_required"] is True
        body = {"username": "root", "password": "reset pass 1"}
        assert (await c.post(f"{API}/auth/setup", json=body)).status_code == 403
        bad = {**body, "reset_token": "nope"}
        assert (await c.post(f"{API}/auth/setup", json=bad)).status_code == 403
        r = await c.post(f"{API}/auth/setup", json={**body, "reset_token": tok})
        assert r.status_code == 200
        # one use only
        assert (await c.get(f"{API}/auth/status")).json()["reset_token_required"] is False
        again = {**body, "reset_token": tok}
        assert (await c.post(f"{API}/auth/setup", json=again)).status_code == 409
        c.cookies.clear()
        r = await c.post(
            f"{API}/auth/local/login", json={"username": "root", "password": "reset pass 1"}
        )
        assert r.status_code == 200


async def test_break_glass_overrides_disabled_local(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    async with session_scope() as s:
        s.add(Setting(key="auth", value={"public_url": None, "local_enabled": False}))
        await s.flush()
        await reload_auth(app, s)
    app.state.settings.break_glass = True
    r = await client.post(f"{API}/auth/local/login", json={"username": "a", "password": "b"})
    assert r.status_code == 401  # reachable, just wrong credentials


async def test_secure_cookie_follows_scheme(app_plain: FastAPI) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_plain), base_url="https://testserver"
    ) as c:
        r = await c.post(f"{API}/auth/setup", json={"username": "s", "password": PW})
    cookies = [
        x for x in r.headers.get_list("set-cookie") if x.startswith(("session=", "ih_csrf="))
    ]
    assert len(cookies) == 2 and all("secure" in x.lower() for x in cookies)


async def test_cookies_not_secure_over_http(plain: httpx.AsyncClient) -> None:
    r = await _setup(plain)
    cookies = r.headers.get_list("set-cookie")
    assert len(cookies) == 2 and not any("secure" in x.lower() for x in cookies)


async def test_setup_closed_when_any_admin_exists(plain: httpx.AsyncClient) -> None:
    async with session_scope() as s:
        s.add(User(sub="oidc|1", role=Role.admin, groups=[]))
    assert (await plain.get(f"{API}/auth/status")).json()["setup_required"] is False
    assert (await _setup(plain)).status_code == 409


async def test_setup_open_if_only_disabled_admin(plain: httpx.AsyncClient) -> None:
    async with session_scope() as s:
        s.add(User(sub="oidc|1", role=Role.admin, groups=[], disabled=True))
    assert (await _setup(plain)).status_code == 200


async def test_reset_reenables_disabled_admin_and_revokes_sessions(settings: Settings) -> None:
    settings.break_glass = True
    settings.break_glass_reset = True
    app = create_app(settings)
    app.state.runtime_enabled = False
    async with app.router.lifespan_context(app):
        tok = app.state.reset_token
        async with session_scope() as s:
            s.add(Setting(key="local_admin", value={"username": "root", "password_hash": "x"}))
            s.add(User(sub="local:root", role=Role.admin, groups=[], disabled=True))
        t = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=t, base_url="http://testserver") as c:
            r = await c.post(
                f"{API}/auth/setup", json={"username": "root", "password": PW, "reset_token": tok}
            )
            assert r.status_code == 200
            assert (await c.get(f"{API}/auth/me")).status_code == 200
        async with session_scope() as s:
            u = (await s.execute(select(User).where(User.sub == "local:root"))).scalar_one()
            assert u.disabled is False and u.session_gen == 1


async def test_password_change_revokes_other_sessions(plain: httpx.AsyncClient) -> None:
    await _setup(plain)
    stale = dict(plain.cookies)
    h = {"X-CSRF-Token": plain.cookies["ih_csrf"]}
    r = await plain.put(
        f"{API}/settings/local-admin",
        headers=h,
        json={"current_password": PW, "new_password": "new password 1"},
    )
    assert r.status_code == 204
    assert (await plain.get(f"{API}/auth/me")).status_code == 200  # caller stays signed in
    async with httpx.AsyncClient(
        transport=plain._transport,
        base_url="http://testserver",
        cookies=stale,  # type: ignore[attr-defined]
    ) as old:
        assert (await old.get(f"{API}/auth/me")).status_code == 401


async def test_username_change_disables_old_row(app_plain: FastAPI) -> None:
    async with session_scope() as s:
        await save_local_admin(s, "old", PW)
        await save_local_admin(s, "new", PW)
        rows = {u.sub: u for u in (await s.execute(select(User))).scalars()}
    assert rows["local:old"].disabled is True and rows["local:new"].disabled is False


async def test_disable_oidc_requires_local_admin(app: FastAPI, client: httpx.AsyncClient) -> None:
    async with session_scope() as s:
        s.add(User(sub="oidc|a", role=Role.admin, groups=["admins"]))
    # authenticate as the OIDC admin is heavy; call the validator directly
    from fastapi import HTTPException

    from app.api.v1.settings import _prepare_auth
    from app.schemas.settings import SettingsDoc

    body = SettingsDoc.model_validate({"oidc": {"enabled": False}})
    async with session_scope() as s:
        with pytest.raises(HTTPException) as ei:
            await _prepare_auth(body, {}, _FakeReq(app), s)
        assert ei.value.status_code == 422
        await save_local_admin(s, "root", PW)
        await _prepare_auth(body, {}, _FakeReq(app), s)


class _FakeReq:
    def __init__(self, app: FastAPI) -> None:
        self.app = app
