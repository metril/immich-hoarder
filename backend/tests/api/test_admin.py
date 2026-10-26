import httpx
from helpers import actor, headers_for

from app.db.models import Role


async def test_admin_endpoints_admin_only(client: httpx.AsyncClient) -> None:
    _, h = await actor("u")
    for m, path in (
        ("POST", "/api/v1/admin/backup"),
        ("GET", "/api/v1/admin/backups"),
        ("POST", "/api/v1/admin/maintenance/prune"),
    ):
        assert (await client.request(m, path, headers=h)).status_code == 403
    aid, _ = await actor("adm", Role.admin)
    ha = await headers_for(aid)
    hn = await headers_for(aid, ["sources:read"])  # admin role, no admin scope
    assert (await client.post("/api/v1/admin/backup", headers=hn)).status_code == 403
    r = await client.post("/api/v1/admin/backup", headers=ha)
    assert r.status_code == 201 and r.json()["file"].startswith("hoarder-")
    lst = (await client.get("/api/v1/admin/backups", headers=ha)).json()
    assert [i["file"] for i in lst["items"]] == [r.json()["file"]]
    assert lst["items"][0]["size"] > 0 and "mtime" in lst["items"][0]
    p = await client.post("/api/v1/admin/maintenance/prune", headers=ha)
    assert p.status_code == 200 and p.json() == {"jobs": 0, "ephemeral_sources": 0}
