"""Manual dedupe load test: seed N assets_seen rows, then time the real DedupeStore lookups.

Run from backend/: python -m loadtest.dedupe --rows 1000000 --db /tmp/lt.db
"""

import argparse
import random
import sqlite3
import sys
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from sqlalchemy import MetaData, UniqueConstraint, insert, text
from sqlalchemy.dialects import sqlite
from sqlalchemy.schema import CreateTable, Table

from app.db.engine import make_sync_engine
from app.db.migrate import upgrade_head
from app.db.models import AssetSeen, Base, ImmichTarget, Role, Source, User
from app.rip.dedupe import DedupeStore, assets_seen_row
from app.rip.media import to_signed64

BATCH = 1_000_000
PROGRESS = 10_000_000
SAMPLE_CAP = 20_000
_TABLE = cast(Table, AssetSeen.__table__)
COLS = [c.name for c in _TABLE.columns if c.name != "id"]
INSERT = f"INSERT INTO assets_seen ({','.join(COLS)}) VALUES ({','.join('?' * len(COLS))})"


def _pct(samples: list[int], q: float) -> float:
    s = sorted(samples)
    return s[min(len(s) - 1, int(len(s) * q))] / 1e6


def _seed_base(url: str, targets: int, sources: int) -> None:
    engine = make_sync_engine(url)
    with engine.begin() as c:
        c.execute(insert(User).values(sub="lt", role=Role.admin))
        for t in range(1, targets + 1):
            c.execute(
                insert(ImmichTarget).values(
                    name=f"t{t}", url="http://immich.invalid", api_key_enc=b"\x00", owner_id=1
                )
            )
        for s in range(1, sources + 1):
            c.execute(
                insert(Source).values(
                    name=f"s{s}",
                    url="http://s.invalid",
                    extractor="gallery-dl",
                    target_id=(s - 1) % targets + 1,
                    owner_id=1,
                )
            )
    engine.dispose()


