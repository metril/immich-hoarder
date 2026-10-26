import httpx
import pytest
from fastapi import FastAPI
from helpers import TARGET, actor

from app.immich import client as immich_client

PERMS = [p for p in immich_client.REQUIRED_PERMISSIONS if p != "album.create"]


def mount(client: httpx.AsyncClient, handler: httpx.MockTransport) -> None:
    app = client._transport.app  # type: ignore[attr-defined]
    assert isinstance(app, FastAPI)
    app.state.immich_transport = handler


async def make_target(client: httpx.AsyncClient, h: dict[str, str]) -> int:
    return (await client.post("/api/v1/targets", json=TARGET, headers=h)).json()["id"]


async def test_target_test_ok_reports_missing_permissions(client: httpx.AsyncClient) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.headers["x-api-key"] == "k-secret"
        if req.url.path == "/api/server/version":
            return httpx.Response(200, json={"major": 1, "minor": 2, "patch": 3})
        return httpx.Response(200, json={"permissions": PERMS})

    mount(client, httpx.MockTransport(handler))
    _, h = await actor("a")
    tid = await make_target(client, h)
    r = await client.post(f"/api/v1/targets/{tid}/test", headers=h)
    assert r.status_code == 200
    assert r.json() == {
        "ok": False,
        "version": "1.2.3",
        "missing_permissions": ["album.create"],
        "error": None,
    }


async def test_target_test_unreachable_ok_false(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(immich_client, "_BACKOFF", (0.0, 0.0, 0.0))

    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom k-secret")

    mount(client, httpx.MockTransport(handler))
    _, h = await actor("a")
    tid = await make_target(client, h)
    r = await client.post(f"/api/v1/targets/{tid}/test", headers=h)
    assert r.status_code == 200
    assert r.json()["ok"] is False and r.json()["error"] == "unreachable"
    assert "k-secret" not in r.text


async def test_target_test_unauthorized(client: httpx.AsyncClient) -> None:
    mount(client, httpx.MockTransport(lambda req: httpx.Response(401, json={"message": "no"})))
    _, h = await actor("a")
    tid = await make_target(client, h)
    r = await client.post(f"/api/v1/targets/{tid}/test", headers=h)
    assert r.status_code == 200
    assert r.json()["ok"] is False and r.json()["error"] == "unauthorized"
    assert "k-secret" not in r.text


async def test_albums_lists(client: httpx.AsyncClient) -> None:
    albums = [
        {"id": "2", "albumName": "b", "assetCount": 3},
        {"id": "1", "albumName": "a", "assetCount": 0},
    ]
    mount(client, httpx.MockTransport(lambda req: httpx.Response(200, json=albums)))
    _, h = await actor("a")
    tid = await make_target(client, h)
    r = await client.get(f"/api/v1/targets/{tid}/albums", headers=h)
    assert r.status_code == 200
    assert r.json() == {
        "items": [
            {"id": "1", "name": "a", "asset_count": 0},
            {"id": "2", "name": "b", "asset_count": 3},
        ]
    }


async def test_albums_unavailable_502(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(immich_client, "_BACKOFF", (0.0, 0.0, 0.0))

    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("x")

    mount(client, httpx.MockTransport(handler))
    _, h = await actor("a")
    tid = await make_target(client, h)
    r = await client.get(f"/api/v1/targets/{tid}/albums", headers=h)
    assert r.status_code == 502 and r.json() == {"detail": "immich unavailable"}


async def test_albums_requires_use(client: httpx.AsyncClient) -> None:
    mount(client, httpx.MockTransport(good_handler))
    _, ha = await actor("a")
    _, hb = await actor("b")
    tid = await make_target(client, ha)
    assert (await client.get(f"/api/v1/targets/{tid}/albums", headers=ha)).status_code == 200
    assert (await client.post(f"/api/v1/targets/{tid}/test", headers=ha)).status_code == 200
    assert (await client.get(f"/api/v1/targets/{tid}/albums", headers=hb)).status_code == 404
    assert (await client.post(f"/api/v1/targets/{tid}/test", headers=hb)).status_code == 404


def good_handler(req: httpx.Request) -> httpx.Response:
    if req.url.path == "/api/server/version":
        return httpx.Response(200, json={"major": 1, "minor": 2, "patch": 3})
    if req.url.path == "/api/albums":
        return httpx.Response(200, json=[])
    return httpx.Response(200, json={"permissions": PERMS})


async def test_invalid_response_test_ok_false(client: httpx.AsyncClient) -> None:
    mount(client, httpx.MockTransport(lambda req: httpx.Response(200, text="<html>hi</html>")))
    _, h = await actor("a")
    tid = await make_target(client, h)
    r = await client.post(f"/api/v1/targets/{tid}/test", headers=h)
    assert r.status_code == 200
    assert r.json()["ok"] is False and r.json()["error"] == "immich error 200"


async def test_invalid_response_albums_502(client: httpx.AsyncClient) -> None:
    mount(client, httpx.MockTransport(lambda req: httpx.Response(200, json={"x": 1})))
    _, h = await actor("a")
    tid = await make_target(client, h)
    r = await client.get(f"/api/v1/targets/{tid}/albums", headers=h)
    assert r.status_code == 502 and r.json() == {"detail": "immich unavailable"}


async def test_albums_auth_failure_502_unauthorized(client: httpx.AsyncClient) -> None:
    mount(client, httpx.MockTransport(lambda req: httpx.Response(403, json={"message": "no"})))
    _, h = await actor("a")
    tid = await make_target(client, h)
    r = await client.get(f"/api/v1/targets/{tid}/albums", headers=h)
    assert r.status_code == 502 and r.json() == {"detail": "immich unauthorized"}


async def test_albums_sorted_casefold(client: httpx.AsyncClient) -> None:
    albums = [
        {"id": str(i), "albumName": n, "assetCount": 0} for i, n in enumerate(["b", "C", "a"])
    ]
    mount(client, httpx.MockTransport(lambda req: httpx.Response(200, json=albums)))
    _, h = await actor("a")
    tid = await make_target(client, h)
    r = await client.get(f"/api/v1/targets/{tid}/albums", headers=h)
    assert [a["name"] for a in r.json()["items"]] == ["a", "b", "C"]


async def test_target_test_json_missing_fields(client: httpx.AsyncClient) -> None:
    mount(client, httpx.MockTransport(lambda req: httpx.Response(200, json={})))
    _, h = await actor("a")
    tid = await make_target(client, h)
    r = await client.post(f"/api/v1/targets/{tid}/test", headers=h)
    assert r.status_code == 200
    assert r.json()["ok"] is False and r.json()["error"] == "immich error 200"
    assert "k-secret" not in r.text
