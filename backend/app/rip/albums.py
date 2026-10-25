import re
import threading
from datetime import date, datetime
from string import Formatter
from typing import Any

from app.immich.client import ImmichClient
from app.immich.errors import ImmichUnavailable

ALBUM_FIELDS = frozenset({"subreddit", "author", "user", "site", "category", "source", "date"})
MAX_ALBUM_LEN = 255

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_WS = re.compile(r"\s+")


def _date(v: Any) -> str | None:
    if isinstance(v, datetime | date):
        return v.strftime("%Y-%m")
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v).strftime("%Y-%m")
        except ValueError:
            return None
    return None


def _value(field: str, meta: dict[str, Any], source_name: str) -> str | None:
    if field == "source":
        v: Any = source_name
    elif field in ("site", "category"):
        v = meta.get("category")
    elif field == "user":
        v = meta.get("user") or meta.get("author")
    elif field == "date":
        v = _date(meta.get("date"))
    else:
        v = meta.get(field)
    if v is None:
        return None
    s = _CONTROL.sub("", str(v))
    return s if s.strip() else None


def render_album(template: str, meta: dict[str, Any], source_name: str) -> str:
    parts: list[str] = []
    try:
        for literal, field, spec, conv in Formatter().parse(template):
            parts.append(literal)
            if field is None:
                continue
            if spec or conv or field not in ALBUM_FIELDS:
                return source_name
            val = _value(field, meta, source_name)
            if val is None:
                return source_name
            parts.append(val)
    except ValueError:
        return source_name
    out = _WS.sub(" ", _CONTROL.sub("", "".join(parts))).strip().strip("/").strip()
    return out[:MAX_ALBUM_LEN] or source_name


class AlbumResolver:
    def __init__(self, client: ImmichClient) -> None:
        self._client = client
        self._lock = threading.Lock()
        self._ids: dict[str, str] | None = None

    def resolve(self, name: str) -> str:
        with self._lock:
            if self._ids is None:
                self._ids = {}
                for a in self._client.list_albums():
                    self._ids.setdefault(a.name, a.id)
            if name in self._ids:
                return self._ids[name]
            try:
                album = self._client.create_album(name)
            except ImmichUnavailable:
                self._ids = None  # may have been created; re-list next time
                raise
            self._ids[name] = album.id
            return album.id
