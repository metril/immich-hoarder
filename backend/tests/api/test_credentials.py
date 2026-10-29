import httpx
from helpers import actor

CRED = {"name": "c", "site": "reddit", "kind": "token", "secret": "s3cr3t-value"}


async def test_credential_secret_never_returned(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    r = await client.post("/api/v1/credentials", json=CRED, headers=h)
    assert r.status_code == 201 and r.json()["has_secret"] is True
    cid = r.json()["id"]
    outs = [
        r.text,
        (await client.get(f"/api/v1/credentials/{cid}", headers=h)).text,
        (await client.get("/api/v1/credentials", headers=h)).text,
        (await client.get(f"/api/v1/credentials/{cid}/shares", headers=h)).text,
    ]
    for o in outs:
        assert "s3cr3t-value" not in o
    p = await client.patch(f"/api/v1/credentials/{cid}", json={"secret": "new"}, headers=h)
    assert p.status_code == 200 and "new" not in p.text


async def test_credential_site_normalized_to_extractor_name(client: httpx.AsyncClient) -> None:
    _, h = await actor("n")
    r = await client.post(
        "/api/v1/credentials", json={**CRED, "site": "https://reddit.com"}, headers=h
    )
    assert r.status_code == 201 and r.json()["site"] == "reddit"
    cid = r.json()["id"]
    r = await client.patch(f"/api/v1/credentials/{cid}", json={"site": "WWW.Imgur.com/"}, headers=h)
    assert r.status_code == 200 and r.json()["site"] == "imgur"
