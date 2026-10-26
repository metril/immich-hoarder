"""Per-target dedupe store with multi-index pHash lookup."""

import time
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

import xxhash
from sqlalchemy import Engine, cast, func, select, union
from sqlalchemy.dialects.postgresql import BIT
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.sql import Select

from app.db.models import AssetSeen
from app.rip.media import chunks16, to_signed64


@dataclass(frozen=True)
class AssetRef:
    immich_asset_id: str | None


class Recorder(Protocol):
    def record(
        self,
        *,
        target_id: int,
        source_id: int,
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

    def _phash_stmt(
        self, target_id: int, phash_signed: int, max_distance: int, deleted: bool = False
    ) -> Select[Any]:
        # UNION of 4 single-index lookups (the planner reliably uses each
        # (target_id, phN) index, unlike an OR). Distance is computed and
        # filtered in SQL so the candidate set never reaches Python.
        cs = chunks16(phash_signed)
        cols = (AssetSeen.ph0, AssetSeen.ph1, AssetSeen.ph2, AssetSeen.ph3)
        selects = [
            select(AssetSeen.immich_asset_id, AssetSeen.phash).where(
                AssetSeen.target_id == target_id,
                col == c,
                AssetSeen.immich_asset_id.is_(None)
                if deleted
                else AssetSeen.immich_asset_id.is_not(None),
            )
            for col, c in zip(cols, cs, strict=True)
        ]
        cand = union(*selects).subquery()
        if self._engine.dialect.name == "postgresql":
            # Requires PostgreSQL >= 14 (bit_count).
            dist = func.bit_count(cast(cand.c.phash.op("#")(phash_signed), BIT(64)))
        else:
            dist = func.hamming(cand.c.phash, phash_signed)
        d = dist.label("d")
        return select(cand.c.immich_asset_id, d).where(dist <= max_distance).order_by(d).limit(1)

    def match_phash(self, target_id: int, phash_signed: int, max_distance: int) -> AssetRef | None:
        with self._engine.connect() as c:
            row = c.execute(self._phash_stmt(target_id, phash_signed, max_distance)).first()
        return _ref(row[0]) if row else None

    def match_deleted(
        self, target_id: int, sha1: bytes, phash_signed: int | None, max_distance: int | None
    ) -> bool:
        """True when a row without an asset id (deleted in Immich) matches by sha1 or pHash."""
        stmt = (
            select(AssetSeen.id)
            .where(
                AssetSeen.target_id == target_id,
                AssetSeen.sha1 == sha1,
                AssetSeen.immich_asset_id.is_(None),
            )
            .limit(1)
        )
        with self._engine.connect() as c:
            if c.execute(stmt).first() is not None:
                return True
            if phash_signed is None or max_distance is None:
                return False
            ps = self._phash_stmt(target_id, phash_signed, max_distance, deleted=True)
            return c.execute(ps).first() is not None

    def record(
        self,
        *,
        target_id: int,
        source_id: int,
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
