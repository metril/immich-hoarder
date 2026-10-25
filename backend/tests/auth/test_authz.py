from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.authz import require_owner_or_admin, require_perm, require_scope, visible_to
from app.auth.principal import Principal
from app.db import engine as eng
from app.db.migrate import upgrade_head_async
from app.db.models import ImmichTarget, Perm, PrincipalType, Role, Share, User, Visibility

ACTORS = [
    "owner",
    "admin",
    "other",
    "group_member",
    "user_share_use",
    "user_share_edit",
    "scoped_admin",
]


@pytest.fixture
async def session(tmp_path: Path) -> AsyncIterator[AsyncSession]:
    url = f"sqlite+aiosqlite:///{tmp_path / 'a.db'}"
    await upgrade_head_async(url)
    engine = eng.make_engine(url)
    async with AsyncSession(engine) as s:
        yield s
    await engine.dispose()


async def _world(s: AsyncSession) -> dict[str, Principal]:
    users = {}
    for name in ACTORS:
        u = User(
            sub=name, role=Role.admin if name in ("admin", "scoped_admin") else Role.user, groups=[]
        )
        s.add(u)
        users[name] = u
    await s.flush()
    ps = {
        n: Principal(
            u.id,
            u.role,
            frozenset({"team"}) if n == "group_member" else frozenset(),
            frozenset({"sources:read"}) if n == "scoped_admin" else None,
        )
        for n, u in users.items()
    }
    return ps


async def _target(
    s: AsyncSession,
    owner: Principal,
    vis: Visibility,
    shares: list[tuple[PrincipalType, str, Perm]],
) -> ImmichTarget:
    t = ImmichTarget(
        name="t", url="http://x", api_key_enc=b"k", owner_id=owner.user_id, visibility=vis
    )
    s.add(t)
    await s.flush()
    for pt, pid, perm in shares:
        s.add(
            Share(
                resource_type=ImmichTarget.share_type,
                resource_id=t.id,
                principal_type=pt,
                principal_id=pid,
                perm=perm,
            )
        )
    await s.flush()
    return t


def _shares(ps: dict[str, Principal], kind: str) -> list[tuple[PrincipalType, str, Perm]]:
    if kind == "none":
        return []
    if kind == "wrongtype":
        kind = "user"
    if kind == "group_edit":
        return [(PrincipalType.group, "team", Perm.edit)]
    if kind == "group_use":
        return [(PrincipalType.group, "team", Perm.use)]
    return [
        (PrincipalType.user, str(ps["user_share_use"].user_id), Perm.use),
        (PrincipalType.user, str(ps["user_share_edit"].user_id), Perm.edit),
    ]


# (actor, visibility, share kind, op, expected)
ROWS = [
    ("owner", "private", "none", "edit", "ok"),
    ("owner", "private", "none", "delete", "ok"),
    ("admin", "private", "none", "edit", "ok"),
    ("admin", "private", "none", "delete", "ok"),
    ("admin", "restricted", "none", "edit", "ok"),
    ("other", "private", "none", "use", "404"),
    ("other", "everyone", "none", "use", "ok"),
    ("other", "everyone", "none", "edit", "403"),
    ("other", "restricted", "user", "use", "404"),
    ("group_member", "restricted", "group_use", "use", "ok"),
    ("group_member", "restricted", "group_use", "edit", "403"),
    ("group_member", "private", "group_use", "use", "404"),
    ("user_share_use", "restricted", "user", "use", "ok"),
    ("user_share_use", "restricted", "user", "edit", "403"),
    ("user_share_edit", "restricted", "user", "use", "ok"),
    ("user_share_edit", "restricted", "user", "edit", "ok"),
    ("user_share_edit", "restricted", "user", "delete", "403"),
    ("other", "everyone", "none", "delete", "403"),
    ("other", "private", "none", "delete", "404"),
    ("user_share_edit", "restricted", "wrongtype", "use", "404"),
    ("user_share_edit", "restricted", "wrongtype", "edit", "404"),
    ("group_member", "restricted", "group_edit", "use", "ok"),
    ("group_member", "restricted", "group_edit", "edit", "ok"),
    ("owner", "restricted", "none", "use", "ok"),
    ("owner", "restricted", "none", "edit", "ok"),
    ("owner", "restricted", "none", "delete", "ok"),
    ("scoped_admin", "private", "none", "use", "404"),
    ("scoped_admin", "private", "none", "edit", "404"),
    ("scoped_admin", "private", "none", "delete", "404"),
]


@pytest.mark.parametrize(("actor", "vis", "kind", "op", "expected"), ROWS)
async def test_access_matrix(
    session: AsyncSession, actor: str, vis: str, kind: str, op: str, expected: str
) -> None:
    ps = await _world(session)
    t = await _target(session, ps["owner"], Visibility(vis), _shares(ps, kind))
    if kind == "wrongtype":
        await session.execute(update(Share).values(resource_type="source"))
    p = ps[actor]
    try:
        if op == "delete":
            await require_owner_or_admin(session, t, p)
        else:
            await require_perm(session, t, p, Perm(op))
    except HTTPException as e:
        assert str(e.status_code) == expected
    else:
        assert expected == "ok"


async def test_visible_to_lists_only_accessible(session: AsyncSession) -> None:
    ps = await _world(session)
    shares = _shares(ps, "user")
    o = ps["owner"]
    priv = await _target(session, o, Visibility.private, [])
    ev = await _target(session, o, Visibility.everyone, [])
    rs = await _target(session, o, Visibility.restricted, shares)
    rg = await _target(session, o, Visibility.restricted, _shares(ps, "group_use"))
    pr = await _target(session, o, Visibility.private, shares)
    allids = {priv.id, ev.id, rs.id, rg.id, pr.id}
    expected = {
        "owner": allids,
        "admin": allids,
        "other": {ev.id},
        "group_member": {ev.id, rg.id},
        "user_share_use": {ev.id, rs.id},
        "user_share_edit": {ev.id, rs.id},
    }
    for actor, ids in expected.items():
        rows = await session.execute(visible_to(select(ImmichTarget.id), ImmichTarget, ps[actor]))
        assert set(rows.scalars()) == ids, actor
    edit = await session.execute(
        visible_to(select(ImmichTarget.id), ImmichTarget, ps["user_share_edit"], Perm.edit)
    )
    assert set(edit.scalars()) == {rs.id}


def test_scoped_admin_is_not_admin_and_scopes() -> None:
    p = Principal(1, Role.admin, frozenset(), frozenset({"sources:read"}))
    assert not p.is_admin
    require_scope(p, "sources:read")
    with pytest.raises(HTTPException) as e:
        require_scope(p, "sources:write")
    assert e.value.status_code == 403
    require_scope(Principal(1, Role.user, frozenset(), None), "anything")
    require_scope(Principal(1, Role.admin, frozenset(), frozenset({"admin"})), "x")


def test_user_key_with_admin_scope_gets_no_bypass() -> None:
    p = Principal(1, Role.user, frozenset(), frozenset({"admin"}))
    with pytest.raises(HTTPException) as e:
        require_scope(p, "sources:write")
    assert e.value.status_code == 403
