import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from helpers import actor
from sqlalchemy import delete

from app.api.v1 import streams
from app.api.v1.streams import (
    dashboard_stream,
    job_source_id,
    job_stream,
    job_visible,
    visible_source_ids,
)
from app.auth.principal import Principal
from app.core.config import Settings
from app.db.engine import session_scope
from app.db.models import (
    ImmichTarget,
    Job,
    JobEvent,
    JobItem,
    JobStatus,
    Perm,
    PrincipalType,
    Role,
    Share,
    Source,
    Visibility,
)
from app.main import create_app
from app.runtime.bus import EventBus


@pytest.fixture
async def env(settings: Settings) -> AsyncIterator[tuple[FastAPI, httpx.AsyncClient]]:
    app = create_app(settings)
    app.state.runtime_enabled = False
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as c,
    ):
        yield app, c


async def _job(
    owner: int,
    status: JobStatus = JobStatus.running,
    vis: Visibility = Visibility.private,
    with_rows: bool = True,
) -> int:
    async with session_scope() as s:
        t = ImmichTarget(name="t", url="http://i", owner_id=owner, api_key_enc=b"x")
        s.add(t)
        await s.flush()
        src = Source(
            name="s",
            url="https://x/",
            extractor="gdl",
            visibility=vis,
            owner_id=owner,
            target_id=t.id,
        )
        s.add(src)
        await s.flush()
        j = Job(source_id=src.id, status=status, counters={"downloaded": 3})
        s.add(j)
        await s.flush()
        if with_rows:
            s.add(
                JobEvent(job_id=j.id, level="info", type="log", data={"type": "log", "msg": "hi"})
            )
            s.add(
                JobItem(job_id=j.id, url="u1", outcome="linked", reason=None, immich_asset_id="a1")
            )
        return j.id


async def _get(job_id: int) -> Job:
    async with session_scope() as s:
        j = await s.get(Job, job_id)
        assert j
        return j


async def _finish(job_id: int) -> None:
    async with session_scope() as s:
        j = await s.get(Job, job_id)
        assert j
        j.status = JobStatus.succeeded


async def _never() -> bool:
    return False


async def _take(gen: Any, n: int) -> list[dict[str, Any]]:
    out = []
    async with asyncio.timeout(5):
        while len(out) < n:
            out.append(await gen.__anext__())
    return out


async def test_job_stream_replays_then_live_then_end(env: Any) -> None:
    uid, _ = await actor("a")
    job = await _get(await _job(uid))
    bus = EventBus()
    gen = job_stream(bus, session_scope, job, _never)
    replay = await _take(gen, 4)
    assert [e["event"] for e in replay] == ["log", "item.linked", "progress", "status"]
    assert json.loads(replay[1]["data"]) == {
        "type": "item.linked",
        "id": 1,
        "job_id": job.id,
        "url": "u1",
        "reason": None,
        "immich_asset_id": "a1",
    }
    assert json.loads(replay[2]["data"]) == {"type": "progress", "counters": {"downloaded": 3}}
    assert json.loads(replay[3]["data"]) == {
        "type": "status",
        "job_id": job.id,
        "status": "running",
    }
    assert bus.subscriber_count(job.id) == 1
    bus.publish(job.id, {"type": "log", "msg": "live"})
    bus.publish(job.id, {"type": "status", "status": "succeeded"})
    rest = [e async for e in gen]
    assert [e["event"] for e in rest] == ["log", "status", "end"]
    assert bus.subscriber_count(job.id) == 0


async def test_terminal_job_replays_and_ends(env: Any) -> None:
    uid, _ = await actor("a")
    job = await _get(await _job(uid, JobStatus.succeeded))
    bus = EventBus()
    evs = [e async for e in job_stream(bus, session_scope, job, _never)]
    assert evs[-1]["event"] == "end"
    assert bus.subscriber_count(job.id) == 0


async def test_disconnect_removes_subscriber(env: Any) -> None:
    uid, _ = await actor("a")
    job = await _get(await _job(uid))
    bus = EventBus()
    flag = {"gone": False}

    async def gone() -> bool:
        return flag["gone"]

    gen = job_stream(bus, session_scope, job, gone)
    await _take(gen, 4)
    assert bus.subscriber_count(job.id) == 1
    flag["gone"] = True
    async with asyncio.timeout(5):
        assert [e async for e in gen] == []
    assert bus.subscriber_count(job.id) == 0
    # explicit aclose also cleans up
    gen2 = job_stream(bus, session_scope, job, _never)
    await _take(gen2, 1)
    await gen2.aclose()
    assert bus.subscriber_count(job.id) == 0


