import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from helpers import actor

from app.api.v1.streams import dashboard_stream, job_stream
from app.core.config import Settings
from app.db.engine import session_scope
from app.db.models import ImmichTarget, Job, JobEvent, JobItem, JobStatus, Source
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


async def _job(owner: int, status: JobStatus = JobStatus.running) -> int:
    async with session_scope() as s:
        t = ImmichTarget(name="t", url="http://i", owner_id=owner, api_key_enc=b"x")
        s.add(t)
        await s.flush()
        src = Source(name="s", url="https://x/", extractor="gdl", owner_id=owner, target_id=t.id)
        s.add(src)
        await s.flush()
        j = Job(source_id=src.id, status=status, counters={"downloaded": 3})
        s.add(j)
        await s.flush()
        s.add(JobEvent(job_id=j.id, level="info", type="log", data={"type": "log", "msg": "hi"}))
        s.add(JobItem(job_id=j.id, url="u1", outcome="linked", reason=None, immich_asset_id="a1"))
        return j.id


async def _get(job_id: int) -> Job:
    async with session_scope() as s:
        j = await s.get(Job, job_id)
        assert j
        return j


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
        "url": "u1",
        "reason": None,
        "immich_asset_id": "a1",
    }
    assert json.loads(replay[2]["data"]) == {"type": "progress", "downloaded": 3}
    assert json.loads(replay[3]["data"]) == {"type": "status", "status": "running"}
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
