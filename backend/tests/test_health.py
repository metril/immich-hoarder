import httpx
from sqlalchemy import text


async def test_healthz_ok(client: httpx.AsyncClient) -> None:
    r = await client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_openapi_served(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/openapi.json")
    assert r.status_code == 200
    assert r.json()["info"]["version"] == "0.1.0"


async def test_startup_applies_migrations(client: httpx.AsyncClient) -> None:
    from app.db.engine import session_scope

    async with session_scope() as s:
        rows = (await s.execute(text("SELECT name FROM sqlite_master WHERE name='users'"))).all()
    assert rows


async def test_docs_served(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/docs")).status_code == 200
