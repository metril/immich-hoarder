import httpx
from helpers import actor

from app.db.engine import session_scope
from app.db.models import User


async def _mk(sub: str, name: str | None, email: str | None, disabled: bool = False) -> int:
    async with session_scope() as s:
        u = User(sub=sub, name=name, email=email, disabled=disabled)
        s.add(u)
        await s.flush()
        return u.id


async def test_directory_requires_auth(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/users/directory?q=ab")).status_code == 401


async def test_directory_min_q_422(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    for q in ("", "a", " a ", "  "):
        assert (
            await client.get("/api/v1/users/directory", params={"q": q}, headers=h)
        ).status_code == 422
    assert (await client.get("/api/v1/users/directory", headers=h)).status_code == 422
    assert (await client.get("/api/v1/users/directory?q=ab", headers=h)).status_code == 200


async def test_directory_excludes_disabled_and_minimal_fields(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    bob = await _mk("bob", "Bobby Tables", "bob@example.com")
    await _mk("gone", "Bobby Gone", "gone@example.com", disabled=True)
    r = await client.get("/api/v1/users/directory", params={"q": "BOBBY"}, headers=h)
    assert r.status_code == 200
    assert r.json() == [{"id": bob, "name": "Bobby Tables"}]
    # no email substring probing; an exact (case-insensitive) email still matches
    r = await client.get("/api/v1/users/directory", params={"q": "example.com"}, headers=h)
    assert r.json() == []
    r = await client.get("/api/v1/users/directory", params={"q": "BOB@example.com"}, headers=h)
    assert [u["id"] for u in r.json()] == [bob]


async def test_directory_limit_20(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    for i in range(25):
        await _mk(f"u{i}", f"zed {i:02d}", None)
    r = await client.get("/api/v1/users/directory", params={"q": "zed"}, headers=h)
    assert len(r.json()) == 20
    names = [u["name"] for u in r.json()]
    assert names == sorted(names)
