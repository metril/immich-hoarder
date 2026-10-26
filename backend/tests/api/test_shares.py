import httpx
from helpers import TARGET, actor, make_user

from app.db.models import Role


def _body(uid: int, perm: str) -> dict[str, object]:
    return {
        "visibility": "restricted",
        "shares": [{"principal_type": "user", "principal_id": str(uid), "perm": perm}],
    }


async def test_source_revoked_share_blocks_update(client: httpx.AsyncClient) -> None:
    ua, ha = await actor("a")
    ub, hb = await actor("b")
    tid = (await client.post("/api/v1/targets", json=TARGET, headers=ha)).json()["id"]
    await client.put(f"/api/v1/targets/{tid}/shares", json=_body(ub, "use"), headers=ha)
    r = await client.post(
        "/api/v1/sources",
        json={"name": "s", "url": "https://www.reddit.com/r/pics/", "target_id": tid},
        headers=hb,
    )
    assert r.status_code == 201
    sid = r.json()["id"]
    await client.put(
        f"/api/v1/targets/{tid}/shares", json=_body(ub, "use") | {"shares": []}, headers=ha
    )
    p = await client.patch(f"/api/v1/sources/{sid}", json={"target_id": tid}, headers=hb)
    assert p.status_code == 403


async def test_edit_share_cannot_delete_or_reshare(client: httpx.AsyncClient) -> None:
    ua, ha = await actor("a")
    ub, hb = await actor("b")
    tid = (await client.post("/api/v1/targets", json=TARGET, headers=ha)).json()["id"]
    await client.put(f"/api/v1/targets/{tid}/shares", json=_body(ub, "edit"), headers=ha)
    assert (
        await client.patch(f"/api/v1/targets/{tid}", json={"name": "n"}, headers=hb)
    ).status_code == 200
    assert (await client.delete(f"/api/v1/targets/{tid}", headers=hb)).status_code == 403
    r = await client.put(f"/api/v1/targets/{tid}/shares", json=_body(ub, "edit"), headers=hb)
    assert r.status_code == 403
    g = await client.get(f"/api/v1/targets/{tid}/shares", headers=ha)
    assert g.json()["visibility"] == "restricted" and len(g.json()["shares"]) == 1


async def test_admin_patching_uses_owner_perms(client: httpx.AsyncClient) -> None:
    _, ha = await actor("a")
    _, hadm = await actor("adm", Role.admin)
    other_t = (await client.post("/api/v1/targets", json=TARGET, headers=hadm)).json()["id"]
    tid = (await client.post("/api/v1/targets", json=TARGET, headers=ha)).json()["id"]
    sid = (
        await client.post(
            "/api/v1/sources",
            json={"name": "s", "url": "https://www.reddit.com/r/pics/", "target_id": tid},
            headers=ha,
        )
    ).json()["id"]
    r = await client.patch(f"/api/v1/sources/{sid}", json={"target_id": other_t}, headers=hadm)
    assert r.status_code == 403


async def test_delete_removes_shares(client: httpx.AsyncClient) -> None:
    from sqlalchemy import select

    from app.db.engine import session_scope
    from app.db.models import Share

    _, ha = await actor("a")
    ub = await make_user("b")
    tid = (await client.post("/api/v1/targets", json=TARGET, headers=ha)).json()["id"]
    await client.put(f"/api/v1/targets/{tid}/shares", json=_body(ub, "use"), headers=ha)
    assert (await client.delete(f"/api/v1/targets/{tid}", headers=ha)).status_code == 204
    async with session_scope() as s:
        assert (await s.execute(select(Share))).first() is None


async def test_share_unknown_user_principal_422(client: httpx.AsyncClient) -> None:
    _, ha = await actor("a")
    tid = (await client.post("/api/v1/targets", json=TARGET, headers=ha)).json()["id"]
    for pid in ("99999", "not-a-number"):
        r = await client.put(f"/api/v1/targets/{tid}/shares", json=_body_pid(pid), headers=ha)
        assert r.status_code == 422 and r.json() == {"detail": "unknown user"}
    g = _body_pid("any-free-form-group") | {}
    g["shares"][0]["principal_type"] = "group"  # type: ignore[index]
    assert (
        await client.put(f"/api/v1/targets/{tid}/shares", json=g, headers=ha)
    ).status_code == 200


def _body_pid(pid: str) -> dict[str, object]:
    return {
        "visibility": "restricted",
        "shares": [{"principal_type": "user", "principal_id": pid, "perm": "use"}],
    }
