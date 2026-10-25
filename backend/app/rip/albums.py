import re
import threading
import unicodedata
from datetime import date, datetime
from string import Formatter
from typing import Any

from app.immich.client import ImmichClient
from app.immich.errors import ImmichError, ImmichUnavailable

ALBUM_FIELDS = frozenset({"subreddit", "author", "user", "site", "category", "source", "date"})
MAX_ALBUM_LEN = 255

_WS = re.compile(r"\s+")


def _clean(s: str) -> str:
    kept = "".join(c for c in s if c.isspace() or unicodedata.category(c) not in ("Cc", "Cf", "Cs"))
    return _WS.sub(" ", kept).strip().strip("/").strip()


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
    if isinstance(v, bool) or not isinstance(v, str | int | float):
        return None
    s = _clean(str(v)) if field != "date" else str(v)
    return s or None


def render_album(template: str, meta: dict[str, Any], source_name: str) -> str:
    parts: list[str] = []
    try:
        for literal, field, spec, conv in Formatter().parse(template):
            parts.append(literal)
            if field is None:
                continue
            if spec or conv or field not in ALBUM_FIELDS:
                return _clean(source_name)[:MAX_ALBUM_LEN]
            val = _value(field, meta, source_name)
            if val is None:
                return _clean(source_name)[:MAX_ALBUM_LEN]
            parts.append(val)
    except ValueError:
        return _clean(source_name)[:MAX_ALBUM_LEN]
    out = _clean("".join(parts))[:MAX_ALBUM_LEN]
    return _clean(out) or _clean(source_name)[:MAX_ALBUM_LEN]


class AlbumResolver:
    def __init__(self, client: ImmichClient) -> None:
        self._client = client
        self._lock = threading.Lock()
        self._ids: dict[str, str] | None = None

    def resolve(self, name: str) -> str:
        with self._lock:
            if self._ids is None:
                ids: dict[str, str] = {}
                for a in self._client.list_albums():
                    ids.setdefault(a.name, a.id)
                self._ids = ids
            if name in self._ids:
                return self._ids[name]
            try:
                album = self._client.create_album(name)
            except (ImmichUnavailable, ImmichError):
                self._ids = None  # may have been created; re-list next time
                raise
            self._ids[name] = album.id
            return album.id
