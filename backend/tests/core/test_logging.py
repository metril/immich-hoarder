import json
import logging

import pytest

from app.core.logging import TRACE, JsonFormatter, configure_logging


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
