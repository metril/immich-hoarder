import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session
from tests.pgsupport import BACKENDS

from app.db.engine import make_sync_engine
from app.db.models import Base, ImmichTarget, Source, User
from app.rip.dedupe import DedupeStore, url_key
from app.rip.media import to_signed64

ASSET = str(uuid.uuid4())
PH = 0x0123_4567_89AB_CDEF


@pytest.fixture(params=BACKENDS)
def engine(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Engine]:
    if request.param == "pg":
        url = request.getfixturevalue("pg_url")
    else:
        url = f"sqlite+aiosqlite:///{tmp_path / 'd.db'}"
    eng = make_sync_engine(url)
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        u = User(sub="u1")
        s.add(u)
        s.flush()
        ts = [
            ImmichTarget(owner_id=u.id, name=f"t{i}", url="http://i", api_key_enc=b"x")
            for i in range(2)
        ]
        s.add_all(ts)
        s.flush()
        s.add(Source(owner_id=u.id, name="s", url="http://s", extractor="x", target_id=ts[0].id))
        s.commit()
    yield eng
    eng.dispose()


def _rec(
    store: DedupeStore,
    key: bytes,
    *,
    target: int = 1,
    sha1: bytes | None = None,
    phash: int | None = None,
    asset: str | None = ASSET,
) -> None:
    store.record(
        target_id=target,
        source_id=1,
        key=key,
        sha1=sha1,
        phash=phash,
        immich_asset_id=asset,
    )


def test_url_key_is_16_bytes() -> None:
    assert len(url_key("c", "k")) == 16
    assert url_key("c", "k") != url_key("c", "j")


def test_url_seen_after_record(engine: Engine) -> None:
    store = DedupeStore(engine)
    k = url_key("twitter", "1")
    assert not store.url_seen(1, k)
    _rec(store, k)
    assert store.url_seen(1, k)


def test_match_sha1_scoped_to_target(engine: Engine) -> None:
    store = DedupeStore(engine)
    sha = b"\x01" * 20
    _rec(store, url_key("c", "1"), sha1=sha)
    ref = store.match_sha1(1, sha)
    assert ref is not None and ref.immich_asset_id == ASSET
    assert store.match_sha1(2, sha) is None


def _flip(value: int, bits: list[int]) -> int:
    for b in bits:
        value ^= 1 << b
    return to_signed64(value)


def test_phash_distance_3_found_4_not(engine: Engine) -> None:
    store = DedupeStore(engine)
    _rec(store, url_key("c", "1"), phash=to_signed64(PH))
    # one flip in each of 3 different chunks: no chunk matches exactly except ph? (one)
    three = _flip(PH, [0, 20, 40])
    assert store.match_phash(1, three, 3) is not None
    four = _flip(PH, [0, 20, 40, 5])
    assert store.match_phash(1, four, 3) is None
    assert store.match_phash(2, three, 3) is None


def test_phash_picks_closest(engine: Engine) -> None:
    store = DedupeStore(engine)
    other = str(uuid.uuid4())
    _rec(store, url_key("c", "1"), phash=_flip(PH, [1, 2, 3]), asset=other)
    _rec(store, url_key("c", "2"), phash=_flip(PH, [1]))
    ref = store.match_phash(1, to_signed64(PH), 3)
    assert ref is not None and ref.immich_asset_id == ASSET


def test_phash_ignores_null_asset(engine: Engine) -> None:
    store = DedupeStore(engine)
    _rec(store, url_key("c", "1"), phash=to_signed64(PH), asset=None)
    assert store.match_phash(1, to_signed64(PH), 0) is None


def test_phash_disabled_when_none(engine: Engine) -> None:
    store = DedupeStore(engine)
    _rec(store, url_key("c", "1"), phash=None)
    _rec(store, url_key("c", "2"), phash=to_signed64(PH))
    ref = store.match_phash(1, to_signed64(PH), 0)
    assert ref is not None and ref.immich_asset_id == ASSET
    assert store.match_phash(1, _flip(PH, [0]), 0) is None


def test_record_idempotent(engine: Engine) -> None:
    store = DedupeStore(engine)
    k = url_key("c", "1")
    _rec(store, k)
    _rec(store, k)
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM assets_seen")).scalar() == 1


