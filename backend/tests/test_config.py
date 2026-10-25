from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_missing_master_key_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IH_MASTER_KEY", raising=False)
    monkeypatch.setenv("IH_SESSION_SECRET", "s" * 32)
    monkeypatch.setenv("IH_PUBLIC_URL", "http://x")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_env_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IH_MASTER_KEY", "k" * 32)
    monkeypatch.setenv("IH_SESSION_SECRET", "s" * 32)
    monkeypatch.setenv("IH_PUBLIC_URL", "http://x")
    monkeypatch.setenv("IH_OIDC_ADMIN_GROUPS", '["a","b"]')
    s = Settings(_env_file=None)
    assert s.oidc_admin_groups == ["a", "b"]
    assert s.oidc_user_groups == ["hoarder-users"]
    assert s.log_level == "info"


@pytest.mark.parametrize("field", ["IH_MASTER_KEY", "IH_SESSION_SECRET"])
@pytest.mark.parametrize("value", ["", "short", "x" * 31])
def test_short_secret_rejected(monkeypatch: pytest.MonkeyPatch, field: str, value: str) -> None:
    monkeypatch.setenv("IH_MASTER_KEY", "k" * 32)
    monkeypatch.setenv("IH_SESSION_SECRET", "s" * 32)
    monkeypatch.setenv("IH_PUBLIC_URL", "http://x")
    monkeypatch.setenv(field, value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_secret_file_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mk = tmp_path / "mk"
    mk.write_text("m" * 40 + "\n")
    oc = tmp_path / "oc"
    oc.write_text("oidc-secret")
    monkeypatch.delenv("IH_MASTER_KEY", raising=False)
    monkeypatch.setenv("IH_MASTER_KEY_FILE", str(mk))
    monkeypatch.setenv("IH_OIDC_CLIENT_SECRET_FILE", str(oc))
    monkeypatch.setenv("IH_SESSION_SECRET", "s" * 32)
    monkeypatch.setenv("IH_PUBLIC_URL", "http://x")
    s = Settings(_env_file=None)
    assert s.master_key.get_secret_value() == "m" * 40
    assert s.oidc_client_secret is not None
    assert s.oidc_client_secret.get_secret_value() == "oidc-secret"


def test_direct_env_wins_over_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mk = tmp_path / "mk"
    mk.write_text("f" * 40)
    monkeypatch.setenv("IH_MASTER_KEY", "d" * 40)
    monkeypatch.setenv("IH_MASTER_KEY_FILE", str(mk))
    monkeypatch.setenv("IH_SESSION_SECRET", "s" * 32)
    monkeypatch.setenv("IH_PUBLIC_URL", "http://x")
    assert Settings(_env_file=None).master_key.get_secret_value() == "d" * 40
