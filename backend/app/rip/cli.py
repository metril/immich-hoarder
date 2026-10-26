"""Operator CLI: python -m app.rip run --source-id N [--log-level LEVEL]."""

import argparse
import asyncio
import logging
import signal
import sys
import threading
import time
from collections.abc import Sequence
from typing import Any

import orjson
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.crypto import SecretBox
from app.db.engine import make_engine, make_sync_engine
from app.db.models import AssetSeen, Source
from app.immich.client import ImmichClient
from app.rip.build import build_snapshots
from app.rip.dedupe import DedupeStore
from app.rip.pipeline import RipContext, run_rip
from app.rip.settings import load_rip_settings
from app.rip.snapshot import TargetSnapshot

_EXIT = {"succeeded": 0, "failed": 1, "cancelled": 130}
_LEVELS = ("error", "warn", "info", "debug", "trace")


def _emit(ev: dict[str, Any]) -> None:
    sys.stdout.write(orjson.dumps(ev, default=str).decode() + "\n")
    sys.stdout.flush()


async def _load(source_id: int, box: SecretBox, url: str) -> Any:
    engine = make_engine(url)
    try:
        async with engine.connect() as conn:
            from sqlalchemy.ext.asyncio import AsyncSession

            async with AsyncSession(bind=conn, expire_on_commit=False) as session:
                source = await session.get(Source, source_id)
                if source is None:
                    return None
                snaps = await build_snapshots(session, source, box)
                return snaps, await load_rip_settings(session)
    finally:
        await engine.dispose()


def _run(source_id: int, log_level: str | None) -> int:
    st = get_settings()
    box = SecretBox(st.master_key.get_secret_value())
    loaded = asyncio.run(_load(source_id, box, st.database_url))
    if loaded is None:
        sys.stderr.write(f"source {source_id} not found\n")
        return 1
    (src, target, cred), rip = loaded
    if log_level:
        src.log_level = log_level
    engine = make_sync_engine(st.database_url)
    cancel = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: cancel.set())
    try:
        with Session(engine) as s:
            incremental = (
                s.execute(
                    select(AssetSeen.id).where(AssetSeen.source_id == src.id).limit(1)
                ).first()
                is not None
            )
        store = DedupeStore(engine)
        cap = rip.job_scratch_max_bytes or st.scratch_max_bytes // max(st.max_concurrent_jobs, 1)
        ctx = RipContext(
            job_id=int(time.time()),
            source=src,
            target=target,
            credential=cred,
            settings=rip,
            scratch_dir=st.scratch_dir,
            scratch_cap_bytes=cap,
            incremental=incremental,
            store=store,
            recorder=store,
            client_factory=_client,
        )
        result = run_rip(ctx, _emit, cancel)
    finally:
        engine.dispose()
    return _EXIT[result.status]


def _client(t: TargetSnapshot) -> ImmichClient:
    return ImmichClient(t.url, t.api_key.get_secret_value())


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.rip")
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="run one source to completion")
    run.add_argument("--source-id", type=int, required=True)
    run.add_argument("--log-level", choices=_LEVELS)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    try:
        return _run(args.source_id, args.log_level)
    except Exception as e:
        sys.stderr.write(f"error: {type(e).__name__}\n")
        return 1
