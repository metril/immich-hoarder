import httpx
import pytest
from helpers import TARGET, actor
from sqlalchemy import event

from app.db.models import Role

CRED = {"name": "c", "site": "reddit", "kind": "token", "secret": "s3cr3t-value"}


def _share(uid: int, perm: str) -> dict[str, object]:
    return {
        "visibility": "restricted",
        "shares": [{"principal_type": "user", "principal_id": str(uid), "perm": perm}],
    }


@pytest.mark.parametrize(("kind", "body"), [("targets", TARGET), ("credentials", CRED)])
async def test_can_edit_per_principal(
    client: httpx.AsyncClient, kind: str, body: dict[str, str]
) -> None:
    uo, ho = await actor("owner")
    ue, he = await actor("editor")
    uu, hu = await actor("user")
    _, hadm = await actor("adm", Role.admin)
    _, hn = await actor("nobody")
    r = await client.post(f"/api/v1/{kind}", json=body, headers=ho)
    assert r.status_code == 201 and r.json()["can_edit"] is True
    oid = r.json()["id"]
    shares = _share(ue, "edit")
    shares["shares"].append({"principal_type": "user", "principal_id": str(uu), "perm": "use"})  # type: ignore[attr-defined]
    assert (
        await client.put(f"/api/v1/{kind}/{oid}/shares", json=shares, headers=ho)
    ).status_code == 200
    for h, want in ((ho, True), (hadm, True), (he, True), (hu, False)):
        lst = (await client.get(f"/api/v1/{kind}", headers=h)).json()["items"]
        assert [i["can_edit"] for i in lst] == [want]
        assert (await client.get(f"/api/v1/{kind}/{oid}", headers=h)).json()["can_edit"] is want
    # everyone-visibility: use only
    await client.put(
        f"/api/v1/{kind}/{oid}/shares", json={"visibility": "everyone", "shares": []}, headers=ho
    )
    lst = (await client.get(f"/api/v1/{kind}", headers=hn)).json()["items"]
    assert [i["can_edit"] for i in lst] == [False]
    # agrees with PATCH
    assert (
        await client.patch(f"/api/v1/{kind}/{oid}", json={"name": "z"}, headers=hn)
    ).status_code == 403


async def test_list_can_edit_no_n_plus_one(client: httpx.AsyncClient) -> None:
    import app.db.engine as eng_mod  # noqa: PLC0415
    from app.db.engine import session_scope  # noqa: PLC0415
    from app.db.models import ImmichTarget  # noqa: PLC0415

    uid, h = await actor("a")
    async with session_scope() as s:
        s.add_all(
            ImmichTarget(name=f"t{i}", url="u", api_key_enc=b"x", owner_id=uid) for i in range(30)
        )
    n = 0

    def count(*_: object) -> None:
        nonlocal n
        n += 1

    assert eng_mod._engine is not None
    eng = eng_mod._engine.sync_engine
    event.listen(eng, "before_cursor_execute", count)
    try:
        r = await client.get("/api/v1/targets", headers=h)
    finally:
        event.remove(eng, "before_cursor_execute", count)
    assert len(r.json()["items"]) == 30 and n < 10


@pytest.mark.parametrize(("kind", "body"), [("targets", TARGET), ("credentials", CRED)])
async def test_can_use_matches_perm_use(
    client: httpx.AsyncClient, kind: str, body: dict[str, str]
) -> None:
    uo, ho = await actor("owner2")
    uu, hu = await actor("viewer")
    _, hadm = await actor("adm2", Role.admin)
    r = await client.post(f"/api/v1/{kind}", json=body, headers=ho)
    assert r.json()["can_use"] is True
    oid = r.json()["id"]
    await client.put(
        f"/api/v1/{kind}/{oid}/shares",
        json={"visibility": "everyone", "shares": []},
        headers=ho,
    )
    for h in (ho, hu, hadm):
        assert (await client.get(f"/api/v1/{kind}", headers=h)).json()["items"][0]["can_use"]
        assert (await client.get(f"/api/v1/{kind}/{oid}", headers=h)).json()["can_use"] is True


async def test_source_can_use_and_run_gate(client: httpx.AsyncClient) -> None:
    _, ho = await actor("srcowner")
    _, hv = await actor("srcviewer")
    t = (await client.post("/api/v1/targets", json=TARGET, headers=ho)).json()
    r = await client.post(
        "/api/v1/sources",
        json={"name": "s", "url": "https://www.reddit.com/r/pics/", "target_id": t["id"]},
        headers=ho,
    )
    assert r.status_code == 201, r.text
    assert r.json()["can_use"] is True
    sid = r.json()["id"]
    assert (await client.get(f"/api/v1/sources/{sid}", headers=ho)).json()["can_use"] is True
    assert (await client.get("/api/v1/sources", headers=ho)).json()["items"][0]["can_use"] is True
    await client.put(
        f"/api/v1/sources/{sid}/shares",
        json={"visibility": "everyone", "shares": []},
        headers=ho,
    )
    item = (await client.get("/api/v1/sources", headers=hv)).json()["items"][0]
    assert item["can_use"] is True and item["can_edit"] is False
