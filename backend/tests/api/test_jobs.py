from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from helpers import TARGET, actor, headers_for
from sqlalchemy import select

from app.core.config import Settings
from app.db import engine as dbe
from app.db.engine import session_scope
from app.db.models import Job, JobEvent, JobItem, JobStatus, Role, Source
from app.main import create_app
from app.runtime.bus import EventBus
from app.runtime.supervisor import JobSupervisor
from app.runtime.writer import JobWriter

SRC = {"name": "s", "url": "https://www.reddit.com/r/pics/"}


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    app: FastAPI = create_app(settings)
    app.state.runtime_enabled = False
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as c,
    ):
        sf = dbe._sessionmaker
        assert sf is not None
        app.state.supervisor = JobSupervisor(
            sf, JobWriter(sf, EventBus()), settings, mp_ctx=None, ipc_queue=None
        )
        yield c


async def _src(c: httpx.AsyncClient, h: dict[str, str], **kw: Any) -> int:
    tid = (await c.post("/api/v1/targets", json=TARGET, headers=h)).json()["id"]
    r = await c.post("/api/v1/sources", json={**SRC, "target_id": tid, **kw}, headers=h)
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


async def _finish(job_id: int, status: JobStatus = JobStatus.succeeded) -> None:
    async with session_scope() as s:
        j = await s.get(Job, job_id)
        assert j
        j.status = status


