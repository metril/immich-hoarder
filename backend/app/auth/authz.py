from typing import Any

from fastapi import HTTPException
from sqlalchemy import ColumnElement, Select, and_, exists, false, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.principal import Principal
from app.db.models import Ownable, Perm, PrincipalType, Share, Visibility

_GRANTS: dict[Perm, tuple[Perm, ...]] = {
    Perm.use: (Perm.use, Perm.edit),  # edit implies use
    Perm.edit: (Perm.edit,),
}


def _predicate(model: type[Ownable], p: Principal, perm: Perm) -> ColumnElement[bool]:
    if p.is_admin:
        return true()
    m: Any = model
    match = or_(
        and_(
            Share.principal_type == PrincipalType.user,
            Share.principal_id == str(p.user_id),
        ),
        and_(
            Share.principal_type == PrincipalType.group,
            Share.principal_id.in_(sorted(p.groups)) if p.groups else false(),
        ),
    )
    shared = exists().where(
        Share.resource_type == model.share_type,
        Share.resource_id == m.id,
        Share.perm.in_(_GRANTS[perm]),
        match,
    )
    clauses = [m.owner_id == p.user_id, and_(m.visibility == Visibility.restricted, shared)]
    if perm == Perm.use:
        clauses.append(m.visibility == Visibility.everyone)
    return or_(*clauses)


def visible_to(
    stmt: Select[Any], model: type[Ownable], p: Principal, perm: Perm = Perm.use
) -> Select[Any]:
    return stmt.where(_predicate(model, p, perm))


async def _allowed(session: AsyncSession, obj: Ownable, p: Principal, perm: Perm) -> bool:
    m: Any = type(obj)
    stmt = visible_to(select(m.id).where(m.id == obj.id), m, p, perm)
    return (await session.execute(stmt)).first() is not None


async def can_edit(session: AsyncSession, obj: Ownable, p: Principal) -> bool:
    return await _allowed(session, obj, p, Perm.edit)


async def editable_ids(
    session: AsyncSession, model: type[Ownable], p: Principal, ids: list[int]
) -> set[int]:
    """Ids (of `ids`) the principal may PATCH; one query, same predicate as require_perm."""
    if not ids:
        return set()
    m: Any = model
    stmt = select(m.id).where(m.id.in_(ids), _predicate(model, p, Perm.edit))
    return {r[0] for r in (await session.execute(stmt)).all()}


async def usable_ids(
    session: AsyncSession, model: type[Ownable], p: Principal, ids: list[int]
) -> set[int]:
    """Ids (of `ids`) the principal may `use`; same predicate as check_refs."""
    if not ids:
        return set()
    m: Any = model
    stmt = select(m.id).where(m.id.in_(ids), _predicate(model, p, Perm.use))
    return {r[0] for r in (await session.execute(stmt)).all()}


async def can_use(session: AsyncSession, obj: Ownable, p: Principal) -> bool:
    return await _allowed(session, obj, p, Perm.use)


async def require_perm(session: AsyncSession, obj: Ownable, p: Principal, perm: Perm) -> None:
    if not await _allowed(session, obj, p, Perm.use):
        raise HTTPException(404, "not found")
    if perm != Perm.use and not await _allowed(session, obj, p, perm):
        raise HTTPException(403, "forbidden")


async def require_owner_or_admin(session: AsyncSession, obj: Ownable, p: Principal) -> None:
    if not await _allowed(session, obj, p, Perm.use):
        raise HTTPException(404, "not found")
    if not (p.is_admin or obj.owner_id == p.user_id):
        raise HTTPException(403, "forbidden")


def require_scope(p: Principal, scope: str) -> None:
    if p.scopes is None or scope in p.scopes or p.is_admin:
        return
    raise HTTPException(403, "forbidden")
