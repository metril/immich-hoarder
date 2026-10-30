import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from app.api.v1.auth import save_local_admin
from app.auth.local import hash_password
from app.core.config import Settings
from app.db.engine import session_scope
from app.db.models import Role, Setting, User
from app.main import create_app

API = "/api/v1"
PW = "correct horse battery"


async def _login(c: httpx.AsyncClient, user: str, pw: str = PW) -> httpx.Response:
    return await c.post(f"{API}/auth/local/login", json={"username": user, "password": pw})


async def _user(sub: str) -> User:
    async with session_scope() as s:
        return (await s.execute(select(User).where(User.sub == sub))).scalar_one()


async def test_login_uses_user_hash_and_falls_back_to_setting(plain: httpx.AsyncClient) -> None:
    async with session_scope() as s:
        await save_local_admin(s, "root", PW)
    assert (await _login(plain, "root")).status_code == 200
    # fallback: hash only on the setting row (half-migrated DB)
    async with session_scope() as s:
        u = (await s.execute(select(User).where(User.sub == "local:root"))).scalar_one()
        u.password_hash = None
    assert (await _login(plain, "root")).status_code == 200
    assert (await _login(plain, "root", "wrong password")).status_code == 401
    # user hash only (setting row gone)
    async with session_scope() as s:
        u = (await s.execute(select(User).where(User.sub == "local:root"))).scalar_one()
        u.password_hash = hash_password("other password 1")
        row = await s.get(Setting, "local_admin")
        assert row is not None
        await s.delete(row)
    assert (await _login(plain, "root", "other password 1")).status_code == 200
    assert (await _login(plain, "root")).status_code == 401
    assert (await _login(plain, "nobody")).status_code == 401
    assert (await plain.get(f"{API}/auth/status")).json()["local_login_enabled"] is True


async def test_setting_hash_not_used_for_other_user(plain: httpx.AsyncClient) -> None:
    async with session_scope() as s:
        await save_local_admin(s, "root", PW)
        s.add(User(sub="local:bob", role=Role.user, groups=[]))  # no hash anywhere
    assert (await _login(plain, "bob")).status_code == 401


async def test_admin_creates_users_who_log_in(plain: httpx.AsyncClient) -> None:
    async with session_scope() as s:
        await save_local_admin(s, "root", PW)
    assert (await _login(plain, "root")).status_code == 200
    h = {"X-CSRF-Token": plain.cookies["ih_csrf"]}
    for name in ("alice", "bob"):
        r = await plain.post(
            f"{API}/users/local",
            json={"username": name, "password": f"pw-{name}-12345", "role": "user"},
            headers=h,
        )
        assert r.status_code == 201 and r.json()["sub"] == f"local:{name}"
    dup = await plain.post(
        f"{API}/users/local", json={"username": "alice", "password": PW}, headers=h
    )
    assert dup.status_code == 409
    short = await plain.post(
        f"{API}/users/local", json={"username": "x", "password": "a"}, headers=h
    )
    assert short.status_code == 422
    plain.cookies.clear()
    for name in ("alice", "bob", "root"):
        pw = PW if name == "root" else f"pw-{name}-12345"
        assert (await _login(plain, name, pw)).status_code == 200
        assert (await plain.get(f"{API}/auth/me")).json()["name"] == name
        plain.cookies.clear()
    assert (await _login(plain, "alice", "pw-bob-12345")).status_code == 401


