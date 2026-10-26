"""Scrub credential secrets out of text that may be logged or returned to clients."""

import json
from collections.abc import Iterable
from typing import Any
from urllib.parse import quote

from app.db.models import CredentialKind
from app.rip.snapshot import CredentialSnapshot

_MIN_LEN = 4


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
            for v in data.values():
                if isinstance(v, bool):
                    continue
                if isinstance(v, str | int):
                    out.add(str(v))
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
