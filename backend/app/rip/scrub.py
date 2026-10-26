"""Scrub credential secrets out of text that may be logged or returned to clients."""

import json
from collections.abc import Iterable
from typing import Any
from urllib.parse import quote, urlsplit

from app.db.models import CredentialKind
from app.rip.snapshot import CredentialSnapshot

_MIN_LEN = 4


def _collect(node: Any, out: set[str]) -> None:
    if isinstance(node, dict):
        for v in node.values():
            _collect(v, out)
    elif isinstance(node, list):
        for v in node:
            _collect(v, out)
    elif isinstance(node, str | int) and not isinstance(node, bool):
        out.add(str(node))


def secret_fragments(cred: CredentialSnapshot | None) -> frozenset[str]:
    if cred is None:
        return frozenset()
    secret = cred.secret.get_secret_value()
    out: set[str] = {secret}
    if cred.kind == CredentialKind.cookies:
        for line in secret.splitlines():
            parts = line.split("\t")
            if len(parts) >= 7:
                out.add(parts[6].strip())
    else:
        try:
            data: Any = json.loads(secret)
        except ValueError:
            data = None
        if isinstance(data, dict):
            _collect(data, out)
    return frozenset(f for f in out if len(f) >= _MIN_LEN)


def scrub(text: str, fragments: Iterable[str]) -> str:
    forms: set[str] = set()
    for f in fragments:
        if f:
            forms.add(f)
            forms.add(quote(f, safe=""))
    for f in sorted(forms, key=len, reverse=True):
        text = text.replace(f, "***")
    return text


def scrub_data(value: Any, fragments: Iterable[str]) -> Any:
    if isinstance(value, str):
        return scrub(value, fragments)
    if isinstance(value, dict):
        return {k: scrub_data(v, fragments) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [scrub_data(v, fragments) for v in value]
    return value


def safe_url(url: str) -> str:
    """scheme://host[:port]/path only: no userinfo, query or fragment."""
    try:
        u = urlsplit(url)
        host = u.hostname or ""
        if ":" in host:
            host = f"[{host}]"
        netloc = f"{host}:{u.port}" if u.port else host
    except ValueError:
        return ""
    return f"{u.scheme}://{netloc}{u.path}" if netloc else ""
