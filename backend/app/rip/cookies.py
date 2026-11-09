"""Normalise cookie credentials (Netscape, JSON export, header string) to Netscape text."""

import json
from typing import Any

_ERR = "cookies must be Netscape cookies.txt or a JSON export"
_HEADER = "# Netscape HTTP Cookie File"


class CredentialError(ValueError):
    """A credential is unusable; the message is safe to show to the user."""


def _rows(text: str) -> list[list[str]]:
    out = []
    for ln in text.splitlines():
        parts = ln.strip().removeprefix("#HttpOnly_").split("\t")
        if len(parts) >= 7 and (not ln.lstrip().startswith("#") or ln.startswith("#HttpOnly_")):
            out.append(parts)
    return out


def _is_netscape(text: str) -> bool:
    if _rows(text):
        return True
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    return first.startswith("# Netscape") or first.startswith("# HTTP Cookie File")


def _clean(v: Any) -> str:
    s = str(v)
    if any(c in s for c in "\t\r\n"):
        raise CredentialError(_ERR)
    return s


def _from_json(data: Any) -> tuple[str, list[str]]:
    if isinstance(data, dict):
        data = data.get("cookies")
    if not isinstance(data, list) or not data:
        raise CredentialError(_ERR)
    rows = [_HEADER]
    names: list[str] = []
    for c in data:
        if not isinstance(c, dict) or not isinstance(c.get("name"), str):
            raise CredentialError(_ERR)
        domain = c.get("domain")
        if not isinstance(domain, str) or not domain:
            raise CredentialError(_ERR)
        exp = c.get("expirationDate", c.get("expires"))
        exp_i = int(exp) if isinstance(exp, int | float) and not isinstance(exp, bool) else 0
        name = _clean(c["name"])
        names.append(name)
        row = "\t".join(
            [
                _clean(domain),
                "TRUE" if domain.startswith(".") else "FALSE",
                _clean(c.get("path") or "/"),
                "TRUE" if c.get("secure") else "FALSE",
                str(max(exp_i, 0)),
                name,
                _clean(c.get("value", "")),
            ]
        )
        rows.append(("#HttpOnly_" if c.get("httpOnly") else "") + row)
    return "\n".join(rows) + "\n", names


def _from_header(text: str) -> tuple[str, list[str]]:
    text = text.strip()
    if text[:7].lower() == "cookie:":
        text = text[7:]
    rows = [_HEADER]
    names: list[str] = []
    for part in text.split(";"):
        name, sep, val = part.strip().partition("=")
        name, val = name.strip(), val.strip()
        if not (sep and name and val) or any(c in name + val for c in "\t\r\n"):
            raise CredentialError(_ERR)
        names.append(name)
        rows.append(f".reddit.com\tTRUE\t/\tTRUE\t0\t{name}\t{val}")
    if not names:
        raise CredentialError(_ERR)
    return "\n".join(rows) + "\n", names


def to_netscape(secret: str, site: str) -> str:
    """Netscape cookies.txt text for any supported input; raises CredentialError."""
    stripped = secret.strip()
    if _is_netscape(secret):
        text = secret
        names = [r[5] for r in _rows(secret)]
    elif stripped[:1] in "[{":
        try:
            data = json.loads(stripped)
        except ValueError:
            raise CredentialError(_ERR) from None
        text, names = _from_json(data)
    elif site == "reddit":
        text, names = _from_header(stripped)
    else:
        raise CredentialError(_ERR)
    if site == "reddit" and "reddit_session" not in names:
        raise CredentialError(
            "Reddit cookies must be from a logged-in session (missing reddit_session); "
            "export all reddit.com cookies"
        )
    return text


def _reddit_rows(text: str) -> list[list[str]]:
    return [r for r in _rows(text) if r[0].lstrip(".").removesuffix("reddit.com") in ("", "www.")]


def _expiry(row: list[str]) -> int:
    try:
        return max(int(float(row[4])), 0)
    except ValueError:
        return 0


def session_expiry(text: str) -> int | None:
    """Unix expiry of reddit_session in Netscape text (0 = none known); None if absent."""
    for r in _reddit_rows(text):
        if r[5] == "reddit_session":
            return _expiry(r)
    return None


def renewed_cookies(old_secret: str, new_text: str, now: float) -> tuple[str, int] | None:
    """reddit.com rows of a usable, changed cookie jar and its session expiry, else None."""
    rows = _reddit_rows(new_text)
    new_exp = session_expiry(new_text)
    if new_exp is None or (new_exp and new_exp < now):
        return None
    try:
        old_text = to_netscape(old_secret, "reddit")
    except CredentialError:
        return None
    old_exp = session_expiry(old_text) or 0
    if new_exp < old_exp:
        return None
    key = {(r[5], r[6], _expiry(r)) for r in rows}
    if key == {(r[5], r[6], _expiry(r)) for r in _reddit_rows(old_text)}:
        return None
    return _HEADER + "\n" + "".join("\t".join(r) + "\n" for r in rows), new_exp