async def test_dashboard_filters_invisible_jobs(env: Any) -> None:
    bus = EventBus()
    sources = {1: 10, 2: 20}

    async def visible() -> set[int] | None:
        return {10}

    async def src(job_id: int) -> int | None:
        return sources.get(job_id)

    gen = dashboard_stream(bus, visible, src, _never)
    task = asyncio.ensure_future(_take(gen, 2))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert bus.subscriber_count(None) == 1
    bus.publish(2, {"type": "status", "status": "running"})
    bus.publish(1, {"type": "log", "msg": "x"})
    bus.publish(1, {"type": "progress", "counters": {"a": 1}})
    bus.publish(2, {"type": "progress", "counters": {"a": 1}})
    bus.publish(1, {"type": "status", "status": "running"})
    got = await task
    assert [(e["event"], json.loads(e["data"])["job_id"]) for e in got] == [
        ("progress", 1),
        ("status", 1),
    ]
    await gen.aclose()
    assert bus.subscriber_count(None) == 0


async def test_stream_visibility_404(env: tuple[FastAPI, httpx.AsyncClient]) -> None:
    app, c = env
    owner, _ = await actor("a")
    _, other = await actor("b")
    jid = await _job(owner)
    app.state.bus = EventBus()
    assert (await c.get(f"/api/v1/jobs/{jid}/stream", headers=other)).status_code == 404


async def test_stream_503_without_bus(env: tuple[FastAPI, httpx.AsyncClient]) -> None:
    _, c = env
    _, h = await actor("a")
    assert (await c.get("/api/v1/jobs/1/stream", headers=h)).status_code == 503
    assert (await c.get("/api/v1/jobs/stream", headers=h)).status_code == 503


async def test_endpoint_streams_until_end(env: tuple[FastAPI, httpx.AsyncClient]) -> None:
    app, c = env
    uid, h = await actor("a")
    jid = await _job(uid, JobStatus.succeeded)
    app.state.bus = EventBus()
    lines: list[str] = []
    async with asyncio.timeout(5):
        async with c.stream("GET", f"/api/v1/jobs/{jid}/stream", headers=h) as r:
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("text/event-stream")
            async for line in r.aiter_lines():
                lines.append(line)
                if line == "event: end":
                    break
    assert "event: item.linked" in lines
    assert app.state.bus.subscriber_count(jid) == 0


def _principal(uid: int, role: Role = Role.user) -> Principal:
    return Principal(user_id=uid, role=role, groups=frozenset(), scopes=None)


async def _share(source_id: int, uid: int) -> None:
    async with session_scope() as s:
        s.add(
            Share(
                resource_type="source",
                resource_id=source_id,
                principal_type=PrincipalType.user,
                principal_id=str(uid),
                perm=Perm.use,
            )
        )


async def _src_of(job_id: int) -> int:
    sid = await job_source_id(job_id)
    assert sid is not None
    return sid


async def test_visibility_matrix_db_backed(env: Any) -> None:
    owner, _ = await actor("o")
    grantee, _ = await actor("g")
    stranger, _ = await actor("s")
    admin, _ = await actor("adm", Role.admin)
    j_shared = await _job(owner, vis=Visibility.restricted)
    j_priv = await _job(owner)
    s_shared, s_priv = await _src_of(j_shared), await _src_of(j_priv)
    await _share(s_shared, grantee)
    assert await visible_source_ids(_principal(owner)) == {s_shared, s_priv}
    assert await visible_source_ids(_principal(grantee)) == {s_shared}
    assert await visible_source_ids(_principal(stranger)) == set()
    assert await visible_source_ids(_principal(admin, Role.admin)) is None
    assert await job_visible(_principal(grantee), j_shared)
    assert not await job_visible(_principal(grantee), j_priv)
    assert not await job_visible(_principal(stranger), j_shared)
    assert await job_visible(_principal(admin, Role.admin), j_priv)
    # end-to-end through the real functions for the grantee
    bus = EventBus()
    p = _principal(grantee)

    async def vis() -> set[int] | None:
        return await visible_source_ids(p)

    gen = dashboard_stream(bus, vis, job_source_id, _never)
    task = asyncio.ensure_future(_take(gen, 1))
    await asyncio.sleep(0.05)
    bus.publish(j_priv, {"type": "status", "status": "running"})
    bus.publish(j_shared, {"type": "status", "status": "running"})
    got = await task
    assert json.loads(got[0]["data"])["job_id"] == j_shared
    await gen.aclose()


