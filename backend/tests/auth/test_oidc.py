import time

import fake_idp
import httpx
import pytest
from conftest import do_login
from sqlalchemy import select

from app.auth import oidc
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


async def test_callback_denied_clears_session_and_persists_groups(
    client: httpx.AsyncClient, idp: fake_idp.FakeIdp
) -> None:
    await do_login(client, idp, "erin", ["hoarder-users"])
    assert (await client.get("/api/v1/auth/me")).status_code == 200
    r = await do_login(client, idp, "erin", ["other"])
    assert r.status_code == 403
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    async with session_scope() as s:
        u = (await s.execute(select(User).where(User.sub == "erin"))).scalar_one()
        assert u.groups == ["other"]


async def test_callback_first_login_outside_groups_403(
    client: httpx.AsyncClient, idp: fake_idp.FakeIdp
) -> None:
    r = await do_login(client, idp, "frank", ["other"])
    assert r.status_code == 403
    assert (await client.get("/api/v1/auth/me")).status_code == 401


async def test_jwks_with_enc_key_still_validates(
    client: httpx.AsyncClient, idp: fake_idp.FakeIdp
) -> None:
    idp.extra_keys = [
        {"kid": "enc1", "kty": "RSA", "use": "enc", "alg": "RSA-OAEP", "n": "AQAB", "e": "AQAB"},
        {"kid": "bad", "kty": "RSA", "alg": "RS256"},
    ]
    tok = idp.make_token("gina", ["hoarder-users"])
    r = await client.get("/api/v1/auth/me", headers=bearer(tok))
    assert r.status_code == 200


async def test_es256_token_validates(client: httpx.AsyncClient, idp: fake_idp.FakeIdp) -> None:
    tok = idp.make_token("ella", ["hoarder-users"], es256=True)
    assert (await client.get("/api/v1/auth/me", headers=bearer(tok))).status_code == 200


async def test_disabled_user_bearer_401(client: httpx.AsyncClient, idp: fake_idp.FakeIdp) -> None:
    tok = idp.make_token("dan", ["hoarder-users"])
    assert (await client.get("/api/v1/auth/me", headers=bearer(tok))).status_code == 200
    async with session_scope() as s:
        u = (await s.execute(select(User).where(User.sub == "dan"))).scalar_one()
        u.disabled = True
    assert (await client.get("/api/v1/auth/me", headers=bearer(tok))).status_code == 401


async def test_unknown_kid_refetch_rate_limited(
    client: httpx.AsyncClient, idp: fake_idp.FakeIdp
) -> None:
    ok = idp.make_token("hank", ["hoarder-users"])
    assert (await client.get("/api/v1/auth/me", headers=bearer(ok))).status_code == 200
    assert idp.jwks_calls == 1
    for kid in ("evil1", "evil2"):
        tok = idp.make_token("hank", ["hoarder-users"], kid=kid)
        assert (await client.get("/api/v1/auth/me", headers=bearer(tok))).status_code == 401
    assert idp.jwks_calls == 2  # one forced refetch beyond the initial fetch
    assert idp.discovery_calls == 2


async def test_unknown_kid_refetches_after_window(
    client: httpx.AsyncClient, idp: fake_idp.FakeIdp, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(oidc, "FORCED_REFETCH_INTERVAL", 0.0)
    ok = idp.make_token("ivy", ["hoarder-users"])
    assert (await client.get("/api/v1/auth/me", headers=bearer(ok))).status_code == 200
    for kid in ("evil1", "evil2"):
        tok = idp.make_token("ivy", ["hoarder-users"], kid=kid)
        assert (await client.get("/api/v1/auth/me", headers=bearer(tok))).status_code == 401
    assert idp.jwks_calls == 3
