import ipaddress
import socket
from functools import cache
from typing import Any
from urllib.parse import urlsplit

import requests
from gallery_dl import extractor as gdl_extractor
from pydantic import BaseModel, Field
from urllib3.util import parse_url

GDL_OPTION_BLOCKLIST = frozenset(
    {
        # code execution
        "actions", "postprocessors", "postprocessor-options", "file-filter", "post-filter",
        "child-filter", "skip-filter", "image-filter", "chapter-filter", "keywords-eval", "exec",
        "follow",
        # file access
        "cookies", "cookies-update", "cookies-select", "verify", "truststore", "netrc",
        "tags-blacklist", "tags-whitelist", "base-directory", "directory", "filename",
        "archive", "archive-event", "archive-format", "archive-mode", "archive-prefix",
        "archive-pragma", "archive-reuse", "archive-table", "write-pages", "part-directory",
        # ssrf bypass
        "proxy", "proxy-env", "source-address",
        # app-owned
        "skip", "download", "path-restrict", "path-replace", "path-remove", "path-strip",
        "path-sub", "path-convert", "path-extended", "videos",
    }
)  # fmt: skip
_DICT_OPTIONS = frozenset({"headers", "keywords", "keywords-global", "extension-map"})
_SCALARS = (str, int, float, bool)


class UnsupportedURL(ValueError):
    pass


class ExtractorInfo(BaseModel):
    category: str = Field(description="Site (extractor category).", examples=["pixiv"])
    subcategories: list[str] = Field(
        description="Kinds of URL the extractor handles.", examples=[["user", "artwork"]]
    )
    example: str | None = Field(
        default=None, description="An example URL.", examples=["https://www.pixiv.net/en/users/123"]
    )


_HEXISH = frozenset("0123456789abcdefx.")


_SITE_LOCAL = ipaddress.IPv6Network("fec0::/10")


