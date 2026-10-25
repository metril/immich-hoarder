import httpx


async def test_healthz_ok(client: httpx.AsyncClient) -> None:
    r = await client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_openapi_served(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/openapi.json")
    assert r.status_code == 200
    assert r.json()["info"]["version"] == "0.1.0"
