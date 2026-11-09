"""Per-target dedupe store with multi-index pHash lookup."""

import time
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

import xxhash
from sqlalchemy import Engine, cast, func, literal, select, union, union_all, update
from sqlalchemy.dialects.postgresql import BIT
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.sql import ColumnElement, Select

from app.db.models import AssetSeen
from app.rip.media import chunks16, to_signed64


@dataclass(frozen=True)
class AssetRef:
    immich_asset_id: str | None


@dataclass(frozen=True)
class Existing:
    """Outcome of one combined lookup: the live match (if any) and whether a deleted one exists."""

    live: AssetRef | None = None
    how: str = ""  # "sha1" | "phash" when ``live`` is set
    deleted: bool = False


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

    def rebind_asset(
        self, *, target_id: int, sha1: bytes, new_asset_id: str, old_asset_id: str | None
    ) -> None: ...


def url_key(category: str, archive_key: str) -> bytes:
    return xxhash.xxh128(f"{category}\x00{archive_key}".encode()).digest()


def _ref(raw: bytes | None) -> AssetRef:
    return AssetRef(str(uuid.UUID(bytes=raw)) if raw is not None else None)


def assets_seen_row(
    *,
    target_id: int,
    source_id: int,
    key: bytes,
    sha1: bytes | None,
    phash: int | None,
    immich_asset_id: str | None,
) -> dict[str, Any]:
    ph = None if phash is None else to_signed64(phash)
    chunks = chunks16(ph) if ph is not None else (None,) * 4
    return {
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


def insert_ignore(dialect_name: str, table: Any) -> Any:
    """INSERT ... ON CONFLICT (source_id, url_hash) DO NOTHING for the given dialect."""
    ins = pg_insert if dialect_name == "postgresql" else sqlite_insert
    return ins(table).on_conflict_do_nothing(index_elements=["source_id", "url_hash"])


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

    @staticmethod
    def _chunk_selects(
        target_id: int, phash_signed: int, deleted: bool | None = None
    ) -> list[Select[Any]]:
        # UNION of 4 single-index lookups (the planner reliably uses each
        # (target_id, phN) index, unlike an OR). ``deleted``: None = both.
        cs = chunks16(phash_signed)
        cols = (AssetSeen.ph0, AssetSeen.ph1, AssetSeen.ph2, AssetSeen.ph3)
        out: list[Any] = []
        for col, c in zip(cols, cs, strict=True):
            q = select(AssetSeen.immich_asset_id, AssetSeen.phash).where(
                AssetSeen.target_id == target_id, col == c
            )
            if deleted is not None:
                q = q.where(
                    AssetSeen.immich_asset_id.is_(None)
                    if deleted
                    else AssetSeen.immich_asset_id.is_not(None)
                )
            out.append(q)
        return out

    def _distance(self, phash_col: Any, phash_signed: int) -> Any:
        # Computed and filtered in SQL so the candidate set never reaches Python.
        if self._engine.dialect.name == "postgresql":
            # Requires PostgreSQL >= 14 (bit_count).
            return func.bit_count(cast(phash_col.op("#")(phash_signed), BIT(64)))
        return func.hamming(phash_col, phash_signed)

    def _phash_stmt(
        self, target_id: int, phash_signed: int, max_distance: int, deleted: bool = False
    ) -> Select[Any]:
        cand = union(*self._chunk_selects(target_id, phash_signed, deleted)).subquery()
        dist = self._distance(cand.c.phash, phash_signed)
        d = dist.label("d")
        return select(cand.c.immich_asset_id, d).where(dist <= max_distance).order_by(d).limit(1)

    def lookup(
        self, target_id: int, sha1: bytes, phash_signed: int | None, max_distance: int | None
    ) -> Existing:
        """Live and deleted matches in one round trip; live wins, SHA-1 before pHash.

        Same outcomes as ``match_sha1``, then ``match_phash``, then ``match_deleted``.
        """
        sha = (
            select(literal(0).label("k"), AssetSeen.immich_asset_id.label("a"))
            .where(AssetSeen.target_id == target_id, AssetSeen.sha1 == sha1)
            .order_by(AssetSeen.immich_asset_id.is_(None))  # live rows first
            .limit(1)
            .subquery()
        )
        parts: list[Any] = [select(sha.c.k, sha.c.a, literal(0).label("d"))]
        if phash_signed is not None and max_distance is not None:
            cand = union(*self._chunk_selects(target_id, phash_signed)).subquery()
            dist = self._distance(cand.c.phash, phash_signed)
            ph = (
                select(literal(1).label("k"), cand.c.immich_asset_id.label("a"), dist.label("d"))
                .where(dist <= max_distance)
                .order_by(cand.c.immich_asset_id.is_(None), dist)
                .limit(8)
                .subquery()
            )
            parts.append(select(ph.c.k, ph.c.a, ph.c.d))
        stmt: Any = parts[0]
        if len(parts) > 1:
            stmt = union_all(*parts)
        with self._engine.connect() as c:
            rows = c.execute(stmt).all()
        deleted = any(r[1] is None for r in rows)
        for r in rows:
            if r[0] == 0 and r[1] is not None:
                return Existing(_ref(r[1]), "sha1", deleted)
        live = [r for r in rows if r[0] == 1 and r[1] is not None]
        if live:
            return Existing(_ref(min(live, key=lambda r: r[2])[1]), "phash", deleted)
        return Existing(None, "", deleted)

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
        values = assets_seen_row(
            target_id=target_id,
            source_id=source_id,
            key=key,
            sha1=sha1,
            phash=phash,
            immich_asset_id=immich_asset_id,
        )
        stmt = insert_ignore(self._engine.dialect.name, AssetSeen).values(values)
        with self._engine.begin() as c:
            c.execute(stmt)

    def rebind_asset(
        self, *, target_id: int, sha1: bytes, new_asset_id: str, old_asset_id: str | None
    ) -> None:
        """Point this content's dead/NULL rows (same sha1 only) at its live asset."""
        stmt = rebind_stmt(target_id, sha1, new_asset_id, old_asset_id)
        with self._engine.begin() as c:
            c.execute(stmt)


def rebind_stmt(target_id: int, sha1: bytes, new_asset_id: str, old_asset_id: str | None) -> Any:
    dead: ColumnElement[bool] = AssetSeen.immich_asset_id.is_(None)
    if old_asset_id is not None:
        dead = dead | (AssetSeen.immich_asset_id == uuid.UUID(old_asset_id).bytes)
    return (
        update(AssetSeen)
        .where(AssetSeen.target_id == target_id, AssetSeen.sha1 == sha1, dead)
        .values(immich_asset_id=uuid.UUID(new_asset_id).bytes)
    )
