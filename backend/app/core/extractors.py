import ipaddress
from functools import cache
from typing import Any
from urllib.parse import urlsplit

from gallery_dl import extractor as gdl_extractor
from pydantic import BaseModel

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


def _is_private_host(host: str) -> bool:
    host = host.strip("[]").rstrip(".").lower()
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(host.split("%")[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def validate_url(url: str, *, allow_private: bool = False) -> str:
    """Return the gallery-dl category for a URL, or raise UnsupportedURL."""
    if url.lower().startswith("generic:"):
        raise UnsupportedURL("unsupported url")
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:
        raise UnsupportedURL("unsupported url") from None
    if parts.scheme not in ("http", "https") or not host:
        raise UnsupportedURL("unsupported url")
    if not allow_private and _is_private_host(host):
        raise UnsupportedURL("private host not allowed")
    ex = gdl_extractor.find(url)
    if ex is None:
        raise UnsupportedURL("unsupported url")
    return str(ex.category)


@cache
def list_extractors() -> list[ExtractorInfo]:
    subs: dict[str, set[str]] = {}
    examples: dict[str, str] = {}
    for cls in gdl_extractor._list_classes():
        cat = cls.category
        subs.setdefault(cat, set()).add(cls.subcategory)
        ex = getattr(cls, "example", None)
        if ex and cat not in examples:
            examples[cat] = ex
    return [
        ExtractorInfo(category=c, subcategories=sorted(s), example=examples.get(c))
        for c, s in sorted(subs.items())
    ]


def validate_gdl_options(opts: dict[str, Any]) -> dict[str, Any]:
    for key, val in opts.items():
        if key not in GDL_OPTION_ALLOWLIST:
            raise ValueError(f"gdl option not allowed: {key}")
        items = val if isinstance(val, list) else [val]
        if not all(isinstance(i, _SCALARS) for i in items):
            raise ValueError(f"gdl option must be a scalar or list of scalars: {key}")
    return opts
