import logging
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.apikeys import create_api_key
from app.auth.principal import SCOPES
from app.db import engine as eng
from app.db.engine import session_scope
from app.db.migrate import upgrade_head_async
from app.db.models import Role, Setting, User
from app.rip.settings import RipSettings, load_rip_settings
from app.runtime.settings import (
    NotifySettings,
    RuntimeSettings,
    load_notify_settings,
    load_runtime_settings,
)

BAD_URL = "notaschema-secret-token://x"


async def _admin_headers() -> dict[str, str]:
    async with session_scope() as s:
        u = User(sub="adm", role=Role.admin, groups=["hoarder-admins"])
        s.add(u)
        await s.flush()
        _, raw = await create_api_key(s, u, "t", sorted(SCOPES), None)
    return {"X-API-Key": raw}


@pytest.fixture
async def session(tmp_path: Path) -> AsyncSession:  # type: ignore[misc]
    url = f"sqlite+aiosqlite:///{tmp_path / 'm.db'}"
    await upgrade_head_async(url)
    engine = eng.make_engine(url)
    async with AsyncSession(engine) as s:
        yield s
        await s.rollback()
    await engine.dispose()


async def test_unknown_settings_key_422(client: httpx.AsyncClient) -> None:
    h = await _admin_headers()
    r = await client.put("/api/v1/settings", json={"bogus": {"a": 1}}, headers=h)
    assert r.status_code == 422
    r = await client.put("/api/v1/settings", json={"runtime": {"retention_days": 0}}, headers=h)
    assert r.status_code == 422
    r = await client.put("/api/v1/settings", json={"notify": {"urls": [BAD_URL]}}, headers=h)
    assert r.status_code == 422
    assert "secret-token" not in r.text
    ok = {"runtime": {"retention_days": 5}, "notify": {"on": ["success"]}}
    r = await client.put("/api/v1/settings", json=ok, headers=h)
    assert r.status_code == 200
    assert r.json()["runtime"]["retention_days"] == 5


async def test_put_ignores_unknown_keys_already_stored(client: httpx.AsyncClient) -> None:
    h = await _admin_headers()
    async with session_scope() as s:
        s.add(Setting(key="legacy", value={"x": 1}))
    r = await client.put("/api/v1/settings", json={"rip": {}}, headers=h)
    assert r.status_code == 200
    assert r.json()["legacy"] == {"x": 1}
    r = await client.put("/api/v1/settings", json={"legacy": {}}, headers=h)
    assert r.status_code == 422


def test_runtime_validates_cron_and_ranges() -> None:
    d = RuntimeSettings()
    assert (d.retention_days, d.backup_cron, d.backup_keep) == (30, "0 3 * * *", 7)
    assert (d.max_concurrent_jobs, d.cancel_grace_s) == (None, 10)
    for bad in (
        {"backup_cron": "not a cron"},
        {"retention_days": 0},
        {"retention_days": 3651},
        {"backup_keep": -1},
        {"backup_keep": 366},
        {"max_concurrent_jobs": 0},
        {"max_concurrent_jobs": 65},
        {"bogus": 1},
    ):
        with pytest.raises(ValidationError):
            RuntimeSettings.model_validate(bad)
    assert RuntimeSettings(backup_keep=0, max_concurrent_jobs=64).backup_keep == 0


def test_notify_rejects_bad_apprise_url() -> None:
    assert NotifySettings().on == ["failure"]
    assert NotifySettings(urls=["json://localhost/"]).urls == ["json://localhost/"]
    with pytest.raises(ValidationError) as ei:
        NotifySettings(urls=["json://localhost/", BAD_URL])
    msg = str(ei.value.errors(include_url=False, include_input=False))
    assert "invalid notification url at index 1" in msg
    assert "secret-token" not in msg
    with pytest.raises(ValidationError):
        NotifySettings.model_validate({"on": ["bogus"]})


async def test_loaders_default_on_missing_and_invalid(
    session: AsyncSession, caplog: pytest.LogCaptureFixture
) -> None:
    assert await load_runtime_settings(session) == RuntimeSettings()
    assert await load_notify_settings(session) == NotifySettings()
    assert await load_rip_settings(session) == RipSettings()
    assert not caplog.records
    session.add_all(
        [
            Setting(key="runtime", value={"retention_days": 0}),
            Setting(key="notify", value={"urls": [BAD_URL]}),
            Setting(key="rip", value={"bogus": 1}),
        ]
    )
    await session.flush()
    with caplog.at_level(logging.WARNING):
        assert await load_runtime_settings(session) == RuntimeSettings()
        assert await load_notify_settings(session) == NotifySettings()
        assert await load_rip_settings(session) == RipSettings()
    assert len(caplog.records) == 3
    assert "secret-token" not in caplog.text
    session.add(Setting(key="x", value={}))
    row = await session.get(Setting, "runtime")
    assert row
    row.value = {"retention_days": 9}
    await session.flush()
    assert (await load_runtime_settings(session)).retention_days == 9
