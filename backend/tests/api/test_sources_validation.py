import httpx
from helpers import TARGET, actor

from app.db.models import Role

REDDIT = "https://www.reddit.com/r/pics/"


async def _target(c: httpx.AsyncClient, h: dict[str, str]) -> int:
    return (await c.post("/api/v1/targets", json=TARGET, headers=h)).json()["id"]


async def test_source_create_unsupported_url_422(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    tid = await _target(client, h)
    r = await client.post(
        "/api/v1/sources",
        json={"name": "s", "url": "https://example.invalid/x", "target_id": tid},
        headers=h,
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "unsupported url"


async def test_source_private_ip_422_then_allowed(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    _, ah = await actor("adm", Role.admin)
    tid = await _target(client, h)
    body = {"name": "s", "url": "http://10.0.0.5/a.jpg", "target_id": tid}
    assert (await client.post("/api/v1/sources", json=body, headers=h)).status_code == 422
    r = await client.put(
        "/api/v1/settings", json={"rip": {"allow_private_hosts": True}}, headers=ah
    )
    assert r.status_code == 200
    r = await client.post("/api/v1/sources", json=body, headers=h)
    assert r.status_code == 201
    sid = r.json()["id"]
    r = await client.patch(
        f"/api/v1/sources/{sid}", json={"url": "http://127.0.0.1/b.jpg"}, headers=h
    )
    assert r.status_code == 200
    await client.put("/api/v1/settings", json={"rip": {}}, headers=ah)
    r = await client.patch(
        f"/api/v1/sources/{sid}", json={"url": "http://127.0.0.1/c.jpg"}, headers=h
    )
    assert r.status_code == 422


async def test_source_extractor_set_server_side(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    tid = await _target(client, h)
    r = await client.post(
        "/api/v1/sources",
        json={"name": "s", "url": REDDIT, "target_id": tid, "extractor": "evil"},
        headers=h,
    )
    assert r.status_code == 201
    assert r.json()["extractor"] == "reddit"


async def test_source_bad_gdl_options_422(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    tid = await _target(client, h)
    r = await client.post(
        "/api/v1/sources",
        json={"name": "s", "url": REDDIT, "target_id": tid, "gdl_options": {"exec": "rm"}},
        headers=h,
    )
    assert r.status_code == 422
    ok = await client.post(
        "/api/v1/sources",
        json={"name": "s", "url": REDDIT, "target_id": tid, "gdl_options": {"retries": 2}},
        headers=h,
    )
    assert ok.status_code == 201
    r = await client.patch(
        f"/api/v1/sources/{ok.json()['id']}", json={"gdl_options": {"cookies": "x"}}, headers=h
    )
    assert r.status_code == 422


async def test_extractors_endpoint_lists_reddit(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    r = await client.get("/api/v1/extractors", headers=h)
    assert r.status_code == 200
    assert "reddit" in {i["category"] for i in r.json()["items"]}
