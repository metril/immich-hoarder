from typing import Any

import httpx
import pytest
from helpers import TARGET, actor, headers_for, make_user

from app.db.engine import session_scope
from app.db.models import Job, JobStatus, Role

API = "/api/v1"
SORTS = [None, "id", "-id", "name", "-name", "created_at", "-created_at"]


async def test_admin_scoped_key_still_reaches_settings_and_users(client: httpx.AsyncClient) -> None:
    uid = await make_user("adm", Role.admin)
    h = await headers_for(uid, ["admin"])
    assert (await client.get(f"{API}/settings", headers=h)).status_code == 200
    assert (await client.get(f"{API}/users", headers=h)).status_code == 200
    h_default = await headers_for(uid)  # every non-admin scope plus admin
    assert (await client.get(f"{API}/settings", headers=h_default)).status_code == 200


async def test_fine_admin_scopes_matrix(client: httpx.AsyncClient) -> None:
    uid = await make_user("adm", Role.admin)
    rs = await headers_for(uid, ["settings:read"])
    ur = await headers_for(uid, ["users:read"])
    uw = await headers_for(uid, ["users:write"])
    assert (await client.get(f"{API}/settings", headers=rs)).status_code == 200
    assert (await client.put(f"{API}/settings", json={}, headers=rs)).status_code == 403
    assert (await client.get(f"{API}/users", headers=rs)).status_code == 403
    assert (await client.get(f"{API}/users", headers=ur)).status_code == 200
    assert (await client.get(f"{API}/settings", headers=ur)).status_code == 403
    assert (await client.patch(f"{API}/users/{uid}", json={}, headers=ur)).status_code == 403
    assert (await client.patch(f"{API}/users/{uid}", json={}, headers=uw)).status_code == 200
    assert (await client.get(f"{API}/users", headers=uw)).status_code == 403


async def test_non_admin_role_key_is_stripped_of_admin_only_scopes(
    client: httpx.AsyncClient,
) -> None:
    uid = await make_user("u")
    h = await headers_for(uid, ["settings:read", "settings:write", "users:read", "users:write"])
    assert (await client.get(f"{API}/settings", headers=h)).status_code == 403
    assert (await client.get(f"{API}/users", headers=h)).status_code == 403


async def test_only_admins_can_grant_admin_only_scopes(client: httpx.AsyncClient) -> None:
    uid_u, hu = await actor("u")
    body = {"name": "k", "scopes": ["users:read"]}
    assert (await client.post(f"{API}/api-keys", json=body, headers=hu)).status_code == 403
    uid = await make_user("adm", Role.admin)
    ha = await headers_for(uid, ["admin"])
    r = await client.post(f"{API}/api-keys", json=body, headers=ha)
    assert r.status_code == 201, r.text
    # an admin-role key without `admin` may pass on only the scopes it holds
    hk = await headers_for(uid, ["keys:write", "keys:read", "settings:read"])
    body = {"name": "k2", "scopes": ["settings:read"]}
    r = await client.post(f"{API}/api-keys", json=body, headers=hk)
    assert r.status_code == 201, r.text
    body = {"name": "k3", "scopes": ["settings:write"]}
    assert (await client.post(f"{API}/api-keys", json=body, headers=hk)).status_code == 403
    made = await client.post(
        f"{API}/api-keys", json={"name": "r", "scopes": ["keys:write", "settings:read"]}, headers=ha
    )
    hr = {"X-API-Key": made.json()["key"]}
    r = await client.post(f"{API}/api-keys/{made.json()['id']}/rotate", headers=hr)
    assert r.status_code == 201, r.text
    # edit path goes through the same helper
    kid = (
        await client.post(f"{API}/api-keys", json={"name": "p", "scopes": []}, headers=hu)
    ).json()["id"]
    r = await client.patch(f"{API}/api-keys/{kid}", json={"scopes": ["users:write"]}, headers=hu)
    assert r.status_code == 403
    assert uid_u


# ---- search / sort / pagination ----------------------------------------------------------


async def _mk_targets(client: httpx.AsyncClient, h: dict[str, str]) -> None:
    for n in ["beta", "alpha", "beta", "gamma", "alpha", "beta", "Delta_x", "100%_off"]:
        r = await client.post(f"{API}/targets", json={**TARGET, "name": n}, headers=h)
        assert r.status_code == 201, r.text


