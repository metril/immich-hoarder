import asyncio
import time
from collections import OrderedDict
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

import orjson
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse
from starlette.background import BackgroundTask

from app.api.v1.jobs import _visible_job
from app.auth.authz import require_scope, visible_to
from app.auth.deps import current_principal
from app.auth.principal import Principal
from app.db.engine import session_scope
from app.db.models import Job, JobEvent, JobItem, JobStatus, Perm, Source
from app.runtime.bus import EventBus
from app.runtime.visibility import visible_jobs_stmt

router = APIRouter(tags=["jobs"])

REPLAY_EVENTS = 200
REPLAY_ITEMS = 100
PING_SECONDS = 15
POLL_SECONDS = 1.0
VISIBLE_TTL = 30.0
JOB_SOURCE_CACHE = 512
TERMINAL = {JobStatus.succeeded, JobStatus.failed, JobStatus.cancelled}
_TERMINAL_VALUES = {s.value for s in TERMINAL}

Sse = dict[str, str]
IsDisconnected = Callable[[], Awaitable[bool]]
SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


def _sse(ev: dict[str, Any]) -> Sse:
    return {"event": str(ev.get("type", "message")), "data": orjson.dumps(ev).decode()}


def _is_terminal(ev: dict[str, Any]) -> bool:
    return ev.get("type") == "status" and str(ev.get("status")) in _TERMINAL_VALUES


async def _next(sub: AsyncIterator[dict[str, Any]]) -> dict[str, Any] | None:
    try:
        return await asyncio.wait_for(sub.__anext__(), POLL_SECONDS)
    except TimeoutError:
        return None


async def job_stream(
    bus: EventBus,
    session_factory: SessionFactory,
    job: Job,
    is_disconnected: IsDisconnected,
    still_visible: Callable[[], Awaitable[bool]] | None = None,
) -> AsyncIterator[Sse]:
    with bus.subscribe(job.id) as sub:  # subscribe first so no event is missed
        async with session_factory() as s:
            events = (
                await s.scalars(
                    select(JobEvent)
                    .where(JobEvent.job_id == job.id)
                    .order_by(JobEvent.id.desc())
                    .limit(REPLAY_EVENTS)
                )
            ).all()
            items = (
                await s.scalars(
                    select(JobItem)
                    .where(JobItem.job_id == job.id)
                    .order_by(JobItem.id.desc())
                    .limit(REPLAY_ITEMS)
                )
            ).all()
            fresh = await s.get(Job, job.id)
        cur = fresh or job
        for e in reversed(events):
            yield _sse({**e.data, "type": e.type})
        for i in reversed(items):
            yield _sse(
                {
                    "type": f"item.{i.outcome}",
                    "url": i.url,
                    "reason": i.reason,
                    "immich_asset_id": i.immich_asset_id,
                }
            )
        yield _sse({"type": "progress", "counters": cur.counters or {}})
        yield _sse({"type": "status", "job_id": job.id, "status": str(cur.status)})
        if cur.status in TERMINAL:
            yield {"event": "end", "data": "{}"}
            return
        checked = time.monotonic()
        while not await is_disconnected():
            if still_visible is not None and time.monotonic() - checked >= VISIBLE_TTL:
                checked = time.monotonic()
                if not await still_visible():
                    yield {"event": "end", "data": "{}"}
                    return
            ev = await _next(sub)
            if ev is None:
                continue
            yield _sse(ev)
            if ev.get("type") == "gap":
                async with session_factory() as s:
                    row = await s.get(Job, job.id)
                if row is None or row.status in TERMINAL:
                    yield {"event": "end", "data": "{}"}
                    return
            elif _is_terminal(ev):
                yield {"event": "end", "data": "{}"}
                return


async def dashboard_stream(
    bus: EventBus,
    visible_source_ids_fn: Callable[[], Awaitable[set[int] | None]],
    job_source_fn: Callable[[int], Awaitable[int | None]],
    is_disconnected: IsDisconnected,
) -> AsyncIterator[Sse]:
    visible: set[int] | None = None
    loaded_at = float("-inf")
    have = False
    lru: OrderedDict[int, int | None] = OrderedDict()
    with bus.subscribe(None) as sub:
        while not await is_disconnected():
            ev = await _next(sub)
            if ev is None:
                continue
            if ev.get("type") == "gap":
                yield _sse(ev)
                continue
            if ev.get("type") not in ("status", "progress"):
                continue
            jid = ev.get("job_id")
            if not isinstance(jid, int):
                continue
            now = time.monotonic()
            if not have or now - loaded_at >= VISIBLE_TTL:
                visible, loaded_at, have = await visible_source_ids_fn(), now, True
            if jid in lru:
                lru.move_to_end(jid)
            else:
                lru[jid] = await job_source_fn(jid)
                if len(lru) > JOB_SOURCE_CACHE:
                    lru.popitem(last=False)
            sid = lru[jid]
            if sid is None or (visible is not None and sid not in visible):
                continue
            yield _sse(ev)


def _bus(request: Request) -> EventBus:
    bus = getattr(request.app.state, "bus", None)
    if bus is None:
        raise HTTPException(503, "runtime unavailable")
    return bus  # type: ignore[no-any-return]


async def visible_source_ids(p: Principal) -> set[int] | None:
    """Source ids the principal may use; None means all (admin)."""
    if p.is_admin:
        return None
    async with session_scope() as s:
        stmt = visible_to(select(Source.id), Source, p, Perm.use)
        return set((await s.scalars(stmt)).all())


async def job_source_id(job_id: int) -> int | None:
    async with session_scope() as s:
        return await s.scalar(select(Job.source_id).where(Job.id == job_id))


async def job_visible(p: Principal, job_id: int) -> bool:
    async with session_scope() as s:
        return (await s.scalar(visible_jobs_stmt(p).where(Job.id == job_id))) is not None


MAX_STREAMS = 10
_active: dict[int, int] = {}


def _acquire(uid: int) -> Callable[[], None]:
    if _active.get(uid, 0) >= MAX_STREAMS:
        raise HTTPException(429, "too many streams")
    _active[uid] = _active.get(uid, 0) + 1
    done = False

    def release() -> None:
        nonlocal done
        if done:
            return
        done = True
        if _active.get(uid, 0) <= 1:
            _active.pop(uid, None)
        else:
            _active[uid] -= 1

    return release


async def _guarded(gen: AsyncIterator[Sse], release: Callable[[], None]) -> AsyncIterator[Sse]:
    try:
        async for item in gen:
            yield item
    finally:
        release()


@router.get("/jobs/stream")
async def dashboard(
    request: Request, p: Principal = Depends(current_principal)
) -> EventSourceResponse:
    require_scope(p, "jobs:read")
    bus = _bus(request)
    release = _acquire(p.user_id)
    gen = dashboard_stream(
        bus, lambda: visible_source_ids(p), job_source_id, request.is_disconnected
    )
    return EventSourceResponse(
        _guarded(gen, release), ping=PING_SECONDS, background=BackgroundTask(release)
    )


@router.get("/jobs/{job_id}/stream")
async def stream_job(
    job_id: int, request: Request, p: Principal = Depends(current_principal)
) -> EventSourceResponse:
    require_scope(p, "jobs:read")
    bus = _bus(request)
    async with session_scope() as s:
        job = await _visible_job(s, p, job_id)
    release = _acquire(p.user_id)
    gen = job_stream(
        bus, session_scope, job, request.is_disconnected, lambda: job_visible(p, job_id)
    )
    return EventSourceResponse(
        _guarded(gen, release), ping=PING_SECONDS, background=BackgroundTask(release)
    )
