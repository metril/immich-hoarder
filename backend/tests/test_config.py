import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_missing_master_key_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IH_MASTER_KEY", raising=False)
    monkeypatch.setenv("IH_SESSION_SECRET", "s")
    monkeypatch.setenv("IH_PUBLIC_URL", "http://x")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_env_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IH_MASTER_KEY", "k")
    monkeypatch.setenv("IH_SESSION_SECRET", "s")
    monkeypatch.setenv("IH_PUBLIC_URL", "http://x")
    monkeypatch.setenv("IH_OIDC_ADMIN_GROUPS", '["a","b"]')
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.oidc_admin_groups == ["a", "b"]
    assert s.oidc_user_groups == ["hoarder-users"]
    assert s.log_level == "info"
