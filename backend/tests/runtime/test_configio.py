import base64
from collections.abc import AsyncIterator

import httpx
import pytest
import yaml
from fastapi import FastAPI
from sqlalchemy import delete, select

from app.auth.apikeys import create_api_key
from app.auth.principal import SCOPES
from app.core.config import Settings
from app.core.crypto import SecretBox
from app.db.engine import session_scope
from app.db.models import Credential, ImmichTarget, Role, Setting, Share, Source, User
from app.main import create_app

U = "/api/v1/admin"
SRC_URL = "https://www.reddit.com/r/pics/"


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    app: FastAPI = create_app(settings)
    app.state.runtime_enabled = False
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as c,
    ):
        yield c


async def actor(sub: str, role: Role = Role.user) -> tuple[int, dict[str, str]]:
    async with session_scope() as s:
        grp = "hoarder-admins" if role == Role.admin else "hoarder-users"
        u = User(sub=sub, role=role, groups=[grp])
        s.add(u)
        await s.flush()
        sc = sorted(SCOPES if role == Role.admin else SCOPES - {"admin"})
        _, raw = await create_api_key(s, u, "t", sc, None)
        return u.id, {"X-API-Key": raw}


async def seed(client: httpx.AsyncClient, h: dict[str, str]) -> None:
    r = await client.post(
        "/api/v1/targets",
        json={"name": "t1", "url": "http://immich", "api_key": "KEY-SECRET"},
        headers=h,
    )
    tid = r.json()["id"]
    c = await client.post(
        "/api/v1/credentials",
        json={"name": "ap", "site": "n", "kind": "apprise", "secret": "json://notify.example/x"},
        headers=h,
    )
    cid = c.json()["id"]
    r = await client.post(
        "/api/v1/sources",
        json={
            "name": "s1",
            "url": SRC_URL,
            "target_id": tid,
            "notify": {"credential_ids": [cid], "on": ["success"]},
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    await client.put(
        f"/api/v1/targets/{tid}/shares",
        json={
            "visibility": "restricted",
            "shares": [{"principal_type": "group", "principal_id": "g", "perm": "use"}],
        },
        headers=h,
    )


async def test_export_omits_secrets_by_default(client: httpx.AsyncClient) -> None:
    _, h = await actor("adm", Role.admin)
    await seed(client, h)
    r = await client.get(f"{U}/export", headers=h)
    assert r.status_code == 200
    assert "KEY-SECRET" not in r.text and "notify.example" not in r.text
    doc = yaml.safe_load(r.text)
    assert doc["version"] == 1
    assert doc["targets"][0]["name"] == "t1" and doc["targets"][0]["owner"] == "adm"
    assert "api_key_enc" not in doc["targets"][0]
    assert doc["credentials"][0]["kind"] == "apprise"
    s = doc["sources"][0]
    assert s["target"] == "t1" and s["notify"]["credentials"] == ["ap"]
    assert doc["shares"] == [
        {
            "resource_type": "target",
            "resource": "t1",
            "owner": "adm",
            "principal_type": "group",
            "principal_id": "g",
            "perm": "use",
        }
    ]
    assert set(doc["settings"]) == {"rip", "runtime", "notify"}


async def test_roundtrip_encrypted_secrets_same_key(
    client: httpx.AsyncClient, settings: Settings
) -> None:
    _, h = await actor("adm", Role.admin)
    await seed(client, h)
    r = await client.get(f"{U}/export?secrets=encrypted", headers=h)
    assert "KEY-SECRET" not in r.text
    doc = yaml.safe_load(r.text)
    box = SecretBox(settings.master_key.get_secret_value())
    assert box.decrypt(base64.b64decode(doc["targets"][0]["api_key_enc"])) == b"KEY-SECRET"
    # wipe and re-import
    async with session_scope() as s:
        await s.execute(delete(Source))
        await s.execute(delete(Credential))
        await s.execute(delete(ImmichTarget))
    r2 = await client.post(f"{U}/import", content=r.text, headers=h)
    assert r2.status_code == 200, r2.text
    out = r2.json()
    assert out["errors"] == []
    assert out["created"]["targets"] == 1 and out["created"]["sources"] == 1
    async with session_scope() as s:
        t = (await s.execute(ImmichTarget.__table__.select())).first()
        assert t is not None
        tgt = await s.get(ImmichTarget, t.id)
        assert tgt and box.decrypt(tgt.api_key_enc) == b"KEY-SECRET"
        cr = (await s.execute(Credential.__table__.select())).first()
        assert cr is not None
        cred = await s.get(Credential, cr.id)
        assert cred and box.decrypt(cred.secret_enc) == b"json://notify.example/x"
        src = (await s.execute(Source.__table__.select())).first()
        assert src is not None
        assert src.notify["credential_ids"] == [cr.id] and src.target_id == t.id


async def test_import_dry_run_reports_without_writing(client: httpx.AsyncClient) -> None:
    _, h = await actor("adm", Role.admin)
    doc = (
        "version: 1\ntargets:\n- {name: n1, url: 'http://immich', api_key: k}\n"
        "sources:\n- {name: s, url: 'https://www.reddit.com/r/pics/', target: n1}\n"
    )
    r = await client.post(f"{U}/import?dry_run=true", content=doc, headers=h)
    assert r.status_code == 200 and r.json()["errors"] == []
    assert r.json()["created"]["targets"] == 1 and r.json()["created"]["sources"] == 1
    async with session_scope() as s:
        assert (await s.execute(ImmichTarget.__table__.select())).first() is None
        assert (await s.execute(Source.__table__.select())).first() is None
    r = await client.post(f"{U}/import", content=doc, headers=h)
    assert r.json()["errors"] == []
    async with session_scope() as s:
        assert (await s.execute(Source.__table__.select())).first() is not None


async def test_import_skips_existing_and_validates(client: httpx.AsyncClient) -> None:
    _, h = await actor("adm", Role.admin)
    await seed(client, h)
    doc = (
        "version: 1\ntargets:\n- {name: t1, url: 'http://immich', api_key: k}\n"
        "- {name: t2, url: 'http://immich', api_key: k}\n"
        "sources:\n- {name: s1, url: 'https://www.reddit.com/r/pics/', target: t1}\n"
        "- {name: bad, url: 'https://www.reddit.com/r/pics/', target: t2, schedule_cron: nope}\n"
        "- {name: bad2, url: 'https://x.invalid/', target: t2}\n"
        "- {name: bad3, url: 'https://www.reddit.com/r/pics/', target: ghost}\n"
        "- {name: bad4, url: 'https://www.reddit.com/r/pics/', target: t2, notify: "
        "{credentials: [ghost]}}\n"
    )
    r = await client.post(f"{U}/import", content=doc, headers=h)
    out = r.json()
    assert out["skipped"]["targets"] == 1 and out["skipped"]["sources"] == 1
    assert out["created"]["targets"] == 1
    assert len(out["errors"]) == 4
    # whole import rolled back
    async with session_scope() as s:
        names = [t.name for t in (await s.execute(select(ImmichTarget))).scalars()]
        assert names == ["t1"]


async def test_import_bad_secrets_and_apprise(
    client: httpx.AsyncClient, settings: Settings
) -> None:
    _, h = await actor("adm", Role.admin)
    other = SecretBox("another-master-key-0123456789abcdef-q")
    tok = base64.b64encode(other.encrypt(b"SUPERSECRET")).decode()
    doc = f"version: 1\ntargets:\n- {{name: t, url: 'http://immich', api_key_enc: {tok}}}\n"
    out = (await client.post(f"{U}/import", content=doc, headers=h)).json()
    assert len(out["errors"]) == 1 and "SUPERSECRET" not in str(out)
    doc = (
        "version: 1\ncredentials:\n- {name: a, site: n, kind: apprise, "
        "secret: 'json://127.0.0.1/hook'}\n"
    )
    out = (await client.post(f"{U}/import", content=doc, headers=h)).json()
    assert len(out["errors"]) == 1 and "127.0.0.1" not in str(out)


async def test_import_rejects_unsafe_yaml_tags(client: httpx.AsyncClient) -> None:
    _, h = await actor("adm", Role.admin)
    r = await client.post(
        f"{U}/import", content="version: 1\nx: !!python/object/apply:os.system ['id']\n", headers=h
    )
    assert r.status_code == 422
    for body in ("- 1\n- 2\n", "version: 2\n", "targets: []\n"):
        assert (await client.post(f"{U}/import", content=body, headers=h)).status_code == 422
    big = "version: 1\n#" + "a" * (5 * 1024 * 1024)
    assert (await client.post(f"{U}/import", content=big, headers=h)).status_code == 413


async def test_import_admin_only(client: httpx.AsyncClient) -> None:
    _, h = await actor("u")
    assert (await client.get(f"{U}/export", headers=h)).status_code == 403
    assert (await client.post(f"{U}/import", content="version: 1\n", headers=h)).status_code == 403


async def _wipe() -> None:
    async with session_scope() as s:
        await s.execute(delete(Share))
        await s.execute(delete(Source))
        await s.execute(delete(Credential))
        await s.execute(delete(ImmichTarget))


async def test_roundtrip_shared_target_two_users(client: httpx.AsyncClient) -> None:
    _, ha = await actor("adm", Role.admin)
    ua, hua = await actor("a")
    ub, hub = await actor("b")
    t = await client.post(
        "/api/v1/targets", json={"name": "tt", "url": "http://immich", "api_key": "k"}, headers=hua
    )
    tid = t.json()["id"]
    sh = {
        "visibility": "restricted",
        "shares": [{"principal_type": "user", "principal_id": str(ub), "perm": "use"}],
    }
    assert (
        await client.put(f"/api/v1/targets/{tid}/shares", json=sh, headers=hua)
    ).status_code == 200
    r = await client.post(
        "/api/v1/sources", json={"name": "sb", "url": SRC_URL, "target_id": tid}, headers=hub
    )
    assert r.status_code == 201
    exp = (await client.get(f"{U}/export?secrets=encrypted", headers=ha)).text
    await _wipe()
    out = (await client.post(f"{U}/import", content=exp, headers=ha)).json()
    assert out["errors"] == [] and out["created"]["sources"] == 1
    assert out["created"]["shares"] == 1


async def test_target_url_userinfo_omit_and_encrypted(client: httpx.AsyncClient) -> None:
    _, h = await actor("adm", Role.admin)
    await client.post(
        "/api/v1/targets",
        json={"name": "tu", "url": "http://user:PW123@immich", "api_key": "k"},
        headers=h,
    )
    omit = (await client.get(f"{U}/export", headers=h)).text
    assert "PW123" not in omit and "url_enc" not in omit
    enc = (await client.get(f"{U}/export?secrets=encrypted", headers=h)).text
    assert "PW123" not in enc and "url_enc" in enc
    await _wipe()
    out = (await client.post(f"{U}/import", content=enc, headers=h)).json()
    assert out["errors"] == []
    async with session_scope() as s:
        tgt = (await s.execute(select(ImmichTarget))).scalars().one()
        assert tgt.url == "http://user:PW123@immich"


async def test_owner_fallback_to_importing_admin(client: httpx.AsyncClient) -> None:
    aid, h = await actor("adm", Role.admin)
    doc = (
        "version: 1\ntargets:\n- {name: n, url: 'http://immich', api_key: k, owner: nobody}\n"
        "- {name: m, url: 'http://immich', api_key: k}\n"
    )
    out = (await client.post(f"{U}/import", content=doc, headers=h)).json()
    assert out["errors"] == []
    async with session_scope() as s:
        owners = {t.owner_id for t in (await s.execute(select(ImmichTarget))).scalars()}
        assert owners == {aid}


async def test_roundtrip_notify_urls_and_source_proxy_enc(client: httpx.AsyncClient) -> None:
    _, h = await actor("adm", Role.admin)
    r = await client.put(
        "/api/v1/settings",
        json={"notify": {"urls": ["json://notify.example/hook"], "on": ["success"]}},
        headers=h,
    )
    assert r.status_code == 200
    tid = (
        await client.post(
            "/api/v1/targets",
            json={"name": "t", "url": "http://immich", "api_key": "k"},
            headers=h,
        )
    ).json()["id"]
    r = await client.post(
        "/api/v1/sources",
        json={
            "name": "sp",
            "url": SRC_URL,
            "target_id": tid,
            "proxy": "http://pu:PROXYPW@proxy.example:8080",
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    omit = (await client.get(f"{U}/export", headers=h)).text
    assert "PROXYPW" not in omit and "notify.example/hook" not in omit
    enc = (await client.get(f"{U}/export?secrets=encrypted", headers=h)).text
    assert "PROXYPW" not in enc and "notify.example" not in enc
    assert "urls_enc" in enc and "proxy_enc" in enc
    await _wipe()
    async with session_scope() as s:
        await s.execute(delete(Setting))
    out = (await client.post(f"{U}/import", content=enc, headers=h)).json()
    assert out["errors"] == [], out
    async with session_scope() as s:
        src = (await s.execute(select(Source))).scalars().one()
        assert src.proxy == "http://pu:PROXYPW@proxy.example:8080"
        row = await s.get(Setting, "notify")
        assert row and row.value["urls"] == ["json://notify.example/hook"]
