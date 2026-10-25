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
