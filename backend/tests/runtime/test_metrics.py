import asyncio
import secrets
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from app.auth.apikeys import create_api_key
from app.core.config import Settings
from app.db.engine import session_scope
from app.db.models import Role, User
from app.main import create_app
from app.runtime.bus import EventBus


@pytest.fixture
async def app(settings: Settings) -> AsyncIterator[FastAPI]:
    app = create_app(settings)
    app.state.runtime_enabled = False
    async with app.router.lifespan_context(app):
        yield app


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        yield c


async def _key(scopes: list[str], role: Role = Role.user) -> str:
    async with session_scope() as s:
        u = User(
            sub=secrets.token_hex(4),
            role=role,
            groups=["hoarder-admins" if role == Role.admin else "hoarder-users"],
        )
        s.add(u)
        await s.flush()
        _, raw = await create_api_key(s, u, "k", scopes, None)
        return raw


async def test_metrics_requires_scope(client: httpx.AsyncClient) -> None:
    assert (await client.get("/metrics")).status_code == 401
    bad = await _key(["jobs:read"], Role.admin)  # scoped key without metrics:read
    assert (await client.get("/metrics", headers={"X-API-Key": bad})).status_code == 403
    good = await _key(["metrics:read"], Role.admin)
    r = await client.get("/metrics", headers={"Authorization": f"Bearer {good}"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert "ih_jobs_queued" in r.text and "ih_scratch_bytes" in r.text


async def test_metrics_counts_items_and_jobs(app: FastAPI, client: httpx.AsyncClient) -> None:
    bus = EventBus()
    app.state.metrics.start(bus)
    try:
        bus.publish(1, {"type": "status", "job_id": 1, "status": "running"})
        bus.publish(1, {"type": "item.saved", "url": "u"})
        bus.publish(1, {"type": "item.saved", "url": "v"})
        bus.publish(1, {"type": "item.failed", "url": "w"})
        bus.publish(1, {"type": "status", "job_id": 1, "status": "succeeded"})
        bus.publish(1, {"type": "status", "job_id": 1, "status": "succeeded"})  # dup
        for _ in range(50):
            await asyncio.sleep(0.01)
            if bus.subscriber_count(None) and app.state.metrics.idle():
                break
        key = await _key(["metrics:read"])
        text = (await client.get("/metrics", headers={"X-API-Key": key})).text
    finally:
        await app.state.metrics.stop()
    assert 'ih_items_total{outcome="saved"} 2.0' in text
    assert 'ih_items_total{outcome="failed"} 1.0' in text
    assert 'ih_jobs_total{status="succeeded"} 1.0' in text
    assert "ih_job_duration_seconds_count 1.0" in text


async def test_readyz_reports_components(
    app: FastAPI, client: httpx.AsyncClient, tmp_path: Path
) -> None:
    r = await client.get("/readyz")
    assert r.status_code == 503
    assert set(r.json()["failing"]) == {"scheduler", "supervisor"}
    app.state.scheduler = SimpleNamespace(running=True)
    app.state.supervisor = SimpleNamespace(alive=True)
    r = await client.get("/readyz")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    app.state.supervisor = SimpleNamespace(alive=False)
    r = await client.get("/readyz")
    assert r.status_code == 503 and r.json()["failing"] == ["supervisor"]
    assert (await client.get("/healthz")).json() == {"status": "ok"}