async def test_job_stream_ends_when_visibility_revoked(
    env: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(streams, "VISIBLE_TTL", 0.05)
    owner, _ = await actor("o")
    grantee, _ = await actor("g")
    jid = await _job(owner, vis=Visibility.restricted)
    await _share(await _src_of(jid), grantee)
    job = await _get(jid)
    p = _principal(grantee)

    async def still() -> bool:
        return await job_visible(p, jid)

    bus = EventBus()
    gen = job_stream(bus, session_scope, job, _never, still)
    await _take(gen, 4)
    async with session_scope() as s:
        await s.execute(delete(Share))
    async with asyncio.timeout(5):
        rest = [e async for e in gen]
    assert [e["event"] for e in rest] == ["end"]
    assert bus.subscriber_count(jid) == 0


async def test_event_published_during_replay_is_delivered(env: Any) -> None:
    uid, _ = await actor("a")
    job = await _get(await _job(uid))
    bus = EventBus()

    @asynccontextmanager
    async def factory() -> AsyncIterator[Any]:
        async with session_scope() as s:
            yield s
            bus.publish(job.id, {"type": "log", "msg": "mid-replay"})

    gen = job_stream(bus, factory, job, _never)
    evs = await _take(gen, 5)
    assert evs[4]["event"] == "log" and "mid-replay" in evs[4]["data"]
    await gen.aclose()


async def test_job_gap_rechecks_status(env: Any) -> None:
    uid, _ = await actor("a")
    jid = await _job(uid)
    job = await _get(jid)
    bus = EventBus()
    gen = job_stream(bus, session_scope, job, _never)
    await _take(gen, 4)
    await _finish(jid)
    bus.publish(jid, {"type": "gap"})
    async with asyncio.timeout(5):
        rest = [e async for e in gen]
    assert [e["event"] for e in rest] == ["gap", "end"]


async def test_dashboard_forwards_gap(env: Any) -> None:
    bus = EventBus()

    async def visible() -> set[int] | None:
        return set()

    async def src(job_id: int) -> int | None:
        return None

    gen = dashboard_stream(bus, visible, src, _never)
    task = asyncio.ensure_future(_take(gen, 1))
    await asyncio.sleep(0.05)
    bus.publish(None, {"type": "gap"})
    assert (await task)[0]["event"] == "gap"
    await gen.aclose()


async def test_stream_cap_429(env: tuple[FastAPI, httpx.AsyncClient]) -> None:
    app, c = env
    uid, h = await actor("a")
    jid = await _job(uid, JobStatus.succeeded)
    app.state.bus = EventBus()
    streams._active[uid] = streams.MAX_STREAMS
    r = await c.get(f"/api/v1/jobs/{jid}/stream", headers=h)
    assert r.status_code == 429 and r.json() == {"detail": "too many streams"}
    r = await c.get("/api/v1/jobs/stream", headers=h)
    assert r.status_code == 429
    streams._active[uid] = streams.MAX_STREAMS - 1
    async with c.stream("GET", f"/api/v1/jobs/{jid}/stream", headers=h) as r:
        assert r.status_code == 200
        async for line in r.aiter_lines():
            if line == "event: end":
                break
    assert streams._active.get(uid, 0) == streams.MAX_STREAMS - 1


@pytest.fixture(autouse=True)
def _reset_active() -> Any:
    streams._active.clear()
    yield
    streams._active.clear()


async def test_slot_released_when_cancelled_before_stream_starts() -> None:
    async def gen() -> Any:
        yield {"event": "x", "data": "{}"}

    release = streams._acquire(42)
    assert streams._active == {42: 1}
    resp = streams._stream_response(gen(), release)

    async def receive() -> dict[str, Any]:
        await asyncio.sleep(60)
        return {}

    async def send(_m: Any) -> None:
        raise asyncio.CancelledError  # cancelled before the generator ever runs

    scope = {"type": "http", "method": "GET", "headers": [], "asgi": {"spec_version": "2.3"}}
    try:
        await resp(scope, receive, send)
    except asyncio.CancelledError:
        pass
    assert streams._active == {}
