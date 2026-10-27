from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_secrets_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IH_MASTER_KEY", raising=False)
    monkeypatch.delenv("IH_SESSION_SECRET", raising=False)
    s = Settings()
    assert s.master_key is None and s.session_secret is None
    assert not s.break_glass and not s.break_glass_reset


def test_env_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IH_MASTER_KEY", "k" * 32)
    monkeypatch.setenv("IH_SESSION_SECRET", "s" * 32)
    monkeypatch.setenv("IH_BREAK_GLASS", "true")
    s = Settings()
    assert s.break_glass is True
    assert s.log_level == "info"


@pytest.mark.parametrize("field", ["IH_MASTER_KEY", "IH_SESSION_SECRET"])
@pytest.mark.parametrize("value", ["", "short", "x" * 31])
def test_short_secret_rejected(monkeypatch: pytest.MonkeyPatch, field: str, value: str) -> None:
    monkeypatch.setenv("IH_MASTER_KEY", "k" * 32)
    monkeypatch.setenv("IH_SESSION_SECRET", "s" * 32)
    monkeypatch.setenv(field, value)
    with pytest.raises(ValidationError):
        Settings()


def test_secret_file_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mk = tmp_path / "mk"
    mk.write_text("m" * 40 + "\n")
    monkeypatch.delenv("IH_MASTER_KEY", raising=False)
    monkeypatch.setenv("IH_MASTER_KEY_FILE", str(mk))
    monkeypatch.setenv("IH_SESSION_SECRET", "s" * 32)
    s = Settings()
    assert s.master_key is not None and s.master_key.get_secret_value() == "m" * 40


def test_direct_env_wins_over_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mk = tmp_path / "mk"
    mk.write_text("f" * 40)
    monkeypatch.setenv("IH_MASTER_KEY", "d" * 40)
    monkeypatch.setenv("IH_MASTER_KEY_FILE", str(mk))
    monkeypatch.setenv("IH_SESSION_SECRET", "s" * 32)
    assert Settings().master_key_value() == "d" * 40


def test_session_secret_file_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ss = tmp_path / "ss"
    ss.write_text("z" * 40 + "\n")
    monkeypatch.delenv("IH_SESSION_SECRET", raising=False)
    monkeypatch.setenv("IH_SESSION_SECRET_FILE", str(ss))
    monkeypatch.setenv("IH_MASTER_KEY", "k" * 32)
    assert Settings().session_secret_value() == "z" * 40


def test_validation_error_hides_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "abcdefghij0123456789X"
    assert len(secret) == 21
    monkeypatch.setenv("IH_SESSION_SECRET", "s" * 32)
    with pytest.raises(ValidationError) as ei:
        Settings(master_key=secret)  # type: ignore[arg-type]
    assert secret not in str(ei.value)


def test_secret_file_missing_names_variable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("IH_MASTER_KEY", raising=False)
    monkeypatch.setenv("IH_MASTER_KEY_FILE", str(tmp_path / "nope"))
    monkeypatch.setenv("IH_SESSION_SECRET", "s" * 32)
    with pytest.raises(ValueError, match="IH_MASTER_KEY_FILE"):
        Settings()


def test_secret_file_unreadable_names_variable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("IH_MASTER_KEY", raising=False)
    monkeypatch.setenv("IH_MASTER_KEY_FILE", str(tmp_path))  # a directory
    monkeypatch.setenv("IH_SESSION_SECRET", "s" * 32)
    with pytest.raises(ValueError, match="IH_MASTER_KEY_FILE"):
        Settings()


@pytest.mark.parametrize("eol", ["\n", "\r\n"])
def test_secret_file_strips_line_ending(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, eol: str
) -> None:
    mk = tmp_path / "mk"
    mk.write_bytes(("m" * 40 + eol).encode())
    monkeypatch.delenv("IH_MASTER_KEY", raising=False)
    monkeypatch.setenv("IH_MASTER_KEY_FILE", str(mk))
    monkeypatch.setenv("IH_SESSION_SECRET", "s" * 32)
    assert Settings().master_key_value() == "m" * 40


def test_database_url_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    f = tmp_path / "dbu"
    f.write_bytes(b"postgresql://u:p@db/h\r\n")
    monkeypatch.delenv("IH_DATABASE_URL", raising=False)
    monkeypatch.setenv("IH_DATABASE_URL_FILE", str(f))
    monkeypatch.setenv("IH_MASTER_KEY", "k" * 32)
    monkeypatch.setenv("IH_SESSION_SECRET", "s" * 32)
    assert Settings().database_url == "postgresql://u:p@db/h"


def test_repr_hides_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IH_DATABASE_URL", "postgresql://u:topsecretpw@db/h")
    monkeypatch.setenv("IH_MASTER_KEY", "k" * 32)
    monkeypatch.setenv("IH_SESSION_SECRET", "s" * 32)
    assert "topsecretpw" not in repr(Settings()) + str(Settings())
