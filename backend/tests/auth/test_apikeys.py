from datetime import UTC, datetime, timedelta

import fake_idp
import httpx
from conftest import do_login
from sqlalchemy import select

from app.auth.apikeys import create_api_key
from app.db.engine import session_scope
from app.db.models import ApiKey, Role, User


async def make_user(sub: str = "u", role: Role = Role.user) -> int:
    async with session_scope() as s:
        u = User(
            sub=sub, role=role, groups=["hoarder-admins" if role == Role.admin else "hoarder-users"]
        )
        s.add(u)
        await s.flush()
        return u.id


async def make_key(
    uid: int, scopes: list[str], expires_at: datetime | None = None
) -> tuple[int, str]:
    async with session_scope() as s:
        user = await s.get(User, uid)
        assert user
        key, raw = await create_api_key(s, user, "k", scopes, expires_at)
        return key.id, raw


async def test_api_key_shown_once_and_works(client: httpx.AsyncClient) -> None:
    uid = await make_user()
    kid, raw = await make_key(uid, ["sources:read"])
    assert raw.startswith("ih_") and len(raw.split("_", 2)[1]) == 8
    async with session_scope() as s:
        key = await s.get(ApiKey, kid)
        assert key and raw not in key.hash and key.hash.startswith("$argon2id$")
    r = await client.post("/_t/echo", headers={"X-API-Key": raw})
    assert r.status_code == 200 and r.json() == {"id": uid}
    assert (await client.post("/_t/echo", headers={"X-API-Key": raw + "x"})).status_code == 401


async def test_api_key_revoked_401(client: httpx.AsyncClient) -> None:
    kid, raw = await make_key(await make_user(), [])
    async with session_scope() as s:
        key = await s.get(ApiKey, kid)
        assert key
        key.revoked = True
    assert (await client.post("/_t/echo", headers={"X-API-Key": raw})).status_code == 401


async def test_api_key_expired_401(client: httpx.AsyncClient) -> None:
    past = datetime.now(UTC) - timedelta(minutes=1)
    _, raw = await make_key(await make_user(), [], past)
    assert (await client.post("/_t/echo", headers={"X-API-Key": raw})).status_code == 401


async def test_api_key_scope_capped_after_demotion(client: httpx.AsyncClient) -> None:
    uid = await make_user("adm", Role.admin)
    _, raw = await make_key(uid, ["admin"])
    h = {"X-API-Key": raw}
    assert (await client.get("/_t/admin", headers=h)).status_code == 200
    async with session_scope() as s:
        u = (await s.execute(select(User).where(User.id == uid))).scalar_one()
        u.role = Role.user
        u.groups = ["hoarder-users"]
    assert (await client.get("/_t/admin", headers=h)).status_code == 403


async def test_csrf_required_for_cookie_mutations(
    client: httpx.AsyncClient, idp: fake_idp.FakeIdp
) -> None:
    await do_login(client, idp, "dave", ["hoarder-users"])
    assert (await client.post("/_t/echo")).status_code == 403
    assert (await client.post("/_t/echo", headers={"X-CSRF-Token": "wrong"})).status_code == 403
    tok = client.cookies["ih_csrf"]
    assert (await client.post("/_t/echo", headers={"X-CSRF-Token": tok})).status_code == 200
    async with session_scope() as s:
        user = (await s.execute(select(User).where(User.sub == "dave"))).scalar_one()
        _, raw = await create_api_key(s, user, "k", [], None)
    fresh = httpx.AsyncClient(transport=client._transport, base_url="http://testserver")
    assert (await fresh.post("/_t/echo", headers={"X-API-Key": raw})).status_code == 200
    await fresh.aclose()


def test_api_key_regex_requires_exactly_32() -> None:
    from app.auth.apikeys import _RAW_RE

    assert _RAW_RE.match("ih_abcd1234_" + "A" * 32)
    assert _RAW_RE.match("ih_abcd1234_" + "A" * 33) is None
    assert _RAW_RE.match("ih_abcd1234_" + "A" * 31) is None


async def test_csrf_cookie_renewed_with_session(
    client: httpx.AsyncClient, idp: fake_idp.FakeIdp
) -> None:
    await do_login(client, idp, "gina", ["hoarder-users"])
    tok = client.cookies["ih_csrf"]
    r = await client.get("/api/v1/auth/me")
    sc = [h for h in r.headers.get_list("set-cookie") if h.startswith("ih_csrf=")]
    assert len(sc) == 1 and f"ih_csrf={tok}" in sc[0] and "Max-Age=28800" in sc[0]
    # a browser whose CSRF cookie was refreshed keeps working past the original 8h
    assert (await client.post("/_t/echo", headers={"X-CSRF-Token": tok})).status_code == 200
    # a missing cookie is never papered over
    client.cookies.delete("ih_csrf")
    assert (await client.post("/_t/echo", headers={"X-CSRF-Token": tok})).status_code == 403
    assert "ih_csrf" not in client.cookies
