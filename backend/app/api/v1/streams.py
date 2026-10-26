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

from app.api.v1.jobs import _visible_job
from app.auth.authz import require_scope, visible_to
from app.auth.deps import current_principal
from app.auth.principal import Principal
from app.db.engine import session_scope
from app.db.models import Job, JobEvent, JobItem, JobStatus, Perm, Source
from app.runtime.bus import EventBus

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
        yield _sse({"type": "progress", **(cur.counters or {})})
        yield _sse({"type": "status", "status": str(cur.status)})
        if cur.status in TERMINAL:
            yield {"event": "end", "data": "{}"}
            return
        while not await is_disconnected():
            ev = await _next(sub)
            if ev is None:
                continue
            yield _sse(ev)
            if _is_terminal(ev):
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
            if ev is None or ev.get("type") not in ("status", "progress"):
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


@router.get("/jobs/stream")
async def dashboard(
    request: Request, p: Principal = Depends(current_principal)
) -> EventSourceResponse:
    require_scope(p, "jobs:read")
    bus = _bus(request)

    async def visible() -> set[int] | None:
        if p.is_admin:
            return None
        async with session_scope() as s:
            stmt = visible_to(select(Source.id), Source, p, Perm.use)
            return set((await s.scalars(stmt)).all())

    async def job_source(job_id: int) -> int | None:
        async with session_scope() as s:
            return await s.scalar(select(Job.source_id).where(Job.id == job_id))

    return EventSourceResponse(
        dashboard_stream(bus, visible, job_source, request.is_disconnected), ping=PING_SECONDS
    )


@router.get("/jobs/{job_id}/stream")
async def stream_job(
    job_id: int, request: Request, p: Principal = Depends(current_principal)
) -> EventSourceResponse:
    require_scope(p, "jobs:read")
    bus = _bus(request)
    async with session_scope() as s:
        job = await _visible_job(s, p, job_id)
    return EventSourceResponse(
        job_stream(bus, session_scope, job, request.is_disconnected), ping=PING_SECONDS
    )
