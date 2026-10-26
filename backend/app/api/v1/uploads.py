import uuid
from datetime import datetime
from typing import Literal

import anyio.to_thread
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_obj, secret_box
from app.api.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page, paginate
from app.auth.authz import require_scope
from app.auth.deps import current_principal
from app.auth.principal import Principal
from app.core.crypto import SecretBox
from app.db.engine import get_session
from app.db.models import ImmichTarget, Job, JobItem, Perm, Source
from app.immich.client import ImmichClient
from app.immich.errors import AssetGone, ImmichAuthError, ImmichError, ImmichUnavailable
from app.runtime.visibility import visible_jobs_stmt

router = APIRouter(tags=["uploads"])


class UploadOut(BaseModel):
    id: int
    job_id: int
    source_id: int
    target_id: int
    immich_asset_id: str | None
    url: str
    outcome: str
    created_at: datetime | None


@router.get("/uploads", response_model=Page[UploadOut])
async def list_uploads(
    source_id: int | None = None,
    target_id: int | None = None,
    cursor: str | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session),
) -> Page[UploadOut]:
    require_scope(p, "jobs:read")
    visible = visible_jobs_stmt(p).with_only_columns(Job.id).where(Source.id == Job.source_id)
    stmt = select(JobItem).where(
        JobItem.outcome.in_(("uploaded", "linked")), JobItem.job_id.in_(visible)
    )
    if source_id is not None:
        stmt = stmt.where(JobItem.job_id.in_(select(Job.id).where(Job.source_id == source_id)))
    if target_id is not None:
        stmt = stmt.where(
            JobItem.job_id.in_(
                select(Job.id)
                .join(Source, Source.id == Job.source_id)
                .where(Source.target_id == target_id)
            )
        )
    rows, nxt = await paginate(session, stmt, cursor, limit, desc=True)
    info: dict[int, tuple[Job, int]] = {}
    ids = {r.job_id for r in rows}
    if ids:
        res = await session.execute(
            select(Job, Source.target_id)
            .join(Source, Source.id == Job.source_id)
            .where(Job.id.in_(ids))
        )
        info = {j.id: (j, t) for j, t in res.all()}
    items = []
    for r in rows:
        j, tid = info[r.job_id]
        items.append(
            UploadOut(
                id=r.id,
                job_id=r.job_id,
                source_id=j.source_id,
                target_id=tid,
                immich_asset_id=r.immich_asset_id,
                url=r.url,
                outcome=r.outcome,
                created_at=j.finished_at or j.started_at,
            )
        )
    return Page(items=items, next_cursor=nxt)


def _fetch(
    url: str,
    key_enc: bytes,
    box: SecretBox,
    transport: httpx.BaseTransport | None,
    asset_id: str,
    size: str,
) -> tuple[bytes, str]:
    with ImmichClient(url, box.decrypt(key_enc).decode(), transport=transport) as c:
        return c.thumbnail(asset_id, size)


@router.get("/targets/{obj_id}/assets/{asset_id}/thumbnail")
async def thumbnail(
    obj_id: int,
    asset_id: str,
    request: Request,
    size: Literal["thumbnail", "preview"] = "thumbnail",
    p: Principal = Depends(current_principal),
    box: SecretBox = Depends(secret_box),
    session: AsyncSession = Depends(get_session),
) -> Response:
    require_scope(p, "targets:read")
    try:
        uuid.UUID(asset_id)
    except ValueError:
        raise HTTPException(422, "invalid asset id") from None
    t: ImmichTarget = await get_obj(session, ImmichTarget, obj_id, p, Perm.use)
    visible = visible_jobs_stmt(p).with_only_columns(Job.id).where(Source.target_id == obj_id)
    found = await session.execute(
        select(exists().where(JobItem.immich_asset_id == asset_id, JobItem.job_id.in_(visible)))
    )
    if not found.scalar():
        raise HTTPException(404, "not found")
    transport = request.app.state.immich_transport
    try:
        data, ctype = await anyio.to_thread.run_sync(
            _fetch, t.url, t.api_key_enc, box, transport, asset_id, size
        )
    except AssetGone as e:
        raise HTTPException(404, "not found") from e
    except ImmichAuthError as e:
        raise HTTPException(502, "immich unauthorized") from e
    except (ImmichUnavailable, ImmichError) as e:
        raise HTTPException(502, "immich unavailable") from e
    if not ctype.lower().startswith("image/"):
        raise HTTPException(502, "immich unavailable")
    return Response(
        data,
        media_type=ctype,
        headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"},
    )
