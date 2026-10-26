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


async def test_put_runtime_settings_reschedules_backup(client: httpx.AsyncClient) -> None:
    from types import SimpleNamespace

    calls: list[int] = []

    class FakeSched:
        async def sync_maintenance(self) -> None:
            calls.append(1)
            if len(calls) == 2:
                raise RuntimeError("boom")

    client._transport.app.state.scheduler = FakeSched()  # type: ignore[attr-defined]
    _ = SimpleNamespace
    aid, _h = await actor("adm", Role.admin)
    ha = await headers_for(aid)
    r = await client.put(
        "/api/v1/settings", json={"runtime": {"backup_cron": "5 1 * * *"}}, headers=ha
    )
    assert r.status_code == 200 and calls == [1]
    await client.put("/api/v1/settings", json={"notify": {"on": ["success"]}}, headers=ha)
    assert calls == [1]
    r = await client.put("/api/v1/settings", json={"runtime": {"retention_days": 9}}, headers=ha)
    assert r.status_code == 200 and calls == [1, 1]
