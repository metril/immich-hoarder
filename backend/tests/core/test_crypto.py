import pytest

from app.core.config import get_settings
from app.core.crypto import SecretBox, SecretDecryptError, _box_for, get_secret_box


def test_roundtrip() -> None:
    box = SecretBox("master-key-0123456789abcdef-xyz")
    assert box.decrypt(box.encrypt(b"hunter2")) == b"hunter2"


def test_wrong_key_raises_SecretDecryptError() -> None:
    token = SecretBox("key-a").encrypt(b"hunter2")
    with pytest.raises(SecretDecryptError) as exc:
        SecretBox("key-b").decrypt(token)
    assert "hunter2" not in str(exc.value)
    assert exc.value.__suppress_context__ is True


def test_ciphertexts_differ() -> None:
    box = SecretBox("master-key-0123456789abcdef-xyz")
    assert box.encrypt(b"same") != box.encrypt(b"same")


def test_get_secret_box_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IH_MASTER_KEY", "k" * 32)
    get_settings.cache_clear()
    _box_for.cache_clear()
    try:
        assert get_secret_box() is get_secret_box()
    finally:
        get_settings.cache_clear()
        _box_for.cache_clear()
