"""Build picklable job snapshots from DB rows, re-checking the owner's access."""

from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.authz import visible_to
from app.auth.principal import Principal
from app.core.crypto import SecretBox
from app.db.models import Credential, CredentialKind, ImmichTarget, Perm, Source, User
from app.rip.filters import FilterSpec
from app.rip.settings import load_rip_settings
from app.rip.snapshot import CredentialSnapshot, SourceSnapshot, TargetSnapshot
from app.runtime.notify import check_notify_url


async def check_refs(
    session: AsyncSession, owner_id: int, target_id: int | None, credential_id: int | None
) -> None:
    """The source owner (not the caller) must have `use` on the target and credential."""
    owner = await session.get(User, owner_id)
    if owner is None:
        raise HTTPException(422, "invalid owner")
    if owner.disabled:
        raise HTTPException(403, "source owner is disabled")
    op = Principal(owner.id, owner.role, frozenset(owner.groups or []), None)
    checks: list[tuple[type[ImmichTarget] | type[Credential], int | None]] = [
        (ImmichTarget, target_id),
        (Credential, credential_id),
    ]
    for model, ref in checks:
        if ref is None:
            continue
        stmt = visible_to(select(model.id).where(model.id == ref), model, op, Perm.use)
        if (await session.execute(stmt)).first() is None:
            raise HTTPException(403, f"no access to {model.share_type}")


async def credential_snapshot(
    session: AsyncSession, credential_id: int, box: SecretBox
) -> CredentialSnapshot:
    cred = await session.get(Credential, credential_id)
    if cred is None:
        raise HTTPException(422, "invalid credential")
    return CredentialSnapshot(
        site=cred.site, kind=cred.kind, secret=box.decrypt(cred.secret_enc).decode()
    )


async def build_snapshots(
    session: AsyncSession, source: Source, box: SecretBox
) -> tuple[SourceSnapshot, TargetSnapshot, CredentialSnapshot | None]:
    await check_refs(session, source.owner_id, source.target_id, source.credential_id)
    target = await session.get(ImmichTarget, source.target_id)
    if target is None:
        raise HTTPException(422, "invalid target")
    cred = (
        await credential_snapshot(session, source.credential_id, box)
        if source.credential_id is not None
        else None
    )
    snap = SourceSnapshot(
        id=source.id,
        name=source.name,
        url=source.url,
        extractor=source.extractor,
        target_id=source.target_id,
        album_template=source.album_template,
        backfill_mode=source.backfill_mode,
        backfill_value=source.backfill_value,
        allow_animated=source.allow_animated,
        filters=FilterSpec.model_validate(source.filters or {}),
        gdl_options=dict(source.gdl_options or {}),
        proxy=source.proxy,
        log_level=source.log_level or "info",
    )
    tsnap = TargetSnapshot(
        id=target.id, url=target.url, api_key=box.decrypt(target.api_key_enc).decode()
    )
    return snap, tsnap, cred


async def check_notify_refs(
    session: AsyncSession, owner_id: int, notify: dict[str, Any], box: SecretBox
) -> None:
    """Every notify credential must be of kind apprise and usable by the source owner."""
    ids = list(notify.get("credential_ids") or [])
    allow_private = (await load_rip_settings(session)).allow_private_hosts if ids else False
    for cid in ids:
        await check_refs(session, owner_id, None, cid)
        cred = await session.get(Credential, cid)
        if cred is None or cred.kind != CredentialKind.apprise:
            raise HTTPException(422, "notify credentials must be of kind apprise")
        try:
            check_notify_url(box.decrypt(cred.secret_enc).decode(), allow_private=allow_private)
        except ValueError as e:
            raise HTTPException(422, str(e)) from None
