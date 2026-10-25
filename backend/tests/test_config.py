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
