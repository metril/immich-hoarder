import httpx
import pytest
from helpers import TARGET, actor

SRC = {"name": "s", "url": "https://www.reddit.com/r/pics/"}


async def _target(c: httpx.AsyncClient, h: dict[str, str]) -> int:
    return (await c.post("/api/v1/targets", json=TARGET, headers=h)).json()["id"]


async def test_source_requires_use_on_target(client: httpx.AsyncClient) -> None:
    _, ha = await actor("a")
    ub, hb = await actor("b")
    tid = await _target(client, ha)
    r = await client.post("/api/v1/sources", json={**SRC, "target_id": tid}, headers=hb)
    assert r.status_code == 403
    body = {
        "visibility": "restricted",
        "shares": [{"principal_type": "user", "principal_id": str(ub), "perm": "use"}],
    }
    assert (
        await client.put(f"/api/v1/targets/{tid}/shares", json=body, headers=ha)
    ).status_code == 200
    r = await client.post("/api/v1/sources", json={**SRC, "target_id": tid}, headers=hb)
    assert r.status_code == 201


@pytest.mark.parametrize("bad", ["nope", "0 3 * *", "0 0 31 2 *", "0 3 * * * *"])
async def test_invalid_cron_422(client: httpx.AsyncClient, bad: str) -> None:
    _, h = await actor("a")
    tid = await _target(client, h)
    r = await client.post(
        "/api/v1/sources", json={**SRC, "target_id": tid, "schedule_cron": bad}, headers=h
    )
    assert r.status_code == 422


