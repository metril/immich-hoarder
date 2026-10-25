import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.db.engine import make_sync_engine
from app.db.models import Base, ImmichTarget, Source, User
from app.rip.dedupe import DedupeStore, url_key
from app.rip.media import to_signed64

ASSET = str(uuid.uuid4())
PH = 0x0123_4567_89AB_CDEF


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    eng = make_sync_engine(f"sqlite+aiosqlite:///{tmp_path / 'd.db'}")
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


def test_record_without_source(engine: Engine) -> None:
    store = DedupeStore(engine)
    store.record(
        target_id=1,
        source_id=None,
        key=url_key("c", "1"),
        sha1=b"\x02" * 20,
        phash=None,
        immich_asset_id=ASSET,
    )
    assert store.match_sha1(1, b"\x02" * 20) is not None


def test_phash_query_uses_index(engine: Engine) -> None:
    store = DedupeStore(engine)
    plan = store.phash_plan(1, to_signed64(PH))
    for n in range(4):
        assert f"ix_assets_seen_target_ph{n} (target_id=? AND ph{n}=?)" in plan
    assert "SCAN" not in plan


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
