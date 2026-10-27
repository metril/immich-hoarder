import os
import stat
from pathlib import Path

import pytest

from app.core.config import Settings
from app.core.secrets import load_or_create


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for v in ("IH_MASTER_KEY", "IH_MASTER_KEY_FILE", "IH_SESSION_SECRET", "IH_SESSION_SECRET_FILE"):
        monkeypatch.delenv(v, raising=False)


def test_creates_once_with_0600(tmp_path: Path) -> None:
    d = tmp_path / "secrets"
    first = load_or_create("master_key", d)
    assert len(first) >= 32
    assert load_or_create("master_key", d) == first
    assert stat.S_IMODE(os.stat(d / "master_key").st_mode) == 0o600
    assert [p.name for p in d.iterdir()] == ["master_key"]  # no temp leftovers


def test_env_overrides_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("IH_MASTER_KEY", "e" * 40)
    assert load_or_create("master_key", tmp_path) == "e" * 40
    assert not (tmp_path / "master_key").exists()


def test_file_env_overrides_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    f = tmp_path / "ext"
    f.write_text("f" * 40 + "\n")
    monkeypatch.setenv("IH_SESSION_SECRET_FILE", str(f))
    assert load_or_create("session_secret", tmp_path / "d") == "f" * 40


def test_settings_resolves_generated_and_override(tmp_path: Path) -> None:
    s = Settings(data_dir=tmp_path)
    assert s.master_key_value() == s.master_key_value()
    assert s.master_key_value() != s.session_secret_value()
    assert (tmp_path / "secrets" / "session_secret").exists()
    assert Settings(data_dir=tmp_path, master_key="k" * 32).master_key_value() == "k" * 32  # type: ignore[arg-type]
