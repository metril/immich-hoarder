import httpx
from helpers import TARGET, actor

from app.db.models import Role

SRC = {"name": "s", "url": "https://www.reddit.com/r/pics/"}


async def _target(c: httpx.AsyncClient, h: dict[str, str]) -> int:
    return (await c.post("/api/v1/targets", json=TARGET, headers=h)).json()["id"]


async def test_bad_regex_422_on_source_create(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    tid = await _target(client, h)
    r = await client.post(
        "/api/v1/sources",
        json={**SRC, "target_id": tid, "filters": {"title_include": "("}},
        headers=h,
    )
    assert r.status_code == 422
    r = await client.post(
        "/api/v1/sources",
        json={**SRC, "target_id": tid, "filters": {"title_include": "cat", "nope": 1}},
        headers=h,
    )
    assert r.status_code == 422
    r = await client.post(
        "/api/v1/sources",
        json={**SRC, "target_id": tid, "filters": {"title_include": "cat"}},
        headers=h,
    )
    assert r.status_code == 201
    assert r.json()["filters"]["phash_distance"] == 3
    assert r.json()["filters"]["min_width"] is None


async def test_backfill_validation(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    tid = await _target(client, h)

    async def post(mode: str, val: str | None) -> int:
        r = await client.post(
            "/api/v1/sources",
            json={**SRC, "target_id": tid, "backfill_mode": mode, "backfill_value": val},
            headers=h,
        )
        return r.status_code

    assert await post("last_n", "0") == 422
    assert await post("last_n", "x") == 422
    assert await post("last_n", None) == 422
    assert await post("since", "nope") == 422
    assert await post("full", "5") == 422
    assert await post("last_n", "5") == 201
    assert await post("since", "2024-01-31") == 201
    assert await post("full", None) == 201
    sid = (await client.post("/api/v1/sources", json={**SRC, "target_id": tid}, headers=h)).json()[
        "id"
    ]
    r = await client.patch(f"/api/v1/sources/{sid}", json={"backfill_mode": "last_n"}, headers=h)
    assert r.status_code == 422
    r = await client.patch(
        f"/api/v1/sources/{sid}", json={"filters": {"min_width": "x"}}, headers=h
    )
    assert r.status_code == 422


async def test_settings_put_rip_validated(client: httpx.AsyncClient) -> None:
    _, ah = await actor("adm", Role.admin)
    r = await client.put("/api/v1/settings", json={"rip": {"upload_concurrency": 99}}, headers=ah)
    assert r.status_code == 422
    r = await client.put("/api/v1/settings", json={"rip": {"bogus": 1}}, headers=ah)
    assert r.status_code == 422
    ok = {"rip": {"upload_concurrency": 8, "rate_limits": {"default": {"sleep_request": 2.0}}}}
    r = await client.put("/api/v1/settings", json=ok, headers=ah)
    assert r.status_code == 200
    assert r.json()["rip"]["upload_concurrency"] == 8


async def test_inconsistent_filters_422(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    tid = await _target(client, h)
    r = await client.post(
        "/api/v1/sources",
        json={**SRC, "target_id": tid, "filters": {"min_bytes": 10, "max_bytes": 5}},
        headers=h,
    )
    assert r.status_code == 422
