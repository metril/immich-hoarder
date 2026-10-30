from datetime import datetime

import httpx
from helpers import actor, headers_for, make_user

from app.db.engine import session_scope
from app.db.models import ApiKey, Role


async def test_users_admin_only(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    assert (await client.get("/api/v1/users", headers=h)).status_code == 403
    assert (await client.get("/api/v1/settings", headers=h)).status_code == 403
    assert (await client.put("/api/v1/settings", json={"a": 1}, headers=h)).status_code == 403


async def test_admin_manages_users_and_settings(client: httpx.AsyncClient) -> None:
    uid = await make_user("a")
    _, h = await actor("adm", Role.admin)
    r = await client.patch(f"/api/v1/users/{uid}", json={"disabled": True}, headers=h)
    assert r.status_code == 200 and r.json()["disabled"] is True
    assert (
        await client.put("/api/v1/settings", json={"runtime": {"retention_days": 5}}, headers=h)
    ).status_code == 200
    await client.put("/api/v1/settings", json={"notify": {"on": ["success"]}}, headers=h)
    assert (await client.get("/api/v1/settings", headers=h)).json() == {
        "runtime": {"retention_days": 5},
        "notify": {"on": ["success"]},
    }


async def test_api_keys(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    _, hb = await actor("b")
    _, hadm = await actor("adm", Role.admin)
    r = await client.post(
        "/api/v1/api-keys", json={"name": "k", "scopes": ["sources:read"]}, headers=h
    )
    assert r.status_code == 201 and r.json()["key"].startswith("ih_")
    kid = r.json()["id"]
    assert "key" not in (await client.get("/api/v1/api-keys", headers=h)).json()["items"][0]
    bad = await client.post("/api/v1/api-keys", json={"name": "k", "scopes": ["nope"]}, headers=h)
    assert bad.status_code == 422
    cap = await client.post("/api/v1/api-keys", json={"name": "k", "scopes": ["admin"]}, headers=h)
    assert cap.status_code == 403
    ok = await client.post(
        "/api/v1/api-keys", json={"name": "k", "scopes": ["admin"]}, headers=hadm
    )
    assert ok.status_code == 201
    # others cannot see or revoke
    assert (await client.delete(f"/api/v1/api-keys/{kid}", headers=hb)).status_code == 404
    assert len((await client.get("/api/v1/api-keys", headers=hadm)).json()["items"]) >= 3
    assert (await client.delete(f"/api/v1/api-keys/{kid}", headers=h)).status_code == 204
    # revoked key no longer authenticates
    raw = r.json()["key"]
    assert (await client.get("/api/v1/sources", headers={"X-API-Key": raw})).status_code == 401


async def test_api_keys_paginated(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    for i in range(3):
        await client.post("/api/v1/api-keys", json={"name": f"k{i}", "scopes": []}, headers=h)
    p1 = (await client.get("/api/v1/api-keys?limit=2", headers=h)).json()
    assert len(p1["items"]) == 2 and p1["next_cursor"]
    p2 = (
        await client.get(
            "/api/v1/api-keys", params={"limit": 2, "cursor": p1["next_cursor"]}, headers=h
        )
    ).json()
    assert len(p2["items"]) == 2 and p2["next_cursor"] is None  # 4 keys total incl. the caller's


async def test_key_scopes_enforced(client: httpx.AsyncClient) -> None:
    uid = await make_user("a")
    h = await headers_for(uid, ["keys:read"])
    assert (await client.get("/api/v1/api-keys", headers=h)).status_code == 200
    r = await client.post("/api/v1/api-keys", json={"name": "k", "scopes": []}, headers=h)
    assert r.status_code == 403
    assert (await client.delete("/api/v1/api-keys/1", headers=h)).status_code == 403
    h2 = await headers_for(uid, ["sources:read"])
    assert (await client.get("/api/v1/api-keys", headers=h2)).status_code == 403


async def test_last_admin_protected(client: httpx.AsyncClient) -> None:
    aid, h = await actor("adm", Role.admin)
    r = await client.patch(f"/api/v1/users/{aid}", json={"disabled": True}, headers=h)
    assert r.status_code == 409 and r.json() == {"detail": "last admin"}
    other = await make_user("adm2", Role.admin)
    assert (
        await client.patch(f"/api/v1/users/{other}", json={"disabled": True}, headers=h)
    ).status_code == 200
    assert (
        await client.patch(f"/api/v1/users/{aid}", json={"disabled": True}, headers=h)
    ).status_code == 409


async def test_role_not_patchable(client: httpx.AsyncClient) -> None:
    uid = await make_user("a")
    _, h = await actor("adm", Role.admin)
    r = await client.patch(f"/api/v1/users/{uid}", json={"role": "admin"}, headers=h)
    assert r.status_code == 422


async def test_disabling_already_disabled_admin_is_ok(client: httpx.AsyncClient) -> None:
    _, h = await actor("adm", Role.admin)
    other = await make_user("adm2", Role.admin)
    for _ in range(2):
        r = await client.patch(f"/api/v1/users/{other}", json={"disabled": True}, headers=h)
        assert r.status_code == 200 and r.json()["disabled"] is True


async def test_api_key_get_edit_rotate(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    _, hb = await actor("b")
    r = await client.post(
        "/api/v1/api-keys",
        json={"name": "k", "scopes": ["sources:read"], "expires_at": "2099-01-01T00:00:00Z"},
        headers=h,
    )
    kid, raw = r.json()["id"], r.json()["key"]
    url = f"/api/v1/api-keys/{kid}"
    assert (await client.get(url, headers=h)).json()["name"] == "k"
    assert (await client.get(url, headers=hb)).status_code == 404
    assert (await client.patch(url, json={"name": "x"}, headers=hb)).status_code == 404
    assert (await client.post(f"{url}/rotate", headers=hb)).status_code == 404
    up = await client.patch(url, json={"name": "x", "scopes": ["jobs:read"]}, headers=h)
    assert up.json()["name"] == "x" and up.json()["scopes"] == ["jobs:read"]
    esc = await client.patch(url, json={"scopes": ["admin"]}, headers=h)
    assert esc.status_code == 403
    lim = await headers_for(await make_user("c"), ["keys:write", "keys:read"])
    mine = (
        await client.post("/api/v1/api-keys", json={"name": "m", "scopes": []}, headers=lim)
    ).json()["id"]
    r2 = await client.patch(f"/api/v1/api-keys/{mine}", json={"scopes": ["jobs:read"]}, headers=lim)
    assert r2.status_code == 403
    rot = await client.post(f"{url}/rotate", headers=h)
    assert rot.status_code == 201
    new = rot.json()
    assert new["id"] != kid and new["name"] == "x" and new["scopes"] == ["jobs:read"]
    assert new["expires_at"] == r.json()["expires_at"] and new["key"] != raw
    assert (await client.get("/api/v1/sources", headers={"X-API-Key": raw})).status_code == 401
    assert (await client.patch(url, json={"name": "y"}, headers=h)).status_code == 409
    assert (await client.post(f"{url}/rotate", headers=h)).status_code == 409
    assert (
        await client.get("/api/v1/api-keys", headers={"X-API-Key": new["key"]})
    ).status_code == 403


async def test_api_key_rotate_owner_only_and_expired(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    _, hadm = await actor("adm", Role.admin)
    kid = (
        await client.post("/api/v1/api-keys", json={"name": "k", "scopes": []}, headers=h)
    ).json()["id"]
    url = f"/api/v1/api-keys/{kid}"
    assert (await client.post(f"{url}/rotate", headers=hadm)).status_code == 404
    assert (await client.get(url, headers=hadm)).status_code == 200
    assert (await client.patch(url, json={"name": "z"}, headers=hadm)).json()["name"] == "z"
    async with session_scope() as s:
        key = await s.get(ApiKey, kid)
        assert key
        key.expires_at = datetime(2000, 1, 1)
    assert (await client.patch(url, json={"name": "y"}, headers=h)).status_code == 409
    assert (await client.post(f"{url}/rotate", headers=h)).status_code == 409
