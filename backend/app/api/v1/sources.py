import asyncio
import logging
import shutil

import anyio
import anyio.to_thread
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_obj, secret_box
from app.api.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page, paginate
from app.api.v1.shares import delete_shares, shares_router
from app.auth.authz import (
    can_edit,
    editable_ids,
    require_owner_or_admin,
    require_scope,
    visible_to,
)
from app.auth.deps import current_principal
from app.auth.principal import Principal
from app.core.crypto import SecretBox
from app.core.extractors import UnsupportedURL, validate_proxy, validate_url
from app.db.engine import get_session
from app.db.models import BackfillMode, Job, JobStatus, Perm, Source
from app.rip.build import check_notify_refs, check_refs, credential_snapshot
from app.rip.filters import FilterSpec, validate_backfill
from app.rip.preview import (
    PREVIEW_MAX,
    PreviewError,
    PreviewItem,
    make_job_dir,
    preview,
    run_in_subprocess,
)
from app.rip.scrub import secret_fragments
from app.rip.settings import load_rip_settings
from app.rip.snapshot import SourceSnapshot
from app.schemas.sources import SourceIn, SourceOut, SourcePatch

log = logging.getLogger(__name__)

PREVIEW_TIMEOUT = 60.0
_PREVIEW_SEM = asyncio.Semaphore(2)


async def _sync(request: Request, session: AsyncSession, source_id: int) -> None:
    """Commit, then refresh the source's cron trigger (no-op without a scheduler)."""
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is None:
        return
    await session.commit()
    try:
        await scheduler.sync_source(source_id)
    except Exception as e:  # write is already committed; never turn it into a 500
        log.error("scheduler sync failed for source %s: %s", source_id, type(e).__name__)


router = APIRouter(prefix="/sources", tags=["sources"])


async def _check_proxy(session: AsyncSession, proxy: str | None) -> None:
    if proxy is None:
        return
    rip = await load_rip_settings(session)
    try:
        validate_proxy(proxy, allow_private=rip.allow_private_hosts)
    except UnsupportedURL as e:
        raise HTTPException(422, str(e)) from None


async def _extractor_for(session: AsyncSession, url: str) -> str:
    rip = await load_rip_settings(session)
    try:
        return validate_url(url, allow_private=rip.allow_private_hosts)
    except UnsupportedURL as e:
        raise HTTPException(422, str(e)) from None


@router.get("", response_model=Page[SourceOut])
async def list_sources(
    cursor: str | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    include_ephemeral: bool = False,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> Page[SourceOut]:
    require_scope(p, "sources:read")
    stmt = visible_to(select(Source), Source, p)
    if not include_ephemeral:
        stmt = stmt.where(Source.ephemeral.is_(False))
    rows, nxt = await paginate(session, stmt, cursor, limit)
    ed = await editable_ids(session, Source, p, [r.id for r in rows])
    return Page(items=[SourceOut.of(r, r.id in ed) for r in rows], next_cursor=nxt)


async def build_source(
    session: AsyncSession, p: Principal, body: SourceIn, box: SecretBox
) -> Source:
    """Validate a create payload and add the resulting Source (flushed) owned by `p`."""
    await check_refs(session, p.user_id, body.target_id, body.credential_id)
    await check_notify_refs(session, p.user_id, body.notify, box)
    extractor = await _extractor_for(session, body.url)
    await _check_proxy(session, body.proxy)
    s = Source(
        **body.model_dump(),
        extractor=extractor,
        owner_id=p.user_id,
    )
    session.add(s)
    await session.flush()
    return s


@router.post("", response_model=SourceOut, status_code=201)
async def create_source(
    body: SourceIn,
    request: Request,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session, scope="function"),
    box: SecretBox = Depends(secret_box),
) -> SourceOut:
    require_scope(p, "sources:write")
    s = await build_source(session, p, body, box)
    out = SourceOut.of(s, True)
    await _sync(request, session, s.id)
    return out


class PreviewIn(SourceIn):
    limit: int = Field(default=PREVIEW_MAX, ge=1, le=PREVIEW_MAX)


class PreviewOut(BaseModel):
    items: list[PreviewItem]