def _seed(url: str, db: Path, rows: int, targets: int, sources: int) -> dict[str, list[Any]]:
    _seed_base(url, targets, sources)
    rng = random.Random(0)
    con = sqlite3.connect(db, isolation_level=None)
    con.execute("PRAGMA foreign_keys=OFF")
    # Rebuild the indexes after bulk load: drop them (and the unique index) first.
    ddl: list[str] = []
    for idx in _TABLE.indexes:
        con.execute(f'DROP INDEX "{idx.name}"')
        ddl.append(
            f'CREATE INDEX "{idx.name}" ON assets_seen ({", ".join(c.name for c in idx.columns)})'
        )
    ddl.append("CREATE UNIQUE INDEX uq_assets_seen_source_url ON assets_seen (source_id, url_hash)")
    # The unique constraint is an inline sqlite autoindex that cannot be dropped, and the table
    # is still empty: recreate it without constraints/indexes, then add them back after the load.
    md = MetaData()
    for tb in Base.metadata.sorted_tables:
        tb.to_metadata(md)
    t = md.tables["assets_seen"]
    for cons in [c for c in t.constraints if isinstance(c, UniqueConstraint)]:
        t.constraints.discard(cons)
    t.indexes.clear()
    con.execute("DROP TABLE assets_seen")
    con.execute(str(CreateTable(t).compile(dialect=sqlite.dialect())))
    con.execute("PRAGMA synchronous=OFF")
    con.execute("PRAGMA journal_mode=OFF")
    con.execute("PRAGMA cache_size=-262144")
    stride = max(1, rows // SAMPLE_CAP)
    samples: dict[str, list[Any]] = {"keys": [], "sha1": [], "phash": []}
    t0 = time.perf_counter()
    done = 0
    while done < rows:
        n = min(BATCH, rows - done)
        batch = []
        for i in range(done, done + n):
            src = i % sources + 1
            key = rng.randbytes(16)
            sha1 = rng.randbytes(20)
            ph = rng.getrandbits(64)
            row = assets_seen_row(
                target_id=(src - 1) % targets + 1,
                source_id=src,
                key=key,
                sha1=sha1,
                phash=ph,
                immich_asset_id=str(uuid.UUID(bytes=rng.randbytes(16))),
            )
            batch.append(tuple(row[c] for c in COLS))
            if i % stride == 0:
                tgt = row["target_id"]
                samples["keys"].append((src, key))
                samples["sha1"].append((tgt, sha1))
                samples["phash"].append((tgt, to_signed64(ph)))
        con.execute("BEGIN")
        con.executemany(INSERT, batch)
        con.execute("COMMIT")
        before = done
        done += n
        if done // PROGRESS != before // PROGRESS or done == rows:
            el = time.perf_counter() - t0
            print(f"seeded {done:,}/{rows:,} rows ({done / el:,.0f} rows/s)", flush=True)
    t1 = time.perf_counter()
    print("indexing ...", flush=True)
    for stmt in ddl:
        con.execute(stmt)
    print(f"indexes built in {time.perf_counter() - t1:.1f}s", flush=True)
    con.close()
    samples["rows_per_s"] = [rows / (t1 - t0)]
    return samples


def run(
    rows: int, db: Path, targets: int = 4, sources: int = 64, lookups: int = 10_000
) -> dict[str, float]:
    db = Path(db)
    url = f"sqlite+aiosqlite:///{db}"
    upgrade_head(url)
    samples = _seed(url, db, rows, targets, sources)
    engine = make_sync_engine(url)
    with engine.connect() as c:
        c.execute(text("ANALYZE"))
    store = DedupeStore(engine)
    rng = random.Random(1)
    half = max(1, lookups // 2)

    def pick(name: str) -> list[tuple[Any, ...]]:
        pool = samples[name]
        return [pool[rng.randrange(len(pool))] for _ in range(half)]

    def timed(fn: Callable[..., Any], args: list[tuple[Any, ...]]) -> list[int]:
        out: list[int] = []
        for a in args:
            s = time.perf_counter_ns()
            fn(*a)
            out.append(time.perf_counter_ns() - s)
        return out

    url_miss = [(rng.randint(1, sources), rng.randbytes(16)) for _ in range(half)]
    url_t = timed(store.url_seen, pick("keys") + url_miss)

    sha_miss = [(rng.randint(1, targets), rng.randbytes(20)) for _ in range(half)]
    sha_t = timed(store.match_sha1, pick("sha1") + sha_miss)

    ph_hits = []
    for tgt, ph in pick("phash"):
        for b in rng.sample(range(64), rng.randint(0, 3)):
            ph ^= 1 << b
        ph_hits.append((tgt, to_signed64(ph), 3))
    ph_miss = [(rng.randint(1, targets), to_signed64(rng.getrandbits(64)), 3) for _ in range(half)]
    ph_t = timed(store.match_phash, ph_hits + ph_miss)

    res = {"seed_rows_per_s": samples["rows_per_s"][0]}
    for name, t in (("url_seen", url_t), ("match_sha1", sha_t), ("match_phash", ph_t)):
        res[f"{name}_p50"] = _pct(t, 0.5)
        res[f"{name}_p99"] = _pct(t, 0.99)
    size = db.stat().st_size
    res["db_size_mb"] = size / 1e6
    engine.dispose()
    return res


def main() -> int:
    ap = argparse.ArgumentParser(prog="loadtest.dedupe")
    ap.add_argument("--rows", type=int, required=True)
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--targets", type=int, default=4)
    ap.add_argument("--sources", type=int, default=64)
    ap.add_argument("--lookups", type=int, default=10_000)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--p99-ms", type=float, default=5.0)
    a = ap.parse_args()
    if a.db.exists():
        a.db.unlink()
    try:
        r = run(a.rows, a.db, a.targets, a.sources, a.lookups)
    finally:
        if not a.keep:
            for suf in ("", "-wal", "-shm", "-journal"):
                Path(f"{a.db}{suf}").unlink(missing_ok=True)
    print(
        f"\nrows={a.rows:,}  db={r['db_size_mb']:,.0f} MB  seed={r['seed_rows_per_s']:,.0f} rows/s"
    )
    print(f"{'lookup':<12}{'p50 ms':>10}{'p99 ms':>10}  status")
    bad = False
    for n in ("url_seen", "match_sha1", "match_phash"):
        p99 = r[f"{n}_p99"]
        fail = p99 >= a.p99_ms
        bad |= fail
        print(f"{n:<12}{r[f'{n}_p50']:>10.3f}{p99:>10.3f}  {'FAIL' if fail else 'ok'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
