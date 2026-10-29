from typing import Any

import pytest

from app.core.extractors import (
    UnsupportedURL,
    list_extractors,
    validate_gdl_options,
    validate_url,
)


def test_validate_url_reddit() -> None:
    assert validate_url("https://www.reddit.com/r/pics/") == "reddit"


def test_validate_url_unsupported_raises() -> None:
    with pytest.raises(UnsupportedURL):
        validate_url("https://example.invalid/nothing")


def test_generic_prefix_rejected() -> None:
    with pytest.raises(UnsupportedURL):
        validate_url("generic:https://example.com/")


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/x.jpg",
        "http://[::1]/a.png",
        "http://10.0.0.5/a.jpg",
        "http://localhost/a.jpg",
        "http://foo.localhost/a.jpg",
        "http://169.254.169.254/a.jpg",
    ],
)
def test_private_hosts_rejected_by_default(url: str) -> None:
    with pytest.raises(UnsupportedURL, match="private host not allowed"):
        validate_url(url)
    assert validate_url(url, allow_private=True) == "directlink"


def test_non_http_scheme_rejected() -> None:
    with pytest.raises(UnsupportedURL):
        validate_url("ftp://example.com/a.jpg", allow_private=True)


def test_public_directlink_supported() -> None:
    assert validate_url("https://93.184.216.34/a.jpg") == "directlink"


def test_list_extractors_has_reddit() -> None:
    items = {e.category: e for e in list_extractors()}
    assert "reddit" in items
    assert "subreddit" in items["reddit"].subcategories
    assert [e.category for e in list_extractors()] == sorted(items)
    assert list_extractors() is list_extractors()


def test_allowlist_accepts_scalars() -> None:
    opts = {"sleep": [1, 2.5], "retries": 3, "include": "posts", "previews": True}
    assert validate_gdl_options(opts) == opts


@pytest.mark.parametrize(
    "key",
    [
        "postprocessors",
        "exec",
        "file-filter",
        "post-filter",
        "image-filter",
        "directory",
        "filename",
        "base-directory",
        "archive",
        "cookies",
    ],
)
def test_allowlist_rejects_postprocessors_exec_filters_directory(key: str) -> None:
    with pytest.raises(ValueError, match=key):
        validate_gdl_options({key: "x"})


def test_allowlist_rejects_nested_dict_value() -> None:
    with pytest.raises(ValueError, match="sleep"):
        validate_gdl_options({"sleep": {"a": 1}})
    with pytest.raises(ValueError, match="include"):
        validate_gdl_options({"include": [["a"]]})


_PRIVATE_BYPASS = [
    "http://2130706433/a.jpg",
    "http://0x7f.1/a.jpg",
    "http://0177.0.0.1/a.jpg",
    "http://127.1/a.jpg",
    "http://0/a.jpg",
    "http://100.64.0.1/a.jpg",
    "http://[::ffff:127.0.0.1]/a.jpg",
    "http://[2002:7f00:1::]/a.jpg",
    "http://localhost./a.jpg",
    "http://LOCALHOST/a.jpg",
]


@pytest.mark.parametrize("url", _PRIVATE_BYPASS)
def test_private_bypass_forms_rejected(url: str) -> None:
    with pytest.raises(UnsupportedURL, match="private host not allowed"):
        validate_url(url)
    assert validate_url(url, allow_private=True) == "directlink"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1\\@evil.com/a.jpg",
        "http://10.0.0.1\\@evil.com/a.jpg",
        "http://169.254.169.254\\@evil.com/a.jpg",
        "http://exa mple.com/a.jpg",
        "http://example.com/a\n.jpg",
        "http://exämple.com/a.jpg",
    ],
)
@pytest.mark.parametrize("allow_private", [False, True])
def test_malformed_chars_always_rejected(url: str, allow_private: bool) -> None:
    with pytest.raises(UnsupportedURL):
        validate_url(url, allow_private=allow_private)


def test_userinfo_host_is_real_host() -> None:
    assert validate_url("http://127.0.0.1@evil.com/a.jpg") == "directlink"


def test_list_extractors_is_tuple() -> None:
    assert isinstance(list_extractors(), tuple)


@pytest.mark.parametrize(
    "opts",
    [
        {"browser": "firefox"},
        {"ciphers": ["a", "b"]},
        {"headers": {"X": "y"}},
        {"reddit": {"comments": 500}},
        {"reddit": {"headers": {"X": "y"}}},
    ],
)
def test_blocklist_accepts(opts: dict[str, Any]) -> None:
    assert validate_gdl_options(opts) == opts


@pytest.mark.parametrize(
    "opts",
    [
        {"postprocessors": ["x"]},
        {"cookies": "x"},
        {"verify": False},
        {"proxy": "http://x"},
        {"image-filter": "x"},
        {"archive-format": "x"},
        {"reddit": {"cookies": "/etc/passwd"}},
        {"notasite": {"a": 1}},
        {"reddit": {"headers": {"a": {"b": 1}}}},
        {"reddit": {"comments": {"a": 1}}},
        {1: "x"},
    ],
)
def test_blocklist_rejects(opts: dict[Any, Any]) -> None:
    with pytest.raises(ValueError):
        validate_gdl_options(opts)


@pytest.mark.parametrize(
    "opts",
    [
        {"follow": "x"},
        {"browser": "\fE 1"},
        {"reddit": {"browser": "\fE 1"}},
        {"include": ["a", "\fE 1"]},
        {"headers": {"X": "\fE 1"}},
        {"user-agent": "browser"},
        {"user-agent": "@firefox"},
        {"reddit": {"user-agent": "@firefox"}},
        {"retries": -1},
        {"reddit": {"retries": -1}},
        {"reddit": 1},
    ],
)
def test_review_fixes_rejected(opts: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        validate_gdl_options(opts)


@pytest.mark.parametrize(
    ("raw", "want"),
    [
        ("reddit", "reddit"),
        ("  Reddit ", "reddit"),
        ("reddit.com", "reddit"),
        ("www.reddit.com", "reddit"),
        ("old.reddit.com", "reddit"),
        ("https://reddit.com", "reddit"),
        ("https://www.reddit.com/r/pics?x=1", "reddit"),
        ("imgur.com", "imgur"),
        ("apprise", "apprise"),
        ("not-a-known-site.example", "not-a-known-site.example"),
    ],
)
def test_normalize_site(raw: str, want: str) -> None:
    from app.core.extractors import normalize_site

    assert normalize_site(raw) == want
