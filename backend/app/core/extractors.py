import ipaddress
import socket
from functools import cache
from typing import Any
from urllib.parse import urlsplit

import requests
from gallery_dl import extractor as gdl_extractor
from pydantic import BaseModel
from urllib3.util import parse_url

GDL_OPTION_ALLOWLIST = frozenset(
    {"sleep", "sleep-request", "retries", "timeout", "include", "recursion", "previews"}
)
_SCALARS = (str, int, float, bool)


class UnsupportedURL(ValueError):
    pass


class ExtractorInfo(BaseModel):
    category: str
    subcategories: list[str]
    example: str | None = None


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


def validate_gdl_options(opts: dict[str, Any]) -> dict[str, Any]:
    for key, val in opts.items():
        if key not in GDL_OPTION_ALLOWLIST:
            raise ValueError(f"gdl option not allowed: {key}")
        items = val if isinstance(val, list) else [val]
        if not all(isinstance(i, _SCALARS) for i in items):
            raise ValueError(f"gdl option must be a scalar or list of scalars: {key}")
    return opts
