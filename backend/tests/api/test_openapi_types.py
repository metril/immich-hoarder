import json
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from helpers import actor

from app.core.config import Settings
from app.db.models import Role
from app.main import create_app

API = "/api/v1"


def _schema(settings: Settings) -> dict[str, Any]:
    return create_app(settings).openapi()  # type: ignore[no-any-return]


def _ref(op: dict[str, Any], code: str = "200") -> str:
    s = op["responses"][code]["content"]["application/json"]["schema"]
    return str(s.get("$ref") or s["items"]["$ref"])


@pytest.fixture
async def env(settings: Settings) -> AsyncIterator[tuple[FastAPI, httpx.AsyncClient]]:
    app = create_app(settings)
    app.state.runtime_enabled = False
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as c,
    ):
        yield app, c


def test_me_schema_typed(settings: Settings) -> None:
    sch = _schema(settings)
    assert "MeOut" in sch["components"]["schemas"]
    assert _ref(sch["paths"][f"{API}/auth/me"]["get"]).endswith("/MeOut")


def test_settings_schema_typed(settings: Settings) -> None:
    sch = _schema(settings)
    p = sch["paths"][f"{API}/settings"]
    assert _ref(p["get"]).endswith("/SettingsDoc")
    assert _ref(p["put"]).endswith("/SettingsDoc")
    body = p["put"]["requestBody"]["content"]["application/json"]["schema"]
    assert body["$ref"].endswith("/SettingsDoc")


def test_admin_and_extractors_typed(settings: Settings) -> None:
    sch = _schema(settings)
    paths = sch["paths"]
    assert _ref(paths[f"{API}/admin/backup"]["post"], "201").endswith("/BackupOut")
    assert _ref(paths[f"{API}/admin/backups"]["get"]).endswith("/BackupList")
    assert _ref(paths[f"{API}/admin/maintenance/prune"]["post"]).endswith("/PruneOut")
    assert _ref(paths[f"{API}/admin/import"]["post"]).endswith("/ImportResult")
    assert _ref(paths[f"{API}/extractors"]["get"]).endswith("/ExtractorList")
    comps = sch["components"]["schemas"]
    assert set(comps["BackupInfo"]["properties"]) == {"file", "size", "mtime"}


def test_source_filters_schema_has_min_width(settings: Settings) -> None:
    comps = _schema(settings)["components"]["schemas"]
    for name in ("SourceIn", "SourcePatch", "SourceOut", "RipIn"):
        f = comps[name]["properties"]["filters"]
        assert "min_width" in json.dumps(f), name
        assert "credential_ids" in json.dumps(comps[name]["properties"]["notify"]), name


def test_import_body_is_yaml(settings: Settings) -> None:
    op = _schema(settings)["paths"][f"{API}/admin/import"]["post"]
    assert op["requestBody"]["content"] == {"application/yaml": {"schema": {"type": "string"}}}
    assert op["requestBody"]["required"] is True


def test_openapi_dump_deterministic(tmp_path: Path) -> None:
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    for out in (a, b):
        subprocess.run(
            [sys.executable, "-m", "app.openapi_dump", str(out)],
            check=True,
            capture_output=True,
            env={"PATH": "/usr/bin:/bin"},
        )
    assert a.read_bytes() == b.read_bytes()
    doc = json.loads(a.read_text())
    assert doc["info"]["version"] == "0"
    assert a.read_text().endswith("}\n")


async def test_me_returns_typed_payload(env: Any) -> None:
    _, c = env
    uid, h = await actor("a", Role.admin)
    r = await c.get(f"{API}/auth/me", headers=h)
    assert r.status_code == 200
    assert set(r.json()) == {"id", "email", "name", "role", "groups"} and r.json()["id"] == uid


async def test_settings_put_unknown_key_422(env: Any) -> None:
    _, c = env
    _, h = await actor("adm", Role.admin)
    assert (await c.put(f"{API}/settings", json={"bogus": 1}, headers=h)).status_code == 422


async def test_settings_put_single_key_keeps_others(env: Any) -> None:
    _, c = env
    _, h = await actor("adm", Role.admin)
    await c.put(f"{API}/settings", json={"runtime": {"retention_days": 5}}, headers=h)
    r = await c.put(f"{API}/settings", json={"notify": {"on": ["success"]}}, headers=h)
    assert r.status_code == 200
    assert r.json()["runtime"]["retention_days"] == 5
    assert r.json()["notify"]["on"] == ["success"]
    got = (await c.get(f"{API}/settings", headers=h)).json()
    assert got["runtime"]["retention_days"] == 5 and got["notify"]["on"] == ["success"]


async def test_settings_422_loc_nested(env: Any) -> None:
    _, c = env
    _, h = await actor("adm", Role.admin)
    r = await c.put(f"{API}/settings", json={"runtime": {"retention_days": 0}}, headers=h)
    assert r.status_code == 422
    assert ["body", "runtime", "retention_days"] in [d["loc"] for d in r.json()["detail"]]


async def test_login_head_503_unconfigured_204_configured(env: Any) -> None:
    app, c = env
    assert (await c.head(f"{API}/auth/login")).status_code == 503

    async def boom(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("authorize_redirect must not be called for HEAD")

    app.state.oauth = SimpleNamespace(oidc=SimpleNamespace(authorize_redirect=boom))
    assert (await c.head(f"{API}/auth/login")).status_code == 204


def test_api_key_scope_enum_matches_scopes(settings: Settings) -> None:
    from app.auth.principal import SCOPES

    s = _schema(settings)["components"]["schemas"]["ApiKeyIn"]["properties"]["scopes"]
    assert set(s["items"]["enum"]) == SCOPES
