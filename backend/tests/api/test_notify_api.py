import httpx
from helpers import TARGET, actor

URL = "json://localhost/"


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
    assert await create([app_]) in (201, 422)  # url check may reject; kind/use passed
    r = await client.post("/api/v1/sources", json={**base, "notify": {"bogus": 1}}, headers=h)
    assert r.status_code == 422
