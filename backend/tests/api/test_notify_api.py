import httpx
from helpers import TARGET, actor

from app.db.models import Role

URL = "json://example.com/"


async def test_source_notify_requires_apprise_kind_and_use(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    _, h2 = await actor("b")
    tid = (await client.post("/api/v1/targets", json=TARGET, headers=h)).json()["id"]
    base = {"name": "s", "url": "http://x/a.jpg", "target_id": tid}

    def cred(kind: str) -> dict[str, str]:
        return {"name": "c", "site": "notify", "kind": kind, "secret": URL}

    tok = (await client.post("/api/v1/credentials", json=cred("token"), headers=h)).json()["id"]
    app_ = (await client.post("/api/v1/credentials", json=cred("apprise"), headers=h)).json()["id"]
    other = (await client.post("/api/v1/credentials", json=cred("apprise"), headers=h2)).json()[
        "id"
    ]

    async def create(ids: list[int]) -> int:
        body = {**base, "notify": {"credential_ids": ids, "on": ["failure"]}}
        return (await client.post("/api/v1/sources", json=body, headers=h)).status_code

    assert await create([tok]) == 422
    assert await create([other]) == 403
    assert await create([app_]) == 201
    r = await client.post("/api/v1/sources", json={**base, "notify": {"bogus": 1}}, headers=h)
    assert r.status_code == 422


async def test_source_notify_patch_path(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    tid = (await client.post("/api/v1/targets", json=TARGET, headers=h)).json()["id"]
    sid = (
        await client.post(
            "/api/v1/sources",
            json={"name": "s", "url": "http://x/a.jpg", "target_id": tid},
            headers=h,
        )
    ).json()["id"]
    tok = (
        await client.post(
            "/api/v1/credentials",
            json={"name": "c", "site": "n", "kind": "token", "secret": URL},
            headers=h,
        )
    ).json()["id"]
    r = await client.patch(
        f"/api/v1/sources/{sid}", json={"notify": {"credential_ids": [tok]}}, headers=h
    )
    assert r.status_code == 422


async def test_apprise_credential_ssrf(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    _, ah = await actor("adm", Role.admin)

    def body(secret: str) -> dict[str, str]:
        return {"name": "c", "site": "n", "kind": "apprise", "secret": secret}

    for bad in ("json://10.0.0.1/", "json://169.254.169.254", "garbage"):
        r = await client.post("/api/v1/credentials", json=body(bad), headers=h)
        assert r.status_code == 422, bad
        assert bad not in r.text
    cid = (await client.post("/api/v1/credentials", json=body(URL), headers=h)).json()["id"]
    r = await client.patch(
        f"/api/v1/credentials/{cid}", json={"secret": "json://10.0.0.1/"}, headers=h
    )
    assert r.status_code == 422
    await client.put("/api/v1/settings", json={"rip": {"allow_private_hosts": True}}, headers=ah)
    r = await client.post("/api/v1/credentials", json=body("json://10.0.0.1/"), headers=h)
    assert r.status_code == 201