async def _mk_jobs(client: httpx.AsyncClient, h: dict[str, str]) -> None:
    tid = (await client.post(f"{API}/targets", json=TARGET, headers=h)).json()["id"]
    sids = []
    for n in ["src-a", "src-b", "src-a"]:
        r = await client.post(
            f"{API}/sources",
            json={"name": n, "url": "https://www.reddit.com/r/pics/", "target_id": tid},
            headers=h,
        )
        sids.append(r.json()["id"])
    sts = [JobStatus.succeeded, JobStatus.failed, JobStatus.cancelled]
    async with session_scope() as s:
        for i in range(9):
            s.add(Job(source_id=sids[i % 3], status=sts[(i // 2) % 3]))


async def _walk(
    client: httpx.AsyncClient, h: dict[str, str], path: str, params: dict[str, Any], limit: int
) -> list[int]:
    ids: list[int] = []
    cursor = None
    for _ in range(50):
        q = {**params, "limit": limit, **({"cursor": cursor} if cursor else {})}
        r = await client.get(f"{API}{path}", params=q, headers=h)
        assert r.status_code == 200, r.text
        d = r.json()
        ids += [i["id"] for i in d["items"]]
        cursor = d["next_cursor"]
        if not cursor:
            return ids
    raise AssertionError("pagination did not terminate")


@pytest.mark.parametrize("sort", SORTS)
@pytest.mark.parametrize("q", [None, "beta", "ALPHA", "%", "_"])
async def test_targets_walk(client: httpx.AsyncClient, sort: str | None, q: str | None) -> None:
    _, h = await actor("a")
    await _mk_targets(client, h)
    params = {k: v for k, v in {"sort": sort, "q": q}.items() if v}
    full = await _walk(client, h, "/targets", params, 200)
    assert len(full) == len(set(full))
    for lim in (1, 2, 3):
        assert await _walk(client, h, "/targets", params, lim) == full
    if q is None:
        assert len(full) == 8
    if sort in ("name", "-name"):
        items = (await client.get(f"{API}/targets", params=params, headers=h)).json()["items"]
        names = [i["name"] for i in items]
        assert names == sorted(names, reverse=sort == "-name")


async def test_q_is_escaped(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    await _mk_targets(client, h)
    r = await client.get(f"{API}/targets", params={"q": "%"}, headers=h)
    assert [i["name"] for i in r.json()["items"]] == ["100%_off"]
    r = await client.get(f"{API}/targets", params={"q": "_x"}, headers=h)
    assert [i["name"] for i in r.json()["items"]] == ["Delta_x"]


@pytest.mark.parametrize("sort", [None, "sub", "-sub", "created_at", "-created_at", "id"])
@pytest.mark.parametrize("q", [None, "u-"])
async def test_users_walk(client: httpx.AsyncClient, sort: str | None, q: str | None) -> None:
    uid = await make_user("adm", Role.admin)
    h = await headers_for(uid)
    for n in ["u-b", "u-a", "u-b2", "u-a2", "x-1", "x-2"]:
        await make_user(n)
    params = {k: v for k, v in {"sort": sort, "q": q}.items() if v}
    full = await _walk(client, h, "/users", params, 200)
    assert len(full) == (4 if q else 7)
    for lim in (1, 2, 3):
        assert await _walk(client, h, "/users", params, lim) == full
    if sort in ("sub", "-sub"):
        items = (await client.get(f"{API}/users", params=params, headers=h)).json()["items"]
        subs = [i["sub"] for i in items]
        assert subs == sorted(subs, reverse=sort == "-sub")


@pytest.mark.parametrize("sort", [None, "status", "-status", "created_at", "-created_at", "-id"])
@pytest.mark.parametrize("q", [None, "src-a"])
async def test_jobs_walk(client: httpx.AsyncClient, sort: str | None, q: str | None) -> None:
    _, h = await actor("a")
    await _mk_jobs(client, h)
    params = {k: v for k, v in {"sort": sort, "q": q}.items() if v}
    full = await _walk(client, h, "/jobs", params, 200)
    assert len(full) == len(set(full)) == (6 if q else 9)
    for lim in (1, 2, 4):
        assert await _walk(client, h, "/jobs", params, lim) == full
    if sort in ("status", "-status"):
        items = (await client.get(f"{API}/jobs", params=params, headers=h)).json()["items"]
        st = [i["status"] for i in items]
        assert st == sorted(st, reverse=sort == "-status")


@pytest.mark.parametrize("path", ["/credentials", "/sources"])
async def test_credentials_sources_walk(client: httpx.AsyncClient, path: str) -> None:
    _, h = await actor("a")
    tid = (await client.post(f"{API}/targets", json=TARGET, headers=h)).json()["id"]
    for n in ["b", "a", "b", "a", "c"]:
        if path == "/sources":
            body: dict[str, Any] = {
                "name": n,
                "url": "https://www.reddit.com/r/pics/",
                "target_id": tid,
            }
        else:
            body = {"name": n, "site": "reddit", "kind": "token", "secret": "s"}
        r = await client.post(f"{API}{path}", json=body, headers=h)
        assert r.status_code == 201, r.text
    for sort in SORTS:
        params = {"sort": sort} if sort else {}
        full = await _walk(client, h, path, params, 200)
        assert len(full) == 5
        assert await _walk(client, h, path, params, 2) == full
    assert len(await _walk(client, h, path, {"q": "a"}, 1)) == 2


async def test_cursor_sort_mismatch_is_400(client: httpx.AsyncClient) -> None:
    _, h = await actor("a")
    await _mk_targets(client, h)
    r = await client.get(f"{API}/targets", params={"sort": "name", "limit": 2}, headers=h)
    c = r.json()["next_cursor"]
    for params in ({"sort": "-name"}, {"sort": "created_at"}, {}):
        r = await client.get(f"{API}/targets", params={**params, "cursor": c}, headers=h)
        assert r.status_code == 400, params
    r = await client.get(f"{API}/targets", params={"limit": 2}, headers=h)
    legacy = r.json()["next_cursor"]
    r = await client.get(f"{API}/targets", params={"cursor": legacy}, headers=h)
    assert r.status_code == 200
    r = await client.get(f"{API}/targets", params={"sort": "name", "cursor": legacy}, headers=h)
    assert r.status_code == 400
    r = await client.get(f"{API}/targets", params={"sort": "name", "cursor": "!!"}, headers=h)
    assert r.status_code == 422
    assert (
        await client.get(f"{API}/targets", params={"sort": "url"}, headers=h)
    ).status_code == 422