async def test_bad_album_template_field_422(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    tid = await _target(client, h)
    ok = await client.post(
        "/api/v1/sources",
        json={**SRC, "target_id": tid, "album_template": "{subreddit}-{date}"},
        headers=h,
    )
    assert ok.status_code == 201
    r = await client.post(
        "/api/v1/sources",
        json={**SRC, "target_id": tid, "album_template": "{bogus}"},
        headers=h,
    )
    assert r.status_code == 422


async def test_scope_enforced(client: httpx.AsyncClient) -> None:
    from helpers import headers_for

    uid, full = await actor("a")
    tid = await _target(client, full)
    h = await headers_for(uid, ["sources:read"])
    r = await client.post("/api/v1/sources", json={**SRC, "target_id": tid}, headers=h)
    assert r.status_code == 403
    assert (await client.get("/api/v1/sources", headers=h)).status_code == 200
    ok = await client.post("/api/v1/sources", json={**SRC, "target_id": tid}, headers=full)
    assert ok.status_code == 201


async def test_disabled_owner_blocks_source_update(client: httpx.AsyncClient) -> None:
    from helpers import make_user

    from app.db.models import Role

    ua, ha = await actor("a")
    _, hadm = await actor("adm", Role.admin)
    await make_user("adm2", Role.admin)
    tid = await _target(client, ha)
    sid = (await client.post("/api/v1/sources", json={**SRC, "target_id": tid}, headers=ha)).json()[
        "id"
    ]
    await client.patch(f"/api/v1/users/{ua}", json={"disabled": True}, headers=hadm)
    r = await client.patch(f"/api/v1/sources/{sid}", json={"name": "n"}, headers=hadm)
    assert r.status_code == 403


async def test_ephemeral_hidden(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    tid = await _target(client, h)
    await client.post(
        "/api/v1/sources", json={**SRC, "target_id": tid, "ephemeral": True}, headers=h
    )
    assert (await client.get("/api/v1/sources", headers=h)).json()["items"] == []
    r = await client.get("/api/v1/sources?include_ephemeral=true", headers=h)
    assert len(r.json()["items"]) == 1


@pytest.mark.parametrize("tpl", ["{user.name}", "{user[0]}", "{user!r}", "{user:>10}", "{user"])
async def test_unsupported_album_template_syntax_422(client: httpx.AsyncClient, tpl: str) -> None:
    _, h = await actor("a")
    tid = await _target(client, h)
    r = await client.post(
        "/api/v1/sources", json={**SRC, "target_id": tid, "album_template": tpl}, headers=h
    )
    assert r.status_code == 422


class _FakeSched:
    def __init__(self, fail: bool = False) -> None:
        self.calls: list[int] = []
        self.fail = fail

    async def sync_source(self, source_id: int) -> None:
        self.calls.append(source_id)
        if self.fail:
            raise RuntimeError("boom")


async def test_source_writes_sync_scheduler(client: httpx.AsyncClient) -> None:
    sched = _FakeSched()
    client._transport.app.state.scheduler = sched  # type: ignore[attr-defined]
    _, h = await actor("a")
    tid = await _target(client, h)
    r = await client.post("/api/v1/sources", json={**SRC, "target_id": tid}, headers=h)
    sid = r.json()["id"]
    assert sched.calls == [sid]
    assert (
        await client.patch(f"/api/v1/sources/{sid}", json={"name": "x"}, headers=h)
    ).status_code == 200
    assert sched.calls == [sid, sid]
    assert (await client.delete(f"/api/v1/sources/{sid}", headers=h)).status_code == 204
    assert sched.calls == [sid, sid, sid]


async def test_scheduler_failure_does_not_500(client: httpx.AsyncClient) -> None:
    client._transport.app.state.scheduler = _FakeSched(fail=True)  # type: ignore[attr-defined]
    _, h = await actor("a")
    tid = await _target(client, h)
    r = await client.post("/api/v1/sources", json={**SRC, "target_id": tid}, headers=h)
    assert r.status_code == 201
    assert (await client.get(f"/api/v1/sources/{r.json()['id']}", headers=h)).status_code == 200


async def _seen(sid: int, tid: int, n: int, sha1: bytes | None = None) -> None:
    from app.db.engine import session_scope
    from app.db.models import AssetSeen

    async with session_scope() as s:
        for i in range(n):
            s.add(
                AssetSeen(
                    target_id=tid,
                    source_id=sid,
                    url_hash=bytes([i]) * 16,
                    sha1=sha1,
                    seen_at=1,
                )
            )


async def _count(sid: int | None) -> int:
    from sqlalchemy import func, select

    from app.db.engine import session_scope
    from app.db.models import AssetSeen

    async with session_scope() as s:
        cond = AssetSeen.source_id.is_(None) if sid is None else AssetSeen.source_id == sid
        return int(await s.scalar(select(func.count()).select_from(AssetSeen).where(cond)) or 0)


async def _mk(c: httpx.AsyncClient, h: dict[str, str], tid: int) -> int:
    r = await c.post("/api/v1/sources", json={**SRC, "target_id": tid}, headers=h)
    return int(r.json()["id"])


async def test_forget_seen_detaches_only_this_source(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    tid = await _target(client, h)
    s1, s2 = await _mk(client, h, tid), await _mk(client, h, tid)
    await _seen(s1, tid, 3, sha1=b"s" * 20)
    await _seen(s2, tid, 2)
    r = await client.post(f"/api/v1/sources/{s1}/forget-seen", headers=h)
    assert r.status_code == 200 and r.json() == {"forgotten": 3}
    assert await _count(s1) == 0 and await _count(s2) == 2
    assert await _count(None) == 3  # rows kept (sha1 dedupe intact)
    r = await client.post(f"/api/v1/sources/{s1}/forget-seen", headers=h)
    assert r.json() == {"forgotten": 0}


async def test_forget_seen_permissions_and_404(client: httpx.AsyncClient) -> None:
    _, ha = await actor("a")
    _, hb = await actor("b")
    tid = await _target(client, ha)
    sid = await _mk(client, ha, tid)
    assert (await client.post(f"/api/v1/sources/{sid}/forget-seen", headers=hb)).status_code in (
        403,
        404,
    )
    assert (await client.post("/api/v1/sources/9999/forget-seen", headers=ha)).status_code == 404


async def test_forget_seen_409_with_active_job(client: httpx.AsyncClient) -> None:
    from app.db.engine import session_scope
    from app.db.models import Job, JobStatus

    _, h = await actor("a")
    tid = await _target(client, h)
    sid = await _mk(client, h, tid)
    await _seen(sid, tid, 1)
    async with session_scope() as s:
        s.add(Job(source_id=sid, status=JobStatus.queued))
    r = await client.post(f"/api/v1/sources/{sid}/forget-seen", headers=h)
    assert r.status_code == 409
    assert await _count(sid) == 1


async def test_reupload_deleted_round_trip(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    tid = await _target(client, h)
    r = await client.post("/api/v1/sources", json={**SRC, "target_id": tid}, headers=h)
    assert r.json()["reupload_deleted"] is False
    sid = r.json()["id"]
    r = await client.patch(f"/api/v1/sources/{sid}", json={"reupload_deleted": True}, headers=h)
    assert r.json()["reupload_deleted"] is True
    r = await client.post(
        "/api/v1/sources", json={**SRC, "target_id": tid, "reupload_deleted": True}, headers=h
    )
    assert r.json()["reupload_deleted"] is True