@router.post("/preview", response_model=PreviewOut)
async def preview_source(
    body: PreviewIn,
    request: Request,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session, scope="function"),
    box: SecretBox = Depends(secret_box),
) -> PreviewOut:
    require_scope(p, "sources:read")
    await check_refs(session, p.user_id, body.target_id, body.credential_id)
    extractor = await _extractor_for(session, body.url)
    await _check_proxy(session, body.proxy)
    cred = (
        await credential_snapshot(session, body.credential_id, box)
        if body.credential_id is not None
        else None
    )
    rip = await load_rip_settings(session)
    snap = SourceSnapshot(
        id=0,
        name=body.name,
        url=body.url,
        extractor=extractor,
        target_id=body.target_id,
        album_template=body.album_template,
        backfill_mode=body.backfill_mode,
        backfill_value=body.backfill_value,
        allow_animated=body.allow_animated,
        filters=FilterSpec.model_validate(body.filters),
        gdl_options=body.gdl_options,
        proxy=body.proxy,
        log_level=body.log_level or "info",
    )
    # release the DB connection before the (slow) subprocess run
    await session.commit()
    if _PREVIEW_SEM.locked():
        raise HTTPException(429, "too many previews")
    await _PREVIEW_SEM.acquire()
    job_dir = None
    # shielded: a client disconnect must not free the slot or remove the dir under a live child
    with anyio.CancelScope(shield=True):
        try:
            job_dir = make_job_dir(request.app.state.settings.scratch_dir)
            items = await run_in_threadpool(
                run_in_subprocess,
                preview,
                snap,
                cred,
                rip,
                job_dir,
                body.limit,
                timeout=PREVIEW_TIMEOUT,
                fragments=secret_fragments(cred),
            )
        except TimeoutError:
            raise HTTPException(504, "preview timed out") from None
        except PreviewError as e:
            raise HTTPException(502, f"preview failed: {str(e)[:200]}") from None
        finally:
            try:
                if job_dir is not None:
                    await anyio.to_thread.run_sync(shutil.rmtree, job_dir, True)
            finally:
                _PREVIEW_SEM.release()
    return PreviewOut(items=items)


@router.get("/{obj_id}", response_model=SourceOut)
async def get_source(
    obj_id: int,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> SourceOut:
    require_scope(p, "sources:read")
    s: Source = await get_obj(session, Source, obj_id, p)
    return SourceOut.of(s, await can_edit(session, s, p))


@router.patch("/{obj_id}", response_model=SourceOut)
async def patch_source(
    obj_id: int,
    body: SourcePatch,
    request: Request,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session, scope="function"),
    box: SecretBox = Depends(secret_box),
) -> SourceOut:
    require_scope(p, "sources:write")
    s: Source = await get_obj(session, Source, obj_id, p, Perm.edit)
    data = body.model_dump(exclude_unset=True)
    for col in (
        "name",
        "url",
        "target_id",
        "album_template",
        "backfill_mode",
        "allow_animated",
        "filters",
        "notify",
        "gdl_options",
        "enabled",
        "ephemeral",
    ):
        if col in data and data[col] is None:
            raise HTTPException(422, f"{col} cannot be null")
    mode = data.get("backfill_mode", s.backfill_mode)
    value = data["backfill_value"] if "backfill_value" in data else s.backfill_value
    if "backfill_mode" in data and "backfill_value" not in data and mode != s.backfill_mode:
        value = None if mode == BackfillMode.full else value
    try:
        validate_backfill(mode, value)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    for k, v in data.items():
        setattr(s, k, v)
    s.backfill_value = value
    if "proxy" in data:
        await _check_proxy(session, data["proxy"])
    if "url" in data:
        s.extractor = await _extractor_for(session, s.url)
    await check_refs(session, s.owner_id, s.target_id, s.credential_id)
    await check_notify_refs(session, s.owner_id, s.notify, box)
    await session.flush()
    out = SourceOut.of(s, True)
    await _sync(request, session, obj_id)
    return out


@router.delete("/{obj_id}", status_code=204)
async def delete_source(
    obj_id: int,
    request: Request,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session, scope="function"),
) -> Response:
    require_scope(p, "sources:write")
    s: Source = await get_obj(session, Source, obj_id, p)
    await require_owner_or_admin(session, s, p)
    # one atomic statement: no job can become active between the check and the delete
    res = await session.execute(
        delete(Source).where(
            Source.id == obj_id,
            ~exists().where(
                Job.source_id == Source.id,
                Job.status.in_((JobStatus.queued, JobStatus.running)),
            ),
        )
    )
    if res.rowcount == 0:  # type: ignore[attr-defined]
        if await session.scalar(select(Source.id).where(Source.id == obj_id)) is not None:
            raise HTTPException(409, "source has an active job")
        raise HTTPException(404, "not found")
    await delete_shares(session, Source.share_type, obj_id)
    await _sync(request, session, obj_id)
    return Response(status_code=204)


router.include_router(shares_router(Source, "sources"))