def _ip_private(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        elif ip.sixtofour:
            ip = ip.sixtofour
    if isinstance(ip, ipaddress.IPv6Address) and ip in _SITE_LOCAL:
        return True  # deprecated site-local (fec0::/10) is not flagged by is_global
    return not ip.is_global


def _is_private_host(host: str) -> bool:
    host = host.strip("[]").rstrip(".").lower()
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return _ip_private(ipaddress.ip_address(host.split("%")[0]))
    except ValueError:
        pass
    try:
        return _ip_private(ipaddress.IPv4Address(socket.inet_aton(host)))
    except OSError:
        pass
    # Numeric-looking hostnames that inet_aton rejects: treat as unsafe.
    return bool(host) and all(c in _HEXISH for c in host) and host[0].isdigit()


def _real_host(url: str) -> str | None:
    """Host as the downloader (requests/urllib3) will connect to it."""
    try:
        prepared = requests.Request("GET", url).prepare().url
        return parse_url(prepared).host if prepared else None
    except Exception:
        return None


def validate_url(url: str, *, allow_private: bool = False) -> str:
    """Return the gallery-dl category for a URL, or raise UnsupportedURL."""
    url = url.strip()
    if any(c == "\\" or c.isspace() or not 32 < ord(c) < 127 for c in url):
        raise UnsupportedURL("unsupported url")
    if url.lower().startswith("generic:"):
        raise UnsupportedURL("unsupported url")
    try:
        scheme = urlsplit(url).scheme
    except ValueError:
        raise UnsupportedURL("unsupported url") from None
    host = _real_host(url)
    if scheme not in ("http", "https") or not host:
        raise UnsupportedURL("unsupported url")
    if not allow_private and _is_private_host(host):
        raise UnsupportedURL("private host not allowed")
    ex = gdl_extractor.find(url)
    if ex is None:
        raise UnsupportedURL("unsupported url")
    return str(ex.category)


def validate_proxy(proxy: str, *, allow_private: bool = False) -> str:
    """Accept only http(s) proxies whose host passes the private-host rules."""
    proxy = proxy.strip()
    if any(c == "\\" or c.isspace() or not 32 < ord(c) < 127 for c in proxy):
        raise UnsupportedURL("invalid proxy")
    try:
        scheme = urlsplit(proxy).scheme
    except ValueError:
        raise UnsupportedURL("invalid proxy") from None
    host = _real_host(proxy)
    if scheme not in ("http", "https") or not host:
        raise UnsupportedURL("invalid proxy")
    if not allow_private and _is_private_host(host):
        raise UnsupportedURL("private proxy host not allowed")
    return proxy


@cache
def list_extractors() -> tuple[ExtractorInfo, ...]:
    subs: dict[str, set[str]] = {}
    examples: dict[str, str] = {}
    for cls in gdl_extractor._list_classes():
        cat = cls.category
        subs.setdefault(cat, set()).add(cls.subcategory)
        ex = getattr(cls, "example", None)
        if ex and cat not in examples:
            examples[cat] = ex
    return tuple(
        ExtractorInfo(category=c, subcategories=sorted(s), example=examples.get(c))
        for c, s in sorted(subs.items())
    )


@cache
def _categories() -> frozenset[str]:
    return frozenset(e.category for e in list_extractors())


def _blocked(key: str) -> bool:
    return (
        key in GDL_OPTION_BLOCKLIST
        or key.endswith("-filter")
        or key.startswith(("archive", "path-", "cookies"))
    )


def bad_user_agent(val: Any) -> bool:
    """`browser` / `@...` make gallery-dl spawn a process to look up a user agent."""
    return isinstance(val, str) and (val == "browser" or val.startswith("@"))


def _check_option(key: Any, val: Any) -> None:
    if not isinstance(key, str) or _blocked(key):
        raise ValueError(f"gdl option not allowed: {key}")
    if isinstance(val, dict):
        if key not in _DICT_OPTIONS or not all(
            isinstance(k, str) and isinstance(v, _SCALARS) for k, v in val.items()
        ):
            raise ValueError(f"gdl option must be a scalar or list of scalars: {key}")
        items = list(val.values())
    else:
        items = val if isinstance(val, list) else [val]
        if not all(isinstance(i, _SCALARS) for i in items):
            raise ValueError(f"gdl option must be a scalar or list of scalars: {key}")
    # "\f" prefixes make gallery-dl evaluate a format string as Python
    if any(isinstance(i, str) and i.startswith("\f") for i in items):
        raise ValueError(f"gdl option value not allowed: {key}")
    if key == "user-agent" and any(bad_user_agent(i) for i in items):
        raise ValueError(f"gdl option value not allowed: {key}")
    if key == "retries" and any(
        isinstance(i, int | float) and not isinstance(i, bool) and i < 0 for i in items
    ):
        raise ValueError(f"gdl option value not allowed: {key}")


def normalize_site(value: str) -> str:
    """Map a credential's site to a gallery-dl extractor name.

    Accepts the bare name ("reddit"), a host ("reddit.com", "www.reddit.com") or a URL
    ("https://reddit.com/r/pics"). Unknown values are only lowercased and trimmed.
    """
    s = value.strip().lower()
    for prefix in ("https://", "http://"):
        s = s.removeprefix(prefix)
    s = s.split("/", 1)[0].split("?", 1)[0].removeprefix("www.").removeprefix("old.")
    if not s or s in _categories():
        return s
    head = s.split(".", 1)[0]
    return head if head in _categories() else s


def validate_gdl_options(opts: dict[str, Any]) -> dict[str, Any]:
    for key, val in opts.items():
        if isinstance(key, str) and key in _categories() and not isinstance(val, dict):
            raise ValueError(f"per-site options must be an object: {key}")
        if isinstance(val, dict) and isinstance(key, str) and key in _categories():
            for ik, iv in val.items():
                _check_option(ik, iv)
        elif isinstance(val, dict) and not (isinstance(key, str) and key in _DICT_OPTIONS):
            if isinstance(key, str) and not _blocked(key):
                raise ValueError(f"unknown extractor for per-site options: {key}")
            raise ValueError(f"gdl option not allowed: {key}")
        else:
            _check_option(key, val)
    return opts
