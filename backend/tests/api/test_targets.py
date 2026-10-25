import httpx
from helpers import TARGET, actor


async def test_target_create_hides_key(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    r = await client.post("/api/v1/targets", json=TARGET, headers=h)
    assert r.status_code == 201
    tid = r.json()["id"]
    for body in (
        (await client.get(f"/api/v1/targets/{tid}", headers=h)).json(),
        (await client.get("/api/v1/targets", headers=h)).json()["items"][0],
    ):
        assert body["has_api_key"] is True
        assert "api_key" not in body and "k-secret" not in str(body)


async def test_list_paginates(client: httpx.AsyncClient) -> None:
    from app.db.engine import session_scope
    from app.db.models import ImmichTarget

    uid, h = await actor("a")
    async with session_scope() as s:
        s.add_all(
            ImmichTarget(name=f"t{i}", url="u", api_key_enc=b"x", owner_id=uid) for i in range(205)
        )
    r1 = await client.get("/api/v1/targets?limit=500", headers=h)
    assert r1.status_code == 422
    r1 = (await client.get("/api/v1/targets?limit=200", headers=h)).json()
    assert len(r1["items"]) == 200 and r1["next_cursor"]
    r2 = (
        await client.get(
            "/api/v1/targets", params={"limit": 200, "cursor": r1["next_cursor"]}, headers=h
        )
    ).json()
    assert len(r2["items"]) == 5 and r2["next_cursor"] is None


async def test_in_use_delete_409(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    tid = (await client.post("/api/v1/targets", json=TARGET, headers=h)).json()["id"]
    r = await client.post(
        "/api/v1/sources",
        json={"name": "s", "url": "https://www.reddit.com/r/pics/", "target_id": tid},
        headers=h,
    )
    assert r.status_code == 201
    d = await client.delete(f"/api/v1/targets/{tid}", headers=h)
    assert d.status_code == 409 and d.json() == {"detail": "in use"}
    await client.delete(f"/api/v1/sources/{r.json()['id']}", headers=h)
    assert (await client.delete(f"/api/v1/targets/{tid}", headers=h)).status_code == 204
