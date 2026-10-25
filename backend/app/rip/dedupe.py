"""Per-target dedupe store with multi-index pHash lookup."""

import time
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

import xxhash
from sqlalchemy import Engine, select, union
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.sql import CompoundSelect

from app.db.models import AssetSeen
from app.rip.media import chunks16, hamming, to_signed64


@dataclass(frozen=True)
class AssetRef:
    immich_asset_id: str | None


class Recorder(Protocol):
    def record(
        self,
        *,
        target_id: int,
        source_id: int | None,
        key: bytes,
        sha1: bytes | None,
        phash: int | None,
        immich_asset_id: str | None,
    ) -> None: ...


def url_key(category: str, archive_key: str) -> bytes:
    return xxhash.xxh128(f"{category}\x00{archive_key}".encode()).digest()


def _ref(raw: bytes | None) -> AssetRef:
    return AssetRef(str(uuid.UUID(bytes=raw)) if raw is not None else None)


class DedupeStore:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def url_seen(self, source_id: int, key: bytes) -> bool:
        stmt = (
            select(AssetSeen.id)
            .where(AssetSeen.source_id == source_id, AssetSeen.url_hash == key)
            .limit(1)
        )
        with self._engine.connect() as c:
            return c.execute(stmt).first() is not None

    def match_sha1(self, target_id: int, sha1: bytes) -> AssetRef | None:
        stmt = (
            select(AssetSeen.immich_asset_id)
            .where(
                AssetSeen.target_id == target_id,
                AssetSeen.sha1 == sha1,
                AssetSeen.immich_asset_id.is_not(None),
            )
            .limit(1)
        )
        with self._engine.connect() as c:
            row = c.execute(stmt).first()
        return _ref(row[0]) if row else None

    def _phash_stmt(self, target_id: int, phash_signed: int) -> CompoundSelect[Any]:
        # UNION of 4 single-index lookups: the planner reliably uses each
        # (target_id, phN) index, unlike an OR which may fall back to a target scan.
        cs = chunks16(phash_signed)
        cols = (AssetSeen.ph0, AssetSeen.ph1, AssetSeen.ph2, AssetSeen.ph3)
        selects = [
            select(AssetSeen.phash, AssetSeen.immich_asset_id).where(
                AssetSeen.target_id == target_id,
                col == c,
                AssetSeen.immich_asset_id.is_not(None),
            )
            for col, c in zip(cols, cs, strict=True)
        ]
        return union(*selects)

    def phash_plan(self, target_id: int, phash_signed: int) -> str:
        """EXPLAIN QUERY PLAN output (SQLite) for the candidate query."""
        compiled = self._phash_stmt(target_id, phash_signed).compile(dialect=self._engine.dialect)
        params = tuple(compiled.params[k] for k in compiled.positiontup or ())
        with self._engine.connect() as c:
            rows = c.exec_driver_sql("EXPLAIN QUERY PLAN " + str(compiled), params)
            return "\n".join(str(r[-1]) for r in rows)

    def match_phash(self, target_id: int, phash_signed: int, max_distance: int) -> AssetRef | None:
        with self._engine.connect() as c:
            rows = c.execute(self._phash_stmt(target_id, phash_signed)).all()
        best: tuple[int, bytes] | None = None
        for ph, asset in rows:
            if ph is None:
                continue
            d = hamming(ph, phash_signed)
            if d <= max_distance and (best is None or d < best[0]):
                best = (d, asset)
        return _ref(best[1]) if best else None

    def record(
        self,
        *,
        target_id: int,
        source_id: int | None,
        key: bytes,
        sha1: bytes | None,
        phash: int | None,
        immich_asset_id: str | None,
    ) -> None:
        ph = None if phash is None else to_signed64(phash)
        chunks = chunks16(ph) if ph is not None else (None,) * 4
        values: dict[str, Any] = {
            "target_id": target_id,
            "source_id": source_id,
            "url_hash": key,
            "sha1": sha1,
            "phash": ph,
            "ph0": chunks[0],
            "ph1": chunks[1],
            "ph2": chunks[2],
            "ph3": chunks[3],
            "immich_asset_id": (
                uuid.UUID(immich_asset_id).bytes if immich_asset_id is not None else None
            ),
            "seen_at": int(time.time()),
        }
        dialect = self._engine.dialect.name
        if dialect == "postgresql":
            stmt: Any = pg_insert(AssetSeen).values(values)
            stmt = stmt.on_conflict_do_nothing(index_elements=["source_id", "url_hash"])
        else:
            stmt = sqlite_insert(AssetSeen).values(values)
            stmt = stmt.on_conflict_do_nothing(index_elements=["source_id", "url_hash"])
        with self._engine.begin() as c:
            c.execute(stmt)
