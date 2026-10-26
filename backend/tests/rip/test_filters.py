import logging
from datetime import UTC, date, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from app.db.models import BackfillMode
from app.rip.filters import FilterSpec, check, gdl_filter_options
from app.rip.media import MediaInfo
from app.rip.settings import RipSettings, load_rip_settings


def _info(**kw: Any) -> MediaInfo:
    base: dict[str, Any] = {
        "format": "JPEG",
        "width": 1000,
        "height": 1000,
        "animated": False,
        "size": 5000,
        "sha1": b"x",
        "phash": 0,
    }
    return MediaInfo(**{**base, **kw})


def test_filterspec_rejects_unknown_key() -> None:
    with pytest.raises(ValidationError):
        FilterSpec.model_validate({"bogus": 1})


def test_phash_distance_range() -> None:
    assert FilterSpec(phash_distance=3).phash_distance == 3
    with pytest.raises(ValidationError):
        FilterSpec(phash_distance=4)


def test_gdl_options_last_n_first_run_only() -> None:
    s = FilterSpec()
    assert (
        gdl_filter_options(s, BackfillMode.last_n, "10", False)["extractor"]["post-range"] == "1-10"
    )
    assert "post-range" not in gdl_filter_options(s, BackfillMode.last_n, "10", True)["extractor"]
    both = gdl_filter_options(FilterSpec(max_items=5), BackfillMode.last_n, "10", False)
    assert both["extractor"]["post-range"] == "1-5"
    assert (
        gdl_filter_options(FilterSpec(max_items=5), BackfillMode.full, None, True)["extractor"][
            "post-range"
        ]
        == "1-5"
    )


def test_gdl_options_since_and_date_from_takes_later() -> None:
    s = FilterSpec(date_from="2024-06-01")  # type: ignore[arg-type]
    o = gdl_filter_options(s, BackfillMode.since, "2024-01-01", False)
    assert o["extractor"]["date-min"] == "2024-06-01"
    o = gdl_filter_options(s, BackfillMode.since, "2024-09-01", False)
    assert o["extractor"]["date-min"] == "2024-09-01"
    o = gdl_filter_options(s, BackfillMode.since, "2024-09-01", True)
    assert o["extractor"]["date-min"] == "2024-06-01"


def test_gdl_options_sizes_and_date_to_inclusive() -> None:
    s = FilterSpec(min_bytes=10, max_bytes=99, date_to="2024-02-03")  # type: ignore[arg-type]
    o = gdl_filter_options(s, BackfillMode.full, None, False)
    assert o["downloader"]["filesize-min"] == 10
    assert o["downloader"]["filesize-max"] == 99
    assert o["extractor"]["date-max"] == "2024-02-03T23:59:59"


def test_incremental_sets_abort_skip() -> None:
    assert (
        gdl_filter_options(FilterSpec(), BackfillMode.full, None, True)["extractor"]["skip"]
        == "abort:20"
    )
    assert (
        "skip" not in gdl_filter_options(FilterSpec(), BackfillMode.full, None, False)["extractor"]
    )


@pytest.mark.parametrize(
    ("info", "spec", "meta", "animated", "reason"),
    [
        (_info(animated=True), {}, {}, False, "animated"),
        (_info(width=10), {"min_width": 100}, {}, True, "too_small"),
        (_info(height=10), {"min_height": 100}, {}, True, "too_small"),
        (_info(size=900), {"max_bytes": 100}, {}, True, "too_large_bytes"),
        (_info(size=5), {"min_bytes": 100}, {}, True, "too_small_bytes"),
        (_info(width=3000, height=1000), {"aspect_max": 2.0}, {}, True, "aspect"),
        (_info(width=1000, height=3000), {"aspect_min": 0.5}, {}, True, "aspect"),
        (_info(), {"title_exclude": "NSFW"}, {"title": "a nsfw pic"}, True, "title_excluded"),
        (_info(), {"title_include": "cat"}, {"title": "dog"}, True, "title_not_included"),
        (_info(), {"title_include": "cat"}, {"filename": "dog.jpg"}, True, "title_not_included"),
        (
            _info(),
            {"date_from": "2024-01-01"},
            {"date": datetime(2023, 5, 1, tzinfo=UTC)},
            True,
            "date_out_of_range",
        ),
        (
            _info(),
            {"date_to": "2024-01-01"},
            {"date": datetime(2024, 1, 2, tzinfo=UTC)},
            True,
            "date_out_of_range",
        ),
        (
            _info(),
            {"date_to": "2024-01-01", "title_include": "CAT"},
            {"date": datetime(2024, 1, 1, 23, tzinfo=UTC), "title": "a cat"},
            True,
            None,
        ),
    ],
)
def test_check_reasons(
    info: MediaInfo, spec: dict[str, Any], meta: dict[str, Any], animated: bool, reason: str | None
) -> None:
    assert check(info, meta, FilterSpec.model_validate(spec), animated) == reason


def test_missing_date_passes() -> None:
    spec = FilterSpec(date_from="2024-01-01")  # type: ignore[arg-type]
    assert check(_info(), {}, spec, True) is None
    assert check(_info(), {"date": None}, spec, True) is None


def test_rip_settings_defaults_and_bounds() -> None:
    r = RipSettings()
    assert r.upload_concurrency == 4
    assert r.allow_private_hosts is False
    with pytest.raises(ValidationError):
        RipSettings(upload_concurrency=17)


def test_since_filters_older_post() -> None:
    meta = {"date": datetime(2024, 1, 1, tzinfo=UTC)}
    spec = FilterSpec()
    assert check(_info(), meta, spec, True, since=date(2024, 6, 1)) == "date_out_of_range"
    assert check(_info(), meta, spec, True, since=date(2024, 1, 1)) is None
    assert check(_info(), meta, spec, True) is None
    assert check(_info(), {}, spec, True, since=date(2024, 6, 1)) is None


def test_title_truncated_before_regex() -> None:
    spec = FilterSpec(title_exclude="needle")
    assert check(_info(), {"title": "a" * 1000 + "needle"}, spec, True) is None
    assert check(_info(), {"title": "a" * 990 + "needle"}, spec, True) == "title_excluded"


@pytest.mark.parametrize(
    "bad",
    [
        {"min_bytes": 10, "max_bytes": 5},
        {"aspect_min": 2.0, "aspect_max": 1.0},
        {"date_from": "2024-02-01", "date_to": "2024-01-01"},
        {"min_width": -1},
        {"min_bytes": -1},
        {"aspect_min": -0.5},
    ],
)
def test_filterspec_rejects_inconsistent_or_negative(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        FilterSpec.model_validate(bad)


def test_load_rip_settings_invalid_row_defaults_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from unittest.mock import AsyncMock, MagicMock

    session = MagicMock()
    session.get = AsyncMock(return_value=MagicMock(value={"upload_concurrency": 99}))
    import asyncio

    with caplog.at_level(logging.WARNING):
        r = asyncio.run(load_rip_settings(session))
    assert r == RipSettings()
    assert any(rec.levelno == logging.WARNING for rec in caplog.records)


def test_rip_settings_proxy_validated() -> None:
    assert RipSettings(proxy="http://10.0.0.5:3128").proxy == "http://10.0.0.5:3128"
    with pytest.raises(ValidationError):
        RipSettings(proxy="socks5://h:1")
    with pytest.raises(ValidationError):
        RipSettings(proxy="not a proxy")
