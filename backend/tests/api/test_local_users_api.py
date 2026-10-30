import httpx
from helpers import TARGET, actor, headers_for, make_user
from sqlalchemy import select

from app.db.engine import session_scope
from app.db.models import ApiKey, Role, User

U = "/api/v1/users"
PW = "password-1234"


async def _new(c: httpx.AsyncClient, h: dict[str, str], name: str, role: str = "user") -> int:
    r = await c.post(f"{U}/local", json={"username": name, "password": PW, "role": role}, headers=h)
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


async def test_scope_enforcement(client: httpx.AsyncClient) -> None:
    aid = await make_user("adm", Role.admin)
    uid, hu = await actor("u")
    body = {"username": "x", "password": PW}
    reset = {"new_password": PW}
    assert (await client.post(f"{U}/local", json=body, headers=hu)).status_code == 403
    for scopes in (["users:read"], ["sources:read"]):
        h = await headers_for(aid, scopes)
        assert (await client.post(f"{U}/local", json=body, headers=h)).status_code == 403
        assert (await client.post(f"{U}/{uid}/password", json=reset, headers=h)).status_code == 403
        assert (await client.delete(f"{U}/{uid}", headers=h)).status_code == 403
    assert (await client.post(f"{U}/local", json=body)).status_code == 401
    hw = await headers_for(aid, ["users:write"])
    assert (await client.post(f"{U}/local", json=body, headers=hw)).status_code == 201
    ha = await headers_for(aid, ["admin"])
    assert (
        await client.post(f"{U}/local", json={**body, "username": "y"}, headers=ha)
    ).status_code == 201


async def test_create_validation_and_conflict(client: httpx.AsyncClient) -> None:
    _, h = await actor("adm", Role.admin)
    await _new(client, h, "al")
    dup = await client.post(f"{U}/local", json={"username": "al", "password": PW}, headers=h)
    assert dup.status_code == 409
    short = await client.post(f"{U}/local", json={"username": "b", "password": "short"}, headers=h)
    assert short.status_code == 422


async def test_password_and_delete_local_only(client: httpx.AsyncClient) -> None:
    _, h = await actor("adm", Role.admin)
    oidc = await make_user("oidc|9")
    reset = {"new_password": PW}
    assert (await client.post(f"{U}/{oidc}/password", json=reset, headers=h)).status_code == 409
    assert (await client.delete(f"{U}/{oidc}", headers=h)).status_code == 409
    assert (await client.delete(f"{U}/9999", headers=h)).status_code == 404
    assert (await client.post(f"{U}/9999/password", json=reset, headers=h)).status_code == 404


async def test_delete_last_admin_409(client: httpx.AsyncClient) -> None:
    _, h = await actor("adm", Role.admin)
    solo = await _new(client, h, "solo", "admin")
    async with session_scope() as s:  # make solo the only enabled admin
        adm = (await s.execute(select(User).where(User.sub == "adm"))).scalar_one()
        adm.disabled = True
    hs = await headers_for(solo, ["admin"])
    r = await client.delete(f"{U}/{solo}", headers=hs)
    assert r.status_code == 409 and r.json()["detail"] == "last admin"
    async with session_scope() as s:
        adm = (await s.execute(select(User).where(User.sub == "adm"))).scalar_one()
        adm.disabled = False
    assert (await client.delete(f"{U}/{solo}", headers=h)).status_code == 204


async def test_delete_with_reassign(client: httpx.AsyncClient) -> None:
    _, h = await actor("adm", Role.admin)
    uid = await _new(client, h, "owner")
    hu = await headers_for(uid)
    tid = (await client.post("/api/v1/targets", json=TARGET, headers=hu)).json()["id"]
    async with session_scope() as s:
        s.add(ApiKey(user_id=uid, name="k", prefix="abcd1234", hash="x", scopes=[]))
    r = await client.delete(f"{U}/{uid}", headers=h)
    assert r.status_code == 409
    assert r.json()["owned"] == {"targets": 1, "credentials": 0, "sources": 0}
    assert (await client.delete(f"{U}/{uid}?reassign_to={uid}", headers=h)).status_code == 422
    assert (await client.delete(f"{U}/{uid}?reassign_to=9999", headers=h)).status_code == 422
    dest = await make_user("dest")
    assert (await client.delete(f"{U}/{uid}?reassign_to={dest}", headers=h)).status_code == 204
    hd = await headers_for(dest)
    assert (await client.get(f"/api/v1/targets/{tid}", headers=hd)).status_code == 200
    async with session_scope() as s:
        assert await s.get(User, uid) is None
        assert (await s.execute(select(ApiKey).where(ApiKey.user_id == uid))).first() is None
    empty = await _new(client, h, "empty")
    assert (await client.delete(f"{U}/{empty}", headers=h)).status_code == 204
