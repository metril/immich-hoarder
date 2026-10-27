"""Local admin account: scrypt password hashing and failed-login backoff."""

import base64
import hashlib
import hmac
import os
import time

_N, _R, _P = 2**14, 8, 1
_DUMMY = "scrypt$16384$8$1$AAAAAAAAAAAAAAAAAAAAAA==$" + base64.b64encode(bytes(32)).decode()
MIN_PASSWORD_LENGTH = 8


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        password.encode(), salt=salt, n=n, r=r, p=p, maxmem=64 * 1024**2, dklen=32
    )


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = _derive(password, salt, _N, _R, _P)
    b64 = base64.b64encode
    return f"scrypt${_N}${_R}${_P}${b64(salt).decode()}${b64(dk).decode()}"


def verify_password(password: str, stored: str | None) -> bool:
    """Constant-time check; a missing/garbled hash still costs one scrypt run."""
    try:
        algo, n, r, p, salt, dk = (stored or _DUMMY).split("$")
        if algo != "scrypt":
            raise ValueError
        expect = base64.b64decode(dk)
        got = _derive(password, base64.b64decode(salt), int(n), int(r), int(p))
    except (ValueError, TypeError):
        got, expect = _derive(password, bytes(16), _N, _R, _P), b"x"
    return hmac.compare_digest(got, expect) and stored is not None


class LoginLimiter:
    """In-memory exponential backoff per key (e.g. client address): 5 free failures."""

    FREE = 5
    MAX_DELAY = 300.0

    def __init__(self) -> None:
        self._fails: dict[str, tuple[int, float]] = {}

    def retry_after(self, key: str) -> int:
        n, last = self._fails.get(key, (0, 0.0))
        if n < self.FREE:
            return 0
        wait = min(2.0 ** (n - self.FREE), self.MAX_DELAY) * 5
        return max(0, int(min(wait, self.MAX_DELAY) - (time.monotonic() - last)) + 1)

    def failed(self, key: str) -> None:
        n, _ = self._fails.get(key, (0, 0.0))
        if len(self._fails) > 10_000:
            self._fails.clear()  # bound memory under address-spraying
        self._fails[key] = (n + 1, time.monotonic())

    def succeeded(self, key: str) -> None:
        self._fails.pop(key, None)
