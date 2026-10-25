import httpx
from helpers import TARGET, actor

SRC = {"name": "s", "url": "http://x"}


async def _target(c: httpx.AsyncClient, h: dict[str, str]) -> int:
    return (await c.post("/api/v1/targets", json=TARGET, headers=h)).json()["id"]


async def test_source_requires_use_on_target(client: httpx.AsyncClient) -> None:
    _, ha = await actor("a")
    ub, hb = await actor("b")
    tid = await _target(client, ha)
    r = await client.post("/api/v1/sources", json={**SRC, "target_id": tid}, headers=hb)
    assert r.status_code == 403
    body = {
        "visibility": "restricted",
        "shares": [{"principal_type": "user", "principal_id": str(ub), "perm": "use"}],
    }
    assert (
        await client.put(f"/api/v1/targets/{tid}/shares", json=body, headers=ha)
    ).status_code == 200
    r = await client.post("/api/v1/sources", json={**SRC, "target_id": tid}, headers=hb)
    assert r.status_code == 201


async def test_invalid_cron_422(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    tid = await _target(client, h)
    r = await client.post(
        "/api/v1/sources", json={**SRC, "target_id": tid, "schedule_cron": "nope"}, headers=h
    )
    assert r.status_code == 422


async def test_bad_album_template_field_422(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    tid = await _target(client, h)
    ok = await client.post(
        "/api/v1/sources",
        json={**SRC, "target_id": tid, "album_template": "{subreddit}-{date}"},
        headers=h,
    )
    assert ok.status_code == 201
    r = await client.post(
        "/api/v1/sources",
        json={**SRC, "target_id": tid, "album_template": "{bogus}"},
        headers=h,
    )
    assert r.status_code == 422


async def test_scope_enforced(client: httpx.AsyncClient) -> None:
    from helpers import headers_for, make_user

    uid = await make_user("a")
    h = await headers_for(uid, ["sources:read"])
    r = await client.post("/api/v1/sources", json={**SRC, "target_id": 1}, headers=h)
    assert r.status_code == 403
    assert (await client.get("/api/v1/sources", headers=h)).status_code == 200


async def test_ephemeral_hidden(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    tid = await _target(client, h)
    await client.post(
        "/api/v1/sources", json={**SRC, "target_id": tid, "ephemeral": True}, headers=h
    )
    assert (await client.get("/api/v1/sources", headers=h)).json()["items"] == []
    r = await client.get("/api/v1/sources?include_ephemeral=true", headers=h)
    assert len(r.json()["items"]) == 1
