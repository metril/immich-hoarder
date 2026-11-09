import time

from app.rip.cookies import renewed_cookies, session_expiry

NOW = time.time()
FUT = int(NOW) + 10_000
FUT2 = FUT + 5_000


def jar(exp: int, value: str = "v1", extra: str = "") -> str:
    return (
        "# Netscape HTTP Cookie File\n"
        f".reddit.com\tTRUE\t/\tTRUE\t{exp}\treddit_session\t{value}\n" + extra
    )


def test_session_expiry() -> None:
    assert session_expiry(jar(FUT)) == FUT
    assert session_expiry(jar(0)) == 0
    assert session_expiry(".reddit.com\tTRUE\t/\tTRUE\t0\tloid\tx\n") is None


def test_renewed_returns_reddit_rows_only() -> None:
    foreign = ".other.com\tTRUE\t/\tTRUE\t0\ttrack\tz\n"
    res = renewed_cookies(jar(FUT), jar(FUT2, "v2", foreign), NOW)
    assert res is not None
    text, exp = res
    assert exp == FUT2 and "v2" in text and "other.com" not in text


def test_unchanged_is_none() -> None:
    assert renewed_cookies(jar(FUT), jar(FUT), NOW) is None


def test_missing_session_is_none() -> None:
    assert renewed_cookies(jar(FUT), ".reddit.com\tTRUE\t/\tTRUE\t0\tloid\tx\n", NOW) is None


def test_expired_session_is_none() -> None:
    assert renewed_cookies(jar(FUT), jar(int(NOW) - 5, "v2"), NOW) is None


def test_earlier_expiry_is_none() -> None:
    assert renewed_cookies(jar(FUT2), jar(FUT, "v2"), NOW) is None


def test_session_only_expiry() -> None:
    res = renewed_cookies(jar(0), jar(0, "v2"), NOW)
    assert res is not None and res[1] == 0
