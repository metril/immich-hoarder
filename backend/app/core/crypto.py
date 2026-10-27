import base64
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import get_settings

_INFO = b"immich-hoarder/v1"


class SecretDecryptError(Exception):
    pass


class SecretBox:
    def __init__(self, master_key: str) -> None:
        derived = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_INFO).derive(
            master_key.encode()
        )
        self._fernet = MultiFernet([Fernet(base64.urlsafe_b64encode(derived))])

    def encrypt(self, plain: bytes) -> bytes:
        token: bytes = self._fernet.encrypt(plain)
        return token

    def decrypt(self, token: bytes) -> bytes:
        try:
            plain: bytes = self._fernet.decrypt(token)
            return plain
        except InvalidToken:
            raise SecretDecryptError("unable to decrypt secret") from None


@lru_cache
def _box_for(master_key: str) -> SecretBox:
    return SecretBox(master_key)


def get_secret_box() -> SecretBox:
    return _box_for(get_settings().master_key_value())
