import logging
import re
import sys
from datetime import UTC, datetime

import orjson

TRACE = 5
logging.addLevelName(TRACE, "TRACE")

_LEVELS = {
    "error": logging.ERROR,
    "warn": logging.WARNING,
    "info": logging.INFO,
    "debug": logging.DEBUG,
    "trace": TRACE,
}

_SENSITIVE = re.compile(r"(?i)pass|token|secret|key|authorization|cookie|credential")
_MASK = "***"
_URL_USERINFO = re.compile(r"\b([a-zA-Z][\w+.-]{0,31}://)[^/@\s]{1,256}@")
_FREE_TEXT = re.compile(r"(?i)(bearer\s+|x-api-key:\s*)\S{1,512}")
_API_KEY = re.compile(r"\bih_[A-Za-z0-9]{8}_[A-Za-z0-9]{32}\b")
_QUERY_PARAM = re.compile(r"(?i)([?&])([^=&#\s]*)=([^&#\s]*)")
_MAX_SCAN = 64 * 1024


def _mask_query(m: re.Match[str]) -> str:
    return f"{m[1]}{m[2]}={_MASK}" if _SENSITIVE.search(m[2]) else m[0]


def redact(value: object) -> object:
    """Return a copy of ``value`` with secrets masked; the input is never mutated."""
    if isinstance(value, str):
        suffix = ""
        if len(value) > _MAX_SCAN:
            value, suffix = value[:_MAX_SCAN], "...[truncated]"
        value = _URL_USERINFO.sub(rf"\1{_MASK}@", value)
        value = _FREE_TEXT.sub(rf"\1{_MASK}", value)
        value = _API_KEY.sub(_MASK, value)
        return _QUERY_PARAM.sub(_mask_query, value) + suffix
    if isinstance(value, dict):
        return {
            k: _MASK if isinstance(k, str) and _SENSITIVE.search(k) else redact(v)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return value


_STD = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": redact(record.getMessage()),
        }
        for k, v in record.__dict__.items():
            if k not in _STD:
                data[k] = _MASK if _SENSITIVE.search(k) else redact(v)
        if record.exc_info:
            data["exc"] = redact(self.formatException(record.exc_info))
        return orjson.dumps(data, default=str).decode()


def configure_logging(level: str = "info") -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(_LEVELS[level])
