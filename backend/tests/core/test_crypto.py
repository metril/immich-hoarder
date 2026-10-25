import pytest

from app.core.crypto import SecretBox, SecretDecryptError


def test_roundtrip() -> None:
    box = SecretBox("master-key")
    assert box.decrypt(box.encrypt(b"hunter2")) == b"hunter2"


def test_wrong_key_raises_SecretDecryptError() -> None:
    token = SecretBox("key-a").encrypt(b"hunter2")
    with pytest.raises(SecretDecryptError) as exc:
        SecretBox("key-b").decrypt(token)
    assert "hunter2" not in str(exc.value)
    assert exc.value.__cause__ is None


def test_ciphertexts_differ() -> None:
    box = SecretBox("master-key")
    assert box.encrypt(b"same") != box.encrypt(b"same")
