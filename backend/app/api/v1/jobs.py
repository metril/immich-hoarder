import anyio
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_obj, secret_box
from app.api.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page, paginate
from app.api.v1.sources import build_source
from app.auth.authz import require_scope
from app.auth.deps import current_principal
from app.auth.principal import Principal
from app.core.crypto import SecretBox
from app.db.engine import get_session, session_scope
from app.db.models import Job, JobEvent, JobItem, JobStatus, Source, Visibility
from app.runtime.supervisor import JobConflict, JobNotActive, JobSupervisor
from app.runtime.visibility import visible_jobs_stmt
from app.schemas.jobs import LOG_LEVELS, EventOut, ItemOut, JobOut, RipIn, RunIn

router = APIRouter(tags=["jobs"])


def _supervisor(request: Request) -> JobSupervisor:
    sup = getattr(request.app.state, "supervisor", None)
    if sup is None:
        raise HTTPException(503, "runtime unavailable")
    return sup  # type: ignore[no-any-return]


async def _names(session: AsyncSession, jobs: list[Job]) -> dict[int, str]:
    ids = {j.source_id for j in jobs}
    if not ids:
        return {}
    rows = await session.execute(select(Source.id, Source.name).where(Source.id.in_(ids)))
    return {i: n for i, n in rows}


async def _out(session: AsyncSession, job: Job) -> JobOut:
    return JobOut.of(job, (await _names(session, [job])).get(job.source_id))


async def _enqueue(
    session: AsyncSession, sup: JobSupervisor, source_id: int, p: Principal, level: str | None
) -> JobOut:
    await session.commit()  # release the write lock before the supervisor opens its own session
    return await _out(session, await _submit(sup, source_id, p, level))


async def _submit(sup: JobSupervisor, source_id: int, p: Principal, level: str | None) -> Job:
    try:
        return await sup.enqueue(source_id, p.user_id, level)
    except JobConflict:
        raise HTTPException(409, "job already active") from None


async def _visible_job(session: AsyncSession, p: Principal, job_id: int) -> Job:
    job = (await session.scalars(visible_jobs_stmt(p).where(Job.id == job_id))).one_or_none()
    if job is None:
        raise HTTPException(404, "not found")
    return job


@router.post("/sources/{source_id}/run", response_model=JobOut, status_code=202)
async def run_source(
    source_id: int,
    request: Request,
    body: RunIn | None = None,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> JobOut:
    require_scope(p, "sources:run")
    sup = _supervisor(request)
    await get_obj(session, Source, source_id, p)
    return await _enqueue(session, sup, source_id, p, body.log_level if body else None)


@router.post("/rip", response_model=JobOut, status_code=202)
async def adhoc_rip(
    body: RipIn,
    request: Request,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session, scope="function"),
    box: SecretBox = Depends(secret_box),
) -> JobOut:
    require_scope(p, "sources:run")
    sup = _supervisor(request)
    payload = body.model_copy(
        update={
            "ephemeral": True,
            "schedule_cron": None,
            "visibility": Visibility.private,
            "name": f"ad-hoc: {body.url[:80]}",
        }
    )
    src = await build_source(session, p, payload, box)
    source_id = src.id
    await session.commit()  # release the write lock before the supervisor opens its own session
    try:
        # shielded: a disconnect after the job row commits must not delete the live source
        with anyio.CancelScope(shield=True):
            job = await _submit(sup, source_id, p, body.log_level)
    except Exception:  # only a failed enqueue orphans the source; a queued job owns it
        with anyio.CancelScope(shield=True):
            async with session_scope() as s:
                await s.execute(delete(Source).where(Source.id == source_id))
        raise
    return await _out(session, job)


@router.get("/jobs", response_model=Page[JobOut])
async def list_jobs(
    source_id: int | None = None,
    status: JobStatus | None = None,
    cursor: str | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> Page[JobOut]:
    require_scope(p, "jobs:read")
    stmt = visible_jobs_stmt(p)
    if source_id is not None:
        stmt = stmt.where(Job.source_id == source_id)
    if status is not None:
        stmt = stmt.where(Job.status == status)
    rows, nxt = await paginate(session, stmt, cursor, limit, desc=True)
    names = await _names(session, rows)
    return Page(items=[JobOut.of(j, names.get(j.source_id)) for j in rows], next_cursor=nxt)


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(
    job_id: int,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> JobOut:
    require_scope(p, "jobs:read")
    return await _out(session, await _visible_job(session, p, job_id))


@router.get("/jobs/{job_id}/items", response_model=Page[ItemOut])
async def job_items(
    job_id: int,
    outcome: str | None = None,
    cursor: str | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> Page[ItemOut]:
    require_scope(p, "jobs:read")
    await _visible_job(session, p, job_id)
    stmt = select(JobItem).where(JobItem.job_id == job_id)
    if outcome is not None:
        stmt = stmt.where(JobItem.outcome == outcome)
    rows, nxt = await paginate(session, stmt, cursor, limit, desc=True)
    return Page(items=[ItemOut.of(r) for r in rows], next_cursor=nxt)


@router.get("/jobs/{job_id}/events", response_model=Page[EventOut])
async def job_events(
    job_id: int,
    min_level: str | None = None,
    cursor: str | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> Page[EventOut]:
    require_scope(p, "jobs:read")
    if min_level is not None and min_level not in LOG_LEVELS:
        raise HTTPException(422, "invalid min_level")
    await _visible_job(session, p, job_id)
    stmt = select(JobEvent).where(JobEvent.job_id == job_id)
    if min_level is not None:
        stmt = stmt.where(JobEvent.level.in_(LOG_LEVELS[LOG_LEVELS.index(min_level) :]))
    rows, nxt = await paginate(session, stmt, cursor, limit, desc=True)
    return Page(items=[EventOut.of(r) for r in rows], next_cursor=nxt)


@router.post("/jobs/{job_id}/cancel", response_model=JobOut, status_code=202)
async def cancel_job(
    job_id: int,
    request: Request,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> JobOut:
    require_scope(p, "jobs:write")
    sup = _supervisor(request)
    job = await _visible_job(session, p, job_id)
    try:
        await sup.cancel(job_id)
    except JobNotActive:
        raise HTTPException(409, "job not active") from None
    await session.refresh(job)
    return await _out(session, job)


@router.post("/jobs/{job_id}/retry", response_model=JobOut, status_code=202)
async def retry_job(
    job_id: int,
    request: Request,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> JobOut:
    require_scope(p, "sources:run")
    sup = _supervisor(request)
    job = await _visible_job(session, p, job_id)
    return await _enqueue(session, sup, job.source_id, p, job.log_level)