async def test_run_creates_job_202_and_conflict_409(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    sid = await _src(client, h)
    r = await client.post(f"/api/v1/sources/{sid}/run", json={"log_level": "debug"}, headers=h)
    assert r.status_code == 202
    j = r.json()
    assert j["source_id"] == sid and j["status"] == "queued" and j["log_level"] == "debug"
    assert j["source_name"] == "s"
    r = await client.post(f"/api/v1/sources/{sid}/run", headers=h)
    assert r.status_code == 409
    assert r.json() == {"detail": {"msg": "job already active", "job_id": j["id"]}}


async def test_run_requires_use(client: httpx.AsyncClient) -> None:
    _, ha = await actor("a")
    _, hb = await actor("b")
    sid = await _src(client, ha)
    assert (await client.post(f"/api/v1/sources/{sid}/run", headers=hb)).status_code == 404


async def test_scope_enforced_on_run(client: httpx.AsyncClient) -> None:
    uid, h = await actor("a")
    sid = await _src(client, h)
    ro = await headers_for(uid, ["jobs:read", "sources:read"])
    assert (await client.post(f"/api/v1/sources/{sid}/run", headers=ro)).status_code == 403
    assert (
        await client.post("/api/v1/rip", json={**SRC, "target_id": 1}, headers=ro)
    ).status_code == 403
    assert (await client.get("/api/v1/jobs", headers=await headers_for(uid, []))).status_code == 403


async def test_adhoc_rip_creates_ephemeral_source(client: httpx.AsyncClient) -> None:
    uid, h = await actor("a")
    tid = (await client.post("/api/v1/targets", json=TARGET, headers=h)).json()["id"]
    url = "https://www.reddit.com/r/pics/"
    r = await client.post(
        "/api/v1/rip",
        json={"url": url, "target_id": tid, "schedule_cron": "* * * * *", "log_level": "info"},
        headers=h,
    )
    assert r.status_code == 202, r.text
    sid = r.json()["source_id"]
    async with session_scope() as s:
        src = await s.get(Source, sid)
        assert src
        assert src.ephemeral and src.schedule_cron is None and src.owner_id == uid
        assert src.name == f"ad-hoc: {url}" and src.visibility == "private"
    bad = await client.post("/api/v1/rip", json={"url": "ftp://x", "target_id": tid}, headers=h)
    assert bad.status_code == 422


async def test_jobs_list_visibility(client: httpx.AsyncClient) -> None:
    uo, ho = await actor("owner")
    us, hs = await actor("sharee")
    _, hx = await actor("other")
    _, hadm = await actor("adm", Role.admin)
    sid = await _src(client, ho)
    body = {
        "visibility": "restricted",
        "shares": [{"principal_type": "user", "principal_id": str(us), "perm": "use"}],
    }
    assert (
        await client.put(f"/api/v1/sources/{sid}/shares", json=body, headers=ho)
    ).status_code == 200
    jid = (await client.post(f"/api/v1/sources/{sid}/run", headers=ho)).json()["id"]
    for h, n in ((ho, 1), (hs, 1), (hx, 0), (hadm, 1)):
        r = await client.get("/api/v1/jobs", headers=h)
        assert len(r.json()["items"]) == n
    assert (await client.get(f"/api/v1/jobs/{jid}", headers=hx)).status_code == 404
    assert (await client.get(f"/api/v1/jobs/{jid}", headers=hs)).status_code == 200
    r = await client.get(f"/api/v1/jobs?source_id={sid}&status=queued", headers=ho)
    assert len(r.json()["items"]) == 1
    r = await client.get("/api/v1/jobs?status=failed", headers=ho)
    assert r.json()["items"] == []


async def test_items_and_events_paginated_and_filtered(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    _, hx = await actor("x")
    sid = await _src(client, h)
    jid = (await client.post(f"/api/v1/sources/{sid}/run", headers=h)).json()["id"]
    async with session_scope() as s:
        for i in range(5):
            s.add(JobItem(job_id=jid, url=f"u{i}", outcome="uploaded" if i < 3 else "skipped"))
        for lv in ("trace", "debug", "info", "warn", "error"):
            s.add(JobEvent(job_id=jid, level=lv, type="t", data={}))
    r = await client.get(f"/api/v1/jobs/{jid}/items?limit=2", headers=h)
    d = r.json()
    assert len(d["items"]) == 2 and d["next_cursor"]
    r2 = await client.get(f"/api/v1/jobs/{jid}/items?limit=2&cursor={d['next_cursor']}", headers=h)
    assert [i["url"] for i in r2.json()["items"]] == ["u2", "u1"]
    r = await client.get(f"/api/v1/jobs/{jid}/items?outcome=skipped", headers=h)
    assert [i["url"] for i in r.json()["items"]] == ["u4", "u3"]
    r = await client.get(f"/api/v1/jobs/{jid}/events?min_level=warn", headers=h)
    assert [e["level"] for e in r.json()["items"]] == ["error", "warn"]
    r = await client.get(f"/api/v1/jobs/{jid}/events?limit=2", headers=h)
    assert len(r.json()["items"]) == 2 and r.json()["next_cursor"]
    assert (
        await client.get(f"/api/v1/jobs/{jid}/events?min_level=x", headers=h)
    ).status_code == 422
    assert (await client.get(f"/api/v1/jobs/{jid}/items", headers=hx)).status_code == 404
    assert (await client.get(f"/api/v1/jobs/{jid}/events", headers=hx)).status_code == 404


async def test_cancel_and_cancel_finished_409(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    _, hx = await actor("x")
    sid = await _src(client, h)
    jid = (await client.post(f"/api/v1/sources/{sid}/run", headers=h)).json()["id"]
    assert (await client.post(f"/api/v1/jobs/{jid}/cancel", headers=hx)).status_code == 404
    r = await client.post(f"/api/v1/jobs/{jid}/cancel", headers=h)
    assert r.status_code == 202 and r.json()["id"] == jid
    await _finish(jid)
    r = await client.post(f"/api/v1/jobs/{jid}/cancel", headers=h)
    assert r.status_code == 409 and r.json() == {"detail": "job not active"}


async def test_retry_creates_new_job(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    sid = await _src(client, h)
    jid = (await client.post(f"/api/v1/sources/{sid}/run", headers=h)).json()["id"]
    assert (await client.post(f"/api/v1/jobs/{jid}/retry", headers=h)).status_code == 409
    await _finish(jid, JobStatus.failed)
    r = await client.post(f"/api/v1/jobs/{jid}/retry", headers=h)
    assert r.status_code == 202 and r.json()["id"] != jid and r.json()["source_id"] == sid
    async with session_scope() as s:
        assert len((await s.execute(select(Job))).scalars().all()) == 2


async def test_runtime_unavailable_503(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    sid = await _src(client, h)
    client._transport.app.state.supervisor = None  # type: ignore[attr-defined]
    r = await client.post(f"/api/v1/sources/{sid}/run", headers=h)
    assert r.status_code == 503 and r.json() == {"detail": "runtime unavailable"}


async def test_rip_forces_private_visibility(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    tid = (await client.post("/api/v1/targets", json=TARGET, headers=h)).json()["id"]
    r = await client.post(
        "/api/v1/rip",
        json={"url": SRC["url"], "target_id": tid, "visibility": "everyone"},
        headers=h,
    )
    assert r.status_code == 202, r.text
    async with session_scope() as s:
        src = await s.get(Source, r.json()["source_id"])
        assert src and src.visibility == "private"


async def test_rip_cleans_up_source_when_enqueue_fails(client: httpx.AsyncClient) -> None:
    from sqlalchemy.exc import OperationalError

    class Boom:
        async def enqueue(self, *a: Any) -> None:
            raise OperationalError("x", {}, Exception("locked"))

    _, h = await actor("a")
    tid = (await client.post("/api/v1/targets", json=TARGET, headers=h)).json()["id"]
    client._transport.app.state.supervisor = Boom()  # type: ignore[attr-defined]
    with pytest.raises(OperationalError):
        await client.post("/api/v1/rip", json={"url": SRC["url"], "target_id": tid}, headers=h)
    async with session_scope() as s:
        assert (await s.execute(select(Source))).first() is None


async def test_cancel_requires_jobs_write(client: httpx.AsyncClient) -> None:
    uid, h = await actor("a")
    sid = await _src(client, h)
    jid = (await client.post(f"/api/v1/sources/{sid}/run", headers=h)).json()["id"]
    ro = await headers_for(uid, ["jobs:read"])
    assert (await client.post(f"/api/v1/jobs/{jid}/cancel", headers=ro)).status_code == 403


async def test_rip_with_foreign_private_credential_403(client: httpx.AsyncClient) -> None:
    _, ha = await actor("a")
    _, hb = await actor("b")
    cid = (
        await client.post(
            "/api/v1/credentials",
            json={"name": "c", "site": "reddit", "kind": "cookies", "secret": "s3"},
            headers=ha,
        )
    ).json()["id"]
    tid = (await client.post("/api/v1/targets", json=TARGET, headers=hb)).json()["id"]
    r = await client.post(
        "/api/v1/rip",
        json={"url": SRC["url"], "target_id": tid, "credential_id": cid},
        headers=hb,
    )
    assert r.status_code == 403


async def test_retry_invisible_job_404(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    _, hx = await actor("x")
    sid = await _src(client, h)
    jid = (await client.post(f"/api/v1/sources/{sid}/run", headers=h)).json()["id"]
    await _finish(jid)
    assert (await client.post(f"/api/v1/jobs/{jid}/retry", headers=hx)).status_code == 404


async def test_lists_are_newest_first(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    sid = await _src(client, h)
    j1 = (await client.post(f"/api/v1/sources/{sid}/run", headers=h)).json()["id"]
    await _finish(j1)
    j2 = (await client.post(f"/api/v1/sources/{sid}/run", headers=h)).json()["id"]
    r = await client.get("/api/v1/jobs?limit=1", headers=h)
    assert [j["id"] for j in r.json()["items"]] == [j2] and r.json()["next_cursor"]
    r = await client.get(f"/api/v1/jobs?limit=1&cursor={r.json()['next_cursor']}", headers=h)
    assert [j["id"] for j in r.json()["items"]] == [j1]
    async with session_scope() as s:
        for i in range(3):
            s.add(JobItem(job_id=j2, url=f"u{i}", outcome="uploaded"))
            s.add(JobEvent(job_id=j2, level="info", type="t", data={}))
    for kind in ("items", "events"):
        r = await client.get(f"/api/v1/jobs/{j2}/{kind}?limit=2", headers=h)
        ids = [i["id"] for i in r.json()["items"]]
        assert ids == sorted(ids, reverse=True) and r.json()["next_cursor"]
        r = await client.get(
            f"/api/v1/jobs/{j2}/{kind}?limit=2&cursor={r.json()['next_cursor']}", headers=h
        )
        assert len(r.json()["items"]) == 1


async def test_rip_keeps_source_when_failure_is_after_enqueue(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api.v1 import jobs as jobs_api

    async def boom(*a: Any) -> None:
        raise RuntimeError("response building failed")

    monkeypatch.setattr(jobs_api, "_out", boom)
    _, h = await actor("a")
    tid = (await client.post("/api/v1/targets", json=TARGET, headers=h)).json()["id"]
    with pytest.raises(RuntimeError):
        await client.post("/api/v1/rip", json={"url": SRC["url"], "target_id": tid}, headers=h)
    async with session_scope() as s:
        assert (await s.execute(select(Source))).first() is not None
        assert (await s.execute(select(Job))).first() is not None


async def test_rip_disconnect_after_commit_keeps_live_source(
    client: httpx.AsyncClient,
) -> None:
    import asyncio

    import anyio

    app = client._transport.app  # type: ignore[attr-defined]
    real = app.state.supervisor
    scope = anyio.CancelScope()
    started = asyncio.Event()

    class Slow:
        async def enqueue(self, *a: Any) -> Any:
            started.set()
            await asyncio.sleep(0.3)  # the client disconnects meanwhile
            return await real.enqueue(*a)

    app.state.supervisor = Slow()
    _, h = await actor("a")
    tid = (await client.post("/api/v1/targets", json=TARGET, headers=h)).json()["id"]

    async def post() -> None:
        with scope:
            await client.post("/api/v1/rip", json={"url": SRC["url"], "target_id": tid}, headers=h)

    task = asyncio.create_task(post())
    await asyncio.wait_for(started.wait(), 10)
    scope.cancel()
    await asyncio.wait_for(task, 10)
    async with session_scope() as s:
        assert (await s.execute(select(Source))).first() is not None
        assert (await s.execute(select(Job))).first() is not None


async def test_delete_source_blocked_by_active_job(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    sid = await _src(client, h)
    r = await client.post(f"/api/v1/sources/{sid}/run", headers=h)
    jid = r.json()["id"]
    d = await client.delete(f"/api/v1/sources/{sid}", headers=h)
    assert d.status_code == 409 and d.json() == {"detail": "source has an active job"}
    await _finish(jid, JobStatus.running)
    assert (await client.delete(f"/api/v1/sources/{sid}", headers=h)).status_code == 409
    await _finish(jid)
    assert (await client.delete(f"/api/v1/sources/{sid}", headers=h)).status_code == 204


async def test_run_conflict_409_includes_job_id(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    sid = await _src(client, h)
    jid = (await client.post(f"/api/v1/sources/{sid}/run", headers=h)).json()["id"]
    r = await client.post(f"/api/v1/jobs/{jid}/retry", headers=h)
    assert r.status_code == 409 and r.json()["detail"] == {
        "msg": "job already active",
        "job_id": jid,
    }


async def test_enqueue_integrity_race_returns_409(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sqlalchemy as sa

    from app.runtime import supervisor as sup_mod

    _, h = await actor("a")
    sid = await _src(client, h)
    jid = (await client.post(f"/api/v1/sources/{sid}/run", headers=h)).json()["id"]
    real = sup_mod.select
    calls = 0

    def blind_first(*a: Any) -> Any:  # the pre-check misses, so the unique index fires
        nonlocal calls
        calls += 1
        q = real(*a)
        return q.where(sa.false()) if calls == 1 else q

    monkeypatch.setattr(sup_mod, "select", blind_first)
    r = await client.post(f"/api/v1/sources/{sid}/run", headers=h)
    assert r.status_code == 409
    assert r.json()["detail"] == {"msg": "job already active", "job_id": jid}


async def test_get_job_returns_phase(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    sid = await _src(client, h)
    jid = (await client.post(f"/api/v1/sources/{sid}/run", headers=h)).json()["id"]
    assert (await client.get(f"/api/v1/jobs/{jid}", headers=h)).json()["phase"] is None
    async with session_scope() as s:
        j = await s.get(Job, jid)
        assert j
        j.phase = "draining"
    assert (await client.get(f"/api/v1/jobs/{jid}", headers=h)).json()["phase"] == "draining"
