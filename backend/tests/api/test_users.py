import httpx
from helpers import actor, headers_for, make_user

from app.db.models import Role


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
        await client.put("/api/v1/settings", json={"x": {"y": 1}}, headers=h)
    ).status_code == 200
    await client.put("/api/v1/settings", json={"z": 2}, headers=h)
    assert (await client.get("/api/v1/settings", headers=h)).json() == {"x": {"y": 1}, "z": 2}


async def test_api_keys(client: httpx.AsyncClient) -> None:
    uid, h = await actor("a")
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
    _ = (uid, headers_for)


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
    for body in ({"role": "user"}, {"disabled": True}):
        r = await client.patch(f"/api/v1/users/{aid}", json=body, headers=h)
        assert r.status_code == 409 and r.json() == {"detail": "last admin"}
    other = await make_user("adm2", Role.admin)
    assert (
        await client.patch(f"/api/v1/users/{other}", json={"disabled": True}, headers=h)
    ).status_code == 200
    assert (
        await client.patch(f"/api/v1/users/{aid}", json={"role": "user"}, headers=h)
    ).status_code == 409
