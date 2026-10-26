from loadtest.dedupe import run


def test_loadtest_smoke(tmp_path):
    r = run(20_000, tmp_path / "lt.db", lookups=500)
    assert {"url_seen_p99", "match_sha1_p99", "match_phash_p99"} <= r.keys()
    assert all(v > 0 for v in r.values())
