import httpx
from helpers import TARGET, actor
from test_target_immich import mount

from app.db.engine import session_scope
from app.db.models import Job, JobItem, JobStatus

A1 = "11111111-1111-1111-1111-111111111111"
A2 = "22222222-2222-2222-2222-222222222222"
A3 = "33333333-3333-3333-3333-333333333333"


async def _setup(c: httpx.AsyncClient, h: dict[str, str]) -> tuple[int, int]:
    tid = (await c.post("/api/v1/targets", json=TARGET, headers=h)).json()["id"]
    r = await c.post(
        "/api/v1/sources",
        json={"name": "s", "url": "https://www.reddit.com/r/pics/", "target_id": tid},
        headers=h,
    )
    return tid, r.json()["id"]


async def _items(sid: int, rows: list[tuple[str, str | None]]) -> int:
    async with session_scope() as s:
        j = Job(source_id=sid, status=JobStatus.succeeded)
        s.add(j)
        await s.flush()
        for outcome, aid in rows:
            s.add(JobItem(job_id=j.id, url="u", outcome=outcome, immich_asset_id=aid))
        return j.id


async def test_uploads_lists_visible_only(client: httpx.AsyncClient) -> None:
    _, ha = await actor("a")
    _, hb = await actor("b")
    tid, sid = await _setup(client, ha)
    jid = await _items(sid, [("uploaded", A1), ("skipped", None), ("linked", A2)])
    r = await client.get("/api/v1/uploads", headers=ha)
    assert r.status_code == 200
    items = r.json()["items"]
    assert [i["immich_asset_id"] for i in items] == [A2, A1]
    assert items[0]["job_id"] == jid and items[0]["source_id"] == sid
    assert items[0]["target_id"] == tid and items[0]["outcome"] == "linked"
    r = await client.get("/api/v1/uploads?limit=1", headers=ha)
    assert (
        len(
            (
                await client.get(f"/api/v1/uploads?cursor={r.json()['next_cursor']}", headers=ha)
            ).json()["items"]
        )
        == 1
    )
    assert (await client.get("/api/v1/uploads", headers=hb)).json()["items"] == []


def _thumb_handler(
    body: bytes = b"JPG", ctype: str = "image/jpeg", status: int = 200
) -> httpx.MockTransport:
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == f"/api/assets/{A1}/thumbnail"
        assert req.url.params["size"] == "preview"
        return httpx.Response(
            status, stream=httpx.ByteStream(body), headers={"content-type": ctype}
        )

    return httpx.MockTransport(handler)


async def test_thumbnail_proxied_with_cache_header(client: httpx.AsyncClient) -> None:
    mount(client, _thumb_handler())
    _, h = await actor("a")
    tid, sid = await _setup(client, h)
    await _items(sid, [("uploaded", A1)])
    r = await client.get(f"/api/v1/targets/{tid}/assets/{A1}/thumbnail?size=preview", headers=h)
    assert r.status_code == 200 and r.content == b"JPG"
    assert r.headers["content-type"] == "image/jpeg"
    assert r.headers["cache-control"] == "private, max-age=86400"
    assert r.headers["x-content-type-options"] == "nosniff"


async def test_thumbnail_arbitrary_asset_404(client: httpx.AsyncClient) -> None:
    mount(client, _thumb_handler())
    _, h = await actor("a")
    tid, sid = await _setup(client, h)
    await _items(sid, [("uploaded", A1)])
    r = await client.get(f"/api/v1/targets/{tid}/assets/{A3}/thumbnail", headers=h)
    assert r.status_code == 404
    r = await client.get(f"/api/v1/targets/{tid}/assets/not-a-uuid/thumbnail", headers=h)
    assert r.status_code == 422
    r = await client.get(f"/api/v1/targets/{tid}/assets/{A1}/thumbnail?size=big", headers=h)
    assert r.status_code == 422


async def test_thumbnail_requires_use_on_target(client: httpx.AsyncClient) -> None:
    mount(client, _thumb_handler())
    _, ha = await actor("a")
    _, hb = await actor("b")
    tid, sid = await _setup(client, ha)
    await _items(sid, [("uploaded", A1)])
    r = await client.get(f"/api/v1/targets/{tid}/assets/{A1}/thumbnail", headers=hb)
    assert r.status_code == 404


async def test_thumbnail_upstream_errors(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    tid, sid = await _setup(client, h)
    await _items(sid, [("uploaded", A1)])
    url = f"/api/v1/targets/{tid}/assets/{A1}/thumbnail?size=preview"
    mount(client, _thumb_handler(status=404))
    assert (await client.get(url, headers=h)).status_code == 404
    mount(client, _thumb_handler(ctype="text/html"))
    assert (await client.get(url, headers=h)).status_code == 502
    mount(client, _thumb_handler(body=b"x" * (5 * 1024 * 1024 + 1)))
    assert (await client.get(url, headers=h)).status_code == 502
    mount(client, _thumb_handler(status=401))
    r = await client.get(url, headers=h)
    assert r.status_code == 502 and r.json() == {"detail": "immich unauthorized"}


async def test_thumbnail_svg_rejected_and_params_stripped(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    tid, sid = await _setup(client, h)
    await _items(sid, [("uploaded", A1)])
    url = f"/api/v1/targets/{tid}/assets/{A1}/thumbnail?size=preview"
    mount(client, _thumb_handler(ctype="image/svg+xml"))
    assert (await client.get(url, headers=h)).status_code == 502
    mount(client, _thumb_handler(ctype="Image/JPEG; charset=x"))
    r = await client.get(url, headers=h)
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"


async def test_thumbnail_uppercase_id_finds_stored(client: httpx.AsyncClient) -> None:
    aid = "abcdefab-1111-1111-1111-111111111111"

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == f"/api/assets/{aid}/thumbnail"
        return httpx.Response(
            200, stream=httpx.ByteStream(b"J"), headers={"content-type": "image/jpeg"}
        )

    mount(client, httpx.MockTransport(handler))
    _, h = await actor("a")
    tid, sid = await _setup(client, h)
    await _items(sid, [("uploaded", aid)])
    r = await client.get(f"/api/v1/targets/{tid}/assets/{aid.upper()}/thumbnail", headers=h)
    assert r.status_code == 200


async def test_thumbnail_unshared_source_job_404(client: httpx.AsyncClient) -> None:
    mount(client, _thumb_handler())
    _, ha = await actor("a")
    ub, hb = await actor("b")
    tid, sid = await _setup(client, ha)
    body = {
        "visibility": "restricted",
        "shares": [{"principal_type": "user", "principal_id": str(ub), "perm": "use"}],
    }
    await client.put(f"/api/v1/targets/{tid}/shares", json=body, headers=ha)
    await _items(sid, [("uploaded", A1)])
    url = f"/api/v1/targets/{tid}/assets/{A1}/thumbnail?size=preview"
    assert (await client.get(url, headers=hb)).status_code == 404
    assert (await client.get(url, headers=ha)).status_code == 200


async def test_thumbnail_asset_from_other_target_404(client: httpx.AsyncClient) -> None:
    mount(client, _thumb_handler())
    _, h = await actor("a")
    t1, _ = await _setup(client, h)
    _, s2 = await _setup(client, h)
    await _items(s2, [("uploaded", A1)])
    r = await client.get(f"/api/v1/targets/{t1}/assets/{A1}/thumbnail?size=preview", headers=h)
    assert r.status_code == 404
