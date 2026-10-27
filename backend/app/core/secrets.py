"""Auto-generated instance secrets (master key, session secret).

Resolution order: IH_<NAME> env, IH_<NAME>_FILE, then <dir>/<name>, created on first use.
"""

import os
import secrets
import tempfile
from pathlib import Path

_ENV_PREFIX = "IH_"


def load_or_create(name: str, directory: Path) -> str:
    var = f"{_ENV_PREFIX}{name.upper()}"
    if value := os.environ.get(var):
        return value
    if path := os.environ.get(f"{var}_FILE"):
        try:
            return Path(path).read_text().rstrip("\r\n")
        except OSError as e:
            raise ValueError(f"{var}_FILE: cannot read {path}: {e.strerror}") from None
    target = directory / name
    try:
        return target.read_text().rstrip("\r\n")
    except FileNotFoundError:
        pass
    directory.mkdir(parents=True, exist_ok=True)
    value = secrets.token_urlsafe(48)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=f".{name}.")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(value)  # mkstemp creates the file 0600
        try:
            os.link(tmp, target)  # atomic create-if-absent; loses cleanly to a concurrent writer
        except FileExistsError:
            return target.read_text().rstrip("\r\n")
    finally:
        os.unlink(tmp)
    return value
