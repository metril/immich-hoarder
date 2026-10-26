from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, get_args

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models import Role, User

Scope = Literal[
    "sources:read",
    "sources:write",
    "sources:run",
    "targets:read",
    "targets:write",
    "credentials:read",
    "credentials:write",
    "jobs:read",
    "jobs:write",
    "keys:read",
    "keys:write",
    "metrics:read",
    "admin",
]
SCOPES = frozenset(get_args(Scope))


@dataclass(frozen=True)
class Principal:
    user_id: int
    role: Role
    groups: frozenset[str]
    scopes: frozenset[str] | None  # None = full user rights

    @property
    def is_admin(self) -> bool:
        return self.role == Role.admin and (self.scopes is None or "admin" in self.scopes)


def resolve_role(groups: Any, settings: Settings) -> Role | None:
    gs = set(groups or [])
    if gs & set(settings.oidc_admin_groups):
        return Role.admin
    if gs & set(settings.oidc_user_groups):
        return Role.user
    return None


def extract_groups(claims: Mapping[str, Any], settings: Settings) -> list[str]:
    raw = claims.get(settings.oidc_groups_claim)
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [g for g in raw if isinstance(g, str)]
    return []


async def upsert_user(session: AsyncSession, claims: Mapping[str, Any], settings: Settings) -> User:
    """Create/update the user from claims. Role/groups refresh on every login and token use.

    A user whose groups no longer map to a role keeps their last role; callers must
    check `resolve_role(user.groups, settings)` to deny access.
    """
    sub = str(claims["sub"])
    groups = extract_groups(claims, settings)
    role = resolve_role(groups, settings)
    user = await _fetch_or_create(session, sub, role, groups)
    user.groups = groups
    if role is not None:
        user.role = role
    if claims.get("email"):
        user.email = str(claims["email"])
    name = claims.get("name") or claims.get("preferred_username")
    if name:
        user.name = str(name)
    await session.flush()
    return user


async def _fetch_or_create(
    session: AsyncSession, sub: str, role: Role | None, groups: list[str]
) -> User:
    user = (await session.execute(select(User).where(User.sub == sub))).scalar_one_or_none()
    if user is not None:
        return user
    user = User(sub=sub, role=role or Role.user, groups=groups)
    try:
        async with session.begin_nested():  # savepoint: caller's pending work survives
            session.add(user)
            await session.flush()
    except IntegrityError:
        # Concurrent first login: another request created the row; re-select once.
        return (await session.execute(select(User).where(User.sub == sub))).scalar_one()
    return user
