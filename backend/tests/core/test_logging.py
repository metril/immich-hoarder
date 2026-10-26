import json
import logging
import time

import pytest

from app.core.logging import TRACE, JsonFormatter, configure_logging, redact


def _fmt(**extra: object) -> dict[str, object]:
    rec = logging.LogRecord("app.x", logging.INFO, "f.py", 1, "hello %s", ("w",), None)
    rec.__dict__.update(extra)
    out: dict[str, object] = json.loads(JsonFormatter().format(rec))
    return out


def test_json_formatter_fields() -> None:
    d = _fmt(job_id=7)
    assert d["level"] == "info" and d["logger"] == "app.x" and d["msg"] == "hello w"
    assert d["job_id"] == 7 and "ts" in d


@pytest.mark.parametrize(
    "name",
    ["password", "api_token", "client_secret", "api_key", "Authorization", "cookie", "PASSWD"],
)
def test_sensitive_extra_keys_are_masked(name: str) -> None:
    assert _fmt(**{name: "hunter2"})[name] == "***"


def test_non_sensitive_extra_keys_kept() -> None:
    assert _fmt(source_id=3)["source_id"] == 3


def test_trace_level_configurable() -> None:
    configure_logging("trace")
    try:
        assert TRACE == 5
        assert logging.getLevelName(TRACE) == "TRACE"
        assert logging.getLogger().level == TRACE
    finally:
        configure_logging("info")


def test_redacts_secret_extras() -> None:
    extras = {
        "api_key": "x",
        "password": "y",
        "Authorization": "Bearer z",
        "master_key": "k",
        "token": "t",
        "cookie": "c",
        "db_credential": "d",
    }
    d = _fmt(**extras)
    assert all(d[k] == "***" for k in extras)


def test_redacts_url_credentials() -> None:
    rec = logging.LogRecord(
        "a", logging.INFO, "f", 1, "fetch %s", ("https://u:pw@h/x?token=abc&a=1",), None
    )
    out = json.loads(JsonFormatter().format(rec))
    assert out["msg"] == "fetch https://***@h/x?token=***&a=1"


def test_redacts_nested() -> None:
    src = {"a": [{"password": "p", "n": 1}], "b": ("https://u:p@h/",)}
    out = redact(src)
    assert out == {"a": [{"password": "***", "n": 1}], "b": ["https://***@h/"]}
    assert src["a"][0]["password"] == "p"  # type: ignore[index]


def test_non_secret_untouched() -> None:
    d = _fmt(job_id=5, url="https://h/a.jpg")
    assert d["job_id"] == 5 and d["url"] == "https://h/a.jpg"


def test_redact_is_linear_on_long_input() -> None:
    for payload in ("a" * 65536, "x://" + "a" * 65536, "a" * 30 + "://" * 20000):
        t = time.perf_counter()
        redact(payload)
        assert time.perf_counter() - t < 0.2


def test_long_string_is_truncated() -> None:
    out = redact("a" * 70000)
    assert isinstance(out, str) and len(out) < 70000


@pytest.mark.parametrize(
    "text",
    [
        "Authorization: Bearer abc.def",
        "X-API-Key: ih_abcd1234_" + "A" * 32,
        "key ih_abcd1234_" + "B" * 32 + " used",
    ],
)
def test_redacts_free_text_keys(text: str) -> None:
    out = str(redact(text))
    assert "abc.def" not in out and "A" * 32 not in out and "B" * 32 not in out
    assert "***" in out


def test_exc_redacts_url_credentials() -> None:
    try:
        raise RuntimeError("connect https://u:p@h/x failed")
    except RuntimeError:
        import sys

        rec = logging.LogRecord("a", logging.ERROR, "f", 1, "boom", None, sys.exc_info())
    out = json.loads(JsonFormatter().format(rec))
    assert "u:p@" not in out["exc"] and "https://***@h/x" in out["exc"]