def _plan(engine: Engine, store: DedupeStore, ph: int, max_distance: int) -> str:
    compiled = store._phash_stmt(1, ph, max_distance).compile(dialect=engine.dialect)
    params = tuple(compiled.params[k] for k in compiled.positiontup or ())
    with engine.connect() as c:
        rows = c.exec_driver_sql("EXPLAIN QUERY PLAN " + str(compiled), params)
        return "\n".join(str(r[-1]) for r in rows)


def test_phash_query_uses_index(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        pytest.skip("sqlite-specific")
    store = DedupeStore(engine)
    plan = _plan(engine, store, to_signed64(PH), 3)
    for n in range(4):
        assert f"ix_assets_seen_target_ph{n} (target_id=? AND ph{n}=?)" in plan
    assert "SCAN assets_seen" not in plan


def test_phash_four_chunks_each_flipped_not_found(engine: Engine) -> None:
    store = DedupeStore(engine)
    _rec(store, url_key("c", "1"), phash=to_signed64(PH))
    assert store.match_phash(1, _flip(PH, [0, 20, 40, 60]), 3) is None


def test_phash_many_candidates_same_chunk(engine: Engine) -> None:
    store = DedupeStore(engine)
    ids = {}
    for i in range(60):
        # same top chunk (ph0), differing low bits: distance i % 20 + 1 from query
        bits = list(range(i % 20 + 1))
        ph = _flip(PH, [b + 8 for b in bits])
        a = str(uuid.uuid4())
        ids[i] = a
        _rec(store, url_key("c", str(i)), phash=ph, asset=a)
    # closest rows have distance 1 (i = 0, 20, 40); query is exactly 1 off them
    ref = store.match_phash(1, to_signed64(PH), 1)
    assert ref is not None and ref.immich_asset_id in {ids[0], ids[20], ids[40]}
    assert store.match_phash(1, _flip(PH, [60, 61]), 1) is None


def test_hamming_udf(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        pytest.skip("sqlite-specific")
    with engine.connect() as c:
        q = "SELECT hamming(:a, :b)"
        assert c.execute(text(q), {"a": -1, "b": 0}).scalar() == 64
        assert c.execute(text(q), {"a": 5, "b": 5}).scalar() == 0
        assert c.execute(text(q), {"a": -(2**63), "b": 2**63 - 1}).scalar() == 64
        assert c.execute(text(q), {"a": None, "b": 1}).scalar() is None


def test_sync_engine_url_mapping() -> None:
    cases = {
        "sqlite+aiosqlite:///x.db": "sqlite+pysqlite",
        "postgresql+asyncpg://u@h/d": "postgresql+psycopg",
        "postgres://u@h/d": "postgresql+psycopg",
        "postgresql://u@h/d": "postgresql+psycopg",
    }
    for url, driver in cases.items():
        eng = make_sync_engine(url)
        assert eng.url.drivername == driver
        eng.dispose()


def test_sync_engine_pg_url_parts_survive() -> None:
    eng = make_sync_engine(
        "postgresql+asyncpg://us%40er:p%2Fw%3Ad@db.example:5433/mydb?ssl=require&application_name=x"
    )
    u = eng.url
    assert (u.username, u.password, u.host, u.port, u.database) == (
        "us@er",
        "p/w:d",
        "db.example",
        5433,
        "mydb",
    )
    assert dict(u.query) == {"sslmode": "require", "application_name": "x"}
    eng.dispose()


def test_match_deleted_sha1_and_phash(engine: Engine) -> None:
    store = DedupeStore(engine)
    sha = b"\x07" * 20
    _rec(store, b"a" * 16, sha1=sha, phash=PH, asset=None)
    _rec(store, b"b" * 16, sha1=b"\x08" * 20, phash=PH ^ 0xFFFF_FFFF_0000_0000, asset=ASSET)
    assert store.match_deleted(1, sha, None, None)
    assert not store.match_deleted(2, sha, None, None)
    assert not store.match_deleted(1, b"\x09" * 20, None, None)
    assert store.match_deleted(1, b"\x09" * 20, to_signed64(PH ^ 0b111), 3)
    assert not store.match_deleted(1, b"\x09" * 20, to_signed64(PH ^ 0b1111), 3)
    assert not store.match_deleted(1, b"\x09" * 20, to_signed64(PH ^ 1), None)
    # rows with an asset id are not "deleted"
    assert not store.match_deleted(1, b"\x08" * 20, None, None)
