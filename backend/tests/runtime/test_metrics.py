import secrets
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
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
    m = app.state.metrics
    t0 = datetime(2026, 1, 1, 0, 0, 0)
    m.observe(("status", 1, "running", {"started_at": t0}))
    for i in range(1500):  # lossless beyond the bus queue size
        m.observe(("event", 1, {"type": "item.uploaded", "url": str(i)}))
    m.observe(("event", 1, {"type": "item.failed", "url": "w"}))
    m.observe(("event", 1, {"type": "item.weird", "url": "w"}))
    fin = ("status", 1, "succeeded", {"finished_at": t0 + timedelta(seconds=30)})
    m.observe(fin)
    m.observe(fin)  # dup
    key = await _key(["metrics:read"])
    text = (await client.get("/metrics", headers={"X-API-Key": key})).text
    assert 'ih_items_total{outcome="uploaded"} 1500.0' in text
    assert 'ih_items_total{outcome="failed"} 1.0' in text
    assert 'ih_items_total{outcome="other"} 1.0' in text
    assert 'ih_jobs_total{status="succeeded"} 1.0' in text
    assert "ih_job_duration_seconds_count 1.0" in text
    assert "ih_job_duration_seconds_sum 30.0" in text


async def test_metrics_forbidden_for_non_admin_session(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    async with session_scope() as s:
        u = User(sub="plain", role=Role.user, groups=["hoarder-users"])
        s.add(u)
        await s.flush()
        uid = u.id
    from starlette.middleware.sessions import SessionMiddleware  # noqa: F401

    app.add_route("/_t/login", _login(uid), methods=["GET"])
    app.middleware_stack = None
    await client.get("/_t/login")
    assert (await client.get("/metrics")).status_code == 403


def _login(uid: int):  # type: ignore[no-untyped-def]
    from starlette.responses import PlainTextResponse

    async def h(request):  # type: ignore[no-untyped-def]
        request.session["user_id"] = uid
        request.session["sg"] = 0
        return PlainTextResponse("ok")

    return h


async def test_readyz_reports_components(
    app: FastAPI, client: httpx.AsyncClient, tmp_path: Path
) -> None:
    r = await client.get("/readyz")
    assert r.status_code == 503
    assert set(r.json()["failing"]) == {"scheduler", "supervisor", "writer", "bridge"}
    app.state.scheduler = SimpleNamespace(running=True)
    app.state.supervisor = SimpleNamespace(alive=True)
    app.state.job_writer = SimpleNamespace(alive=True)
    app.state.bridge = SimpleNamespace(alive=True)
    r = await client.get("/readyz")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    app.state.supervisor = SimpleNamespace(alive=False)
    r = await client.get("/readyz")
    assert r.status_code == 503 and r.json()["failing"] == ["supervisor"]
    app.state.supervisor = SimpleNamespace(alive=True)
    app.state.job_writer = SimpleNamespace(alive=False)
    app.state.bridge = SimpleNamespace(alive=False)
    r = await client.get("/readyz")
    assert r.json()["failing"] == ["writer", "bridge"]
    assert (await client.get("/healthz")).json() == {"status": "ok"}
