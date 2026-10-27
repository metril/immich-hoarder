import fake_idp
import httpx
import respx
from fastapi import FastAPI

from app.auth.settings import import_legacy_env, reload_auth
from app.core.crypto import SecretBox
from app.db.engine import session_scope
from app.db.models import Setting

API = "/api/v1"
PW = "correct horse battery"
OIDC = {
    "enabled": True,
    "issuer": fake_idp.ISSUER,
    "client_id": fake_idp.CLIENT_ID,
    "client_secret": "s3cret-value",
}


async def _admin(c: httpx.AsyncClient) -> dict[str, str]:
    r = await c.post(f"{API}/auth/setup", json={"username": "root", "password": PW})
    assert r.status_code == 200
    return {"X-CSRF-Token": c.cookies["ih_csrf"]}


async def test_roundtrip_masks_and_encrypts(
    plain: httpx.AsyncClient, idp: fake_idp.FakeIdp, app_plain: FastAPI
) -> None:
    h = await _admin(plain)
    r = await plain.put(f"{API}/settings", json={"oidc": OIDC}, headers=h)
    assert r.status_code == 200
    got = r.json()["oidc"]
    assert got["client_secret_set"] is True and "client_secret" not in got
    assert "s3cret-value" not in (await plain.get(f"{API}/settings", headers=h)).text
    async with session_scope() as s:
        row = await s.get(Setting, "oidc")
        assert row is not None and "s3cret-value" not in str(row.value)
    # blank secret keeps the stored one
    r = await plain.put(
        f"{API}/settings", json={"oidc": {**OIDC, "client_secret": "", "client_id": "x"}}, headers=h
    )
    assert r.json()["oidc"]["client_secret_set"] is True
    assert app_plain.state.oidc_cfg.client_secret == "s3cret-value"
    assert app_plain.state.oidc_cfg.client_id == "x"


async def test_reload_is_live(
    plain: httpx.AsyncClient, idp: fake_idp.FakeIdp, app_plain: FastAPI
) -> None:
    assert (await plain.head(f"{API}/auth/login")).status_code == 503
    h = await _admin(plain)
    await plain.put(f"{API}/settings", json={"oidc": OIDC}, headers=h)
    assert (await plain.head(f"{API}/auth/login")).status_code == 204
    assert (await plain.get(f"{API}/auth/status")).json()["oidc_enabled"] is True
    await plain.put(f"{API}/settings", json={"oidc": {**OIDC, "enabled": False}}, headers=h)
    assert (await plain.head(f"{API}/auth/login")).status_code == 503


async def test_enable_requires_fields(plain: httpx.AsyncClient) -> None:
    h = await _admin(plain)
    r = await plain.put(
        f"{API}/settings", json={"oidc": {"enabled": True, "issuer": fake_idp.ISSUER}}, headers=h
    )
    assert r.status_code == 422


async def test_oidc_test_endpoint(plain: httpx.AsyncClient, idp: fake_idp.FakeIdp) -> None:
    h = await _admin(plain)
    url = f"{API}/settings/oidc/test"
    r = await plain.post(url, json={"issuer": fake_idp.ISSUER}, headers=h)
    assert r.json() == {"ok": True, "error": None}
    assert (await plain.post(url, json={}, headers=h)).json()["ok"] is False
    with respx.mock(assert_all_called=False) as router:
        router.get("https://bad.test/.well-known/openid-configuration").respond(404)
        r = await plain.post(url, json={"issuer": "https://bad.test"}, headers=h)
    assert r.json()["ok"] is False and "404" in r.json()["error"]


async def test_disable_local_after_passing_test(
    plain: httpx.AsyncClient, idp: fake_idp.FakeIdp
) -> None:
    h = await _admin(plain)
    await plain.put(f"{API}/settings", json={"oidc": OIDC}, headers=h)
    r = await plain.put(f"{API}/settings", json={"auth": {"local_enabled": False}}, headers=h)
    assert r.status_code == 200
    # OIDC can no longer be turned off while local login is off
    r = await plain.put(f"{API}/settings", json={"oidc": {**OIDC, "enabled": False}}, headers=h)
    assert r.status_code == 401  # local session is rejected once local accounts are off


async def test_public_url_used_for_redirect(
    plain: httpx.AsyncClient, idp: fake_idp.FakeIdp
) -> None:
    h = await _admin(plain)
    await plain.put(
        f"{API}/settings",
        json={"oidc": OIDC, "auth": {"public_url": "https://hoarder.example.com/"}},
        headers=h,
    )
    r = await plain.get(f"{API}/auth/login")
    assert (
        "redirect_uri=https%3A%2F%2Fhoarder.example.com%2Fapi%2Fv1%2Fauth%2Fcallback"
        in (r.headers["location"])
    )


async def test_legacy_env_import_once(
    app_plain: FastAPI,
    monkeypatch,
    idp: fake_idp.FakeIdp,  # type: ignore[no-untyped-def]
) -> None:
    monkeypatch.setenv("IH_OIDC_ISSUER", fake_idp.ISSUER)
    monkeypatch.setenv("IH_OIDC_CLIENT_ID", "legacy")
    monkeypatch.setenv("IH_OIDC_CLIENT_SECRET", "legacy-secret")
    monkeypatch.setenv("IH_OIDC_ADMIN_GROUPS", '["ops"]')
    monkeypatch.setenv("IH_PUBLIC_URL", "https://legacy.example.com/")
    box = SecretBox(app_plain.state.settings.master_key_value())
    async with session_scope() as s:
        await import_legacy_env(s, box)
        await reload_auth(app_plain, s)
    cfg = app_plain.state.oidc_cfg
    assert cfg.active and cfg.client_id == "legacy" and cfg.admin_groups == ("ops",)
    assert app_plain.state.auth_cfg.public_url == "https://legacy.example.com"
    monkeypatch.setenv("IH_OIDC_CLIENT_ID", "changed")
    async with session_scope() as s:  # DB wins afterwards
        await import_legacy_env(s, box)
        await reload_auth(app_plain, s)
    assert app_plain.state.oidc_cfg.client_id == "legacy"
