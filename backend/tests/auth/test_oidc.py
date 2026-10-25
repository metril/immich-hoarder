import time

import fake_idp
import httpx
from conftest import do_login
from sqlalchemy import select

from app.db.engine import session_scope
from app.db.models import Role, User


def bearer(tok: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {tok}"}


async def test_bearer_valid_creates_user(client: httpx.AsyncClient, idp: fake_idp.FakeIdp) -> None:
    r = await client.get(
        "/api/v1/auth/me", headers=bearer(idp.make_token("alice", ["hoarder-users"]))
    )
    assert r.status_code == 200
    assert r.json()["role"] == "user"
    async with session_scope() as s:
        assert (await s.execute(select(User).where(User.sub == "alice"))).scalar_one()


async def test_bearer_wrong_aud_401(client: httpx.AsyncClient, idp: fake_idp.FakeIdp) -> None:
    tok = idp.make_token("alice", ["hoarder-users"], aud="other")
    assert (await client.get("/api/v1/auth/me", headers=bearer(tok))).status_code == 401


async def test_bearer_expired_401(client: httpx.AsyncClient, idp: fake_idp.FakeIdp) -> None:
    tok = idp.make_token("alice", ["hoarder-users"], exp=int(time.time()) - 60)
    assert (await client.get("/api/v1/auth/me", headers=bearer(tok))).status_code == 401


async def test_group_removed_denied(client: httpx.AsyncClient, idp: fake_idp.FakeIdp) -> None:
    ok = await client.get(
        "/api/v1/auth/me", headers=bearer(idp.make_token("bob", ["hoarder-users"]))
    )
    assert ok.status_code == 200
    r = await client.get("/api/v1/auth/me", headers=bearer(idp.make_token("bob", ["other"])))
    assert r.status_code == 401
    async with session_scope() as s:
        u = (await s.execute(select(User).where(User.sub == "bob"))).scalar_one()
        assert u.groups == ["other"]


async def test_admin_group_maps_admin(client: httpx.AsyncClient, idp: fake_idp.FakeIdp) -> None:
    r = await client.get(
        "/api/v1/auth/me", headers=bearer(idp.make_token("root", ["hoarder-admins"]))
    )
    assert r.json()["role"] == Role.admin


async def test_login_callback_sets_session(
    client: httpx.AsyncClient, idp: fake_idp.FakeIdp
) -> None:
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    r = await do_login(client, idp, "carol", ["hoarder-users"])
    assert r.status_code in (302, 303)
    assert r.headers["location"] == "/"
    assert "ih_csrf" in client.cookies
    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["name"] == "carol"
