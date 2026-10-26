import json
import logging
from typing import Any
from urllib.parse import quote

import pytest
from pydantic import SecretStr

from app.db.models import CredentialKind
from app.rip.gdl import capture_logs
from app.rip.preview import PreviewError, _child, _summary, run_in_subprocess
from app.rip.scrub import scrub, secret_fragments
from app.rip.snapshot import CredentialSnapshot


def _cred(kind: CredentialKind, secret: str) -> CredentialSnapshot:
    return CredentialSnapshot(site="x", kind=kind, secret=SecretStr(secret))


TOKEN = _cred(
    CredentialKind.token, json.dumps({"api_key": "k3y/Secret+1", "user_id": 12345, "n": "ab"})
)


def test_fragments_json_values_and_short_skipped() -> None:
    f = secret_fragments(TOKEN)
    assert {"k3y/Secret+1", "12345"} <= f
    assert "ab" not in f
    assert secret_fragments(None) == frozenset()
    assert secret_fragments(_cred(CredentialKind.token, "abc")) == frozenset()


def test_fragments_cookie_values() -> None:
    row = ".x.com\tTRUE\t/\tTRUE\t0\t"
    txt = f"# Netscape HTTP Cookie File\n{row}sid\tcookieVal123\n{row}b\tzz\n"
    f = secret_fragments(_cred(CredentialKind.cookies, txt))
    assert "cookieVal123" in f
    assert "zz" not in f


def test_scrub_longest_first_and_urlencoded() -> None:
    f = frozenset({"k3y/Secret+1", "k3y"})
    out = scrub(f"a {quote('k3y/Secret+1', safe='')} b k3y/Secret+1 c", f)
    assert out == "a *** b *** c"
    assert "k3y" not in out


def test_capture_logs_scrubs_msg_and_data() -> None:
    events: list[dict[str, Any]] = []
    f = secret_fragments(TOKEN)
    lg = logging.getLogger("gelbooru")
    with capture_logs(events.append, "error", categories=["gelbooru"], fragments=f):
        lg.error(
            "HttpError: 401 for url: https://x/index.php?api_key=%s&user_id=12345",
            quote("k3y/Secret+1", safe=""),
        )
    assert events
    assert "k3y" not in json.dumps(events)
    assert "12345" not in json.dumps(events)


def test_preview_summary_scrubs_json_credential_value() -> None:
    msg = _summary(["bad url ?api_key=k3y/Secret+1"], 1, TOKEN)
    assert "k3y" not in msg and "***" in msg


def _boom(*_a: Any) -> None:
    raise RuntimeError("fail ?api_key=k3y/Secret+1")


def test_subprocess_error_scrubbed() -> None:
    with pytest.raises(PreviewError) as ei:
        run_in_subprocess(_boom, timeout=30, fragments=secret_fragments(TOKEN))
    assert "k3y" not in str(ei.value)


def test_child_signature_accepts_fragments() -> None:
    assert callable(_child)


def test_fragments_nested_json() -> None:
    sec = json.dumps({"a": {"b": ["deepSecret1", {"c": 987654}]}, "ok": True})
    f = secret_fragments(_cred(CredentialKind.oauth, sec))
    assert {"deepSecret1", "987654"} <= f
    assert "True" not in f