async def test_reset_flags_must_change_and_self_change(plain: httpx.AsyncClient) -> None:
    async with session_scope() as s:
        await save_local_admin(s, "root", PW)
    await _login(plain, "root")
    h = {"X-CSRF-Token": plain.cookies["ih_csrf"]}
    body = {"username": "al", "password": "initial pass 1"}
    uid = (await plain.post(f"{API}/users/local", json=body, headers=h)).json()["id"]
    r = await plain.post(
        f"{API}/users/{uid}/password", json={"new_password": "temp password 1"}, headers=h
    )
    assert r.status_code == 200
    plain.cookies.clear()
    assert (await _login(plain, "al", "initial pass 1")).status_code == 401
    me = await _login(plain, "al", "temp password 1")
    assert me.json()["must_change_password"] is True
    assert (await plain.get(f"{API}/auth/me")).json()["must_change_password"] is True
    h2 = {"X-CSRF-Token": plain.cookies["ih_csrf"]}
    new = {"current_password": "temp password 1", "new_password": "final password 1"}
    bad = await plain.post(
        f"{API}/auth/password", json={**new, "current_password": "nope"}, headers=h2
    )
    assert bad.status_code == 403
    ok = await plain.post(f"{API}/auth/password", json=new, headers=h2)
    assert ok.status_code == 200 and ok.json()["must_change_password"] is False
    assert (await plain.get(f"{API}/auth/me")).json()["must_change_password"] is False


async def test_reset_revokes_sessions(plain: httpx.AsyncClient, app_plain: FastAPI) -> None:
    async with session_scope() as s:
        await save_local_admin(s, "root", PW)
        s.add(User(sub="local:al", role=Role.user, groups=[], password_hash=hash_password(PW)))
    await _login(plain, "root")
    h = {"X-CSRF-Token": plain.cookies["ih_csrf"]}
    uid = (await _user("local:al")).id
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_plain), base_url="http://testserver"
    ) as other:
        assert (await _login(other, "al")).status_code == 200
        assert (await other.get(f"{API}/auth/me")).status_code == 200
        r = await plain.post(
            f"{API}/users/{uid}/password", json={"new_password": "brand new pass 1"}, headers=h
        )
        assert r.status_code == 200
        assert (await other.get(f"{API}/auth/me")).status_code == 401


@pytest.mark.parametrize("reset", [False, True])
async def test_break_glass_with_pre_migration_state(settings: Settings, reset: bool) -> None:
    settings.break_glass = True
    settings.break_glass_reset = reset
    app = create_app(settings)
    app.state.runtime_enabled = False
    async with app.router.lifespan_context(app):
        tok = app.state.reset_token
        async with session_scope() as s:  # as left by a pre-migration release: setting-only hash
            s.add(
                Setting(
                    key="local_admin",
                    value={"username": "root", "password_hash": hash_password(PW)},
                )
            )
            s.add(User(sub="local:root", role=Role.admin, groups=[]))
        t = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=t, base_url="http://testserver") as c:
            assert (await _login(c, "root")).status_code == 200  # fallback works
            if reset:
                body = {"username": "root", "password": "recovered pass 1", "reset_token": tok}
                assert (await c.post(f"{API}/auth/setup", json=body)).status_code == 200
                u = await _user("local:root")
                async with session_scope() as s:
                    row = await s.get(Setting, "local_admin")
                    assert u.password_hash and row and row.value["password_hash"] == u.password_hash
                assert (await _login(c, "root", "recovered pass 1")).status_code == 200
                assert (await _login(c, "root")).status_code == 401


async def test_deleted_user_cookie_does_not_match_reused_id(
    plain: httpx.AsyncClient, app_plain: FastAPI
) -> None:
    async with session_scope() as s:
        await save_local_admin(s, "root", PW)
    await _login(plain, "root")
    h = {"X-CSRF-Token": plain.cookies["ih_csrf"]}
    mk = {"username": "al", "password": "initial pass 1"}
    uid = (await plain.post(f"{API}/users/local", json=mk, headers=h)).json()["id"]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_plain), base_url="http://testserver"
    ) as victim:
        assert (await _login(victim, "al", "initial pass 1")).status_code == 200
        assert (await plain.delete(f"{API}/users/{uid}", headers=h)).status_code == 204
        again = await plain.post(f"{API}/users/local", json={**mk, "username": "bo"}, headers=h)
        assert again.json()["id"] == uid  # SQLite reuses the freed id
        assert (await victim.get(f"{API}/auth/me")).status_code == 401
