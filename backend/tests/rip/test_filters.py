from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from app.db.models import BackfillMode
from app.rip.filters import FilterSpec, check, gdl_filter_options
from app.rip.media import MediaInfo
from app.rip.settings import RipSettings


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
    assert gdl_filter_options(s, BackfillMode.last_n, "10", False)["post-range"] == "1-10"
    assert "post-range" not in gdl_filter_options(s, BackfillMode.last_n, "10", True)
    both = gdl_filter_options(FilterSpec(max_items=5), BackfillMode.last_n, "10", False)
    assert both["post-range"] == "1-5"
    assert (
        gdl_filter_options(FilterSpec(max_items=5), BackfillMode.full, None, True)["post-range"]
        == "1-5"
    )


def test_gdl_options_since_and_date_from_takes_later() -> None:
    s = FilterSpec(date_from="2024-06-01")  # type: ignore[arg-type]
    o = gdl_filter_options(s, BackfillMode.since, "2024-01-01", False)
    assert o["date-min"] == "2024-06-01"
    o = gdl_filter_options(s, BackfillMode.since, "2024-09-01", False)
    assert o["date-min"] == "2024-09-01"
    o = gdl_filter_options(s, BackfillMode.since, "2024-09-01", True)
    assert o["date-min"] == "2024-06-01"


def test_gdl_options_sizes_and_date_to_inclusive() -> None:
    s = FilterSpec(min_bytes=10, max_bytes=99, date_to="2024-02-03")  # type: ignore[arg-type]
    o = gdl_filter_options(s, BackfillMode.full, None, False)
    assert o["filesize-min"] == 10
    assert o["filesize-max"] == 99
    assert o["date-max"] == "2024-02-03T23:59:59"


def test_incremental_sets_abort_skip() -> None:
    assert gdl_filter_options(FilterSpec(), BackfillMode.full, None, True)["skip"] == "abort:20"
    assert "skip" not in gdl_filter_options(FilterSpec(), BackfillMode.full, None, False)


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
