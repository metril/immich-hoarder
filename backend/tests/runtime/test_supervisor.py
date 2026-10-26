import asyncio
import multiprocessing as mp
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import fake_workers as fw
import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.crypto import SecretBox
from app.db.engine import make_engine
from app.db.models import (
    AssetSeen,
    Base,
    ImmichTarget,
    Job,
    JobStatus,
    Source,
    User,
)
from app.runtime.bus import EventBus
from app.runtime.supervisor import JobConflict, JobNotActive, JobSupervisor
from app.runtime.writer import IpcBridge, JobWriter, make_ipc_queue

KEY = "test-master-key-0123456789abcdef-xyz"


@dataclass
class Env:
    sf: async_sessionmaker[AsyncSession]
    settings: Settings
    writer: JobWriter
    q: Any
    scratch: Path
    make: Callable[..., JobSupervisor]
    seed: Callable[..., Any]
    owner_id: int


@pytest.fixture
async def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Env]:
    eng = make_engine(f"sqlite+aiosqlite:///{tmp_path / 'sup.db'}")
    async with eng.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    sf = async_sessionmaker(eng, expire_on_commit=False)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'sup.db'}",
        master_key=SecretStr(KEY),
        session_secret=SecretStr("test-session-secret-0123456789abcdef"),
        public_url="http://testserver",
        scratch_dir=scratch,
        max_concurrent_jobs=2,
    )
    box = SecretBox(KEY)
    async with sf() as s:
        u = User(sub="u")
        s.add(u)
        await s.flush()
        owner_id = u.id
        await s.commit()
    ctx = mp.get_context("spawn")
    q = make_ipc_queue(ctx)
    writer = JobWriter(sf, EventBus())
    writer.start()
    bridge = IpcBridge(q, writer, asyncio.get_running_loop())
    bridge.start()
    sups: list[JobSupervisor] = []

    async def seed(target: int | None = None, disabled: bool = False) -> tuple[int, int]:
        """Create (target_id, source_id); reuse target if given."""
        async with sf() as s:
            if target is None:
                t = ImmichTarget(
                    owner_id=owner_id, name="t", url="http://i", api_key_enc=box.encrypt(b"k")
                )
                s.add(t)
                await s.flush()
                target = t.id
            src = Source(
                owner_id=owner_id, name="s", url="http://s", extractor="x", target_id=target
            )
            s.add(src)
            if disabled:
                (await s.get(User, owner_id)).disabled = True  # type: ignore[union-attr]
            await s.commit()
            return target, src.id

    def make(worker_target: Any = fw.fast_worker) -> JobSupervisor:
        sup = JobSupervisor(
            sf, writer, settings, mp_ctx=ctx, ipc_queue=q, worker_target=worker_target
        )
        sup.poll_s = 0.05
        sup.grace_override_s = 0.2
        sup.kill_delay_s = 0.3
        sup.done_wait_s = 1.0
        sups.append(sup)
        return sup

    yield Env(sf, settings, writer, q, scratch, make, seed, owner_id)  # type: ignore[arg-type]
    for sup in sups:
        await sup.stop()
    await asyncio.to_thread(bridge.stop)
    await writer.stop()
    await eng.dispose()


async def wait_for(env: Env, job_id: int, status: JobStatus, timeout: float = 20) -> Job:
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        async with env.sf() as s:
            job = await s.get(Job, job_id)
        assert job is not None
        if job.status == status:
            return job
        assert asyncio.get_running_loop().time() < deadline, f"{job.status} != {status}"
        await asyncio.sleep(0.05)


async def test_job_succeeds_and_scratch_removed(env: Env) -> None:
    _, src = await env.seed()
    sup = env.make(fw.fast_worker)
    await sup.start()
    job = await sup.enqueue(src, None, "info")
    done = await wait_for(env, job.id, JobStatus.succeeded)
    assert done.counters == {"linked": 1}
    assert done.started_at is not None and done.finished_at is not None
    assert not (env.scratch / str(job.id)).exists()
    assert sup.running == {}


async def test_failed_status_and_scratch_removed(env: Env) -> None:
    _, src = await env.seed()
    sup = env.make(fw.failing_worker)
    await sup.start()
    job = await sup.enqueue(src, None, "info")
    done = await wait_for(env, job.id, JobStatus.failed)
    assert done.error == "boom"
    assert not (env.scratch / str(job.id)).exists()


async def test_one_job_per_source_conflict(env: Env) -> None:
    _, src = await env.seed()
    sup = env.make(fw.slow_worker)
    job = await sup.enqueue(src, None, "info")  # queued, loop not started
    with pytest.raises(JobConflict):
        await sup.enqueue(src, None, "info")
    await sup.cancel(job.id)
    await wait_for(env, job.id, JobStatus.cancelled)
    await sup.enqueue(src, None, "info")  # allowed once the first finished


async def test_one_running_per_target_and_concurrency_cap(env: Env) -> None:
    t1, a = await env.seed()
    _, b = await env.seed(target=t1)
    _, c = await env.seed()
    _, d = await env.seed()
    sup = env.make(fw.slow_worker)
    await sup.start()
    ja = await sup.enqueue(a, None, "info")
    jb = await sup.enqueue(b, None, "info")  # same target as a: must wait
    jc = await sup.enqueue(c, None, "info")
    jd = await sup.enqueue(d, None, "info")  # cap=2: must wait
    await wait_for(env, ja.id, JobStatus.running)
    await wait_for(env, jc.id, JobStatus.running)
    await asyncio.sleep(0.5)
    assert set(sup.running) == {ja.id, jc.id}
    async with env.sf() as s:
        assert (await s.get(Job, jb.id)).status == JobStatus.queued  # type: ignore[union-attr]
        assert (await s.get(Job, jd.id)).status == JobStatus.queued  # type: ignore[union-attr]
    await sup.cancel(ja.id)  # frees the target and a slot
    await wait_for(env, ja.id, JobStatus.cancelled)
    await wait_for(env, jb.id, JobStatus.running)
    for j in (jb, jc, jd):
        await sup.cancel(j.id)


async def test_worker_crash_marks_failed_and_frees_slot(env: Env) -> None:
    _, src = await env.seed()
    sup = env.make(fw.crash_worker)
    await sup.start()
    job = await sup.enqueue(src, None, "info")
    done = await wait_for(env, job.id, JobStatus.failed)
    assert done.error == "worker crashed"
    assert sup.running == {}
    assert not (env.scratch / str(job.id)).exists()


async def test_cancel_grace_then_kill(env: Env) -> None:
    _, src = await env.seed()
    sup = env.make(fw.sigterm_proof_worker)
    await sup.start()
    job = await sup.enqueue(src, None, "info")
    marker = env.scratch / str(job.id) / "f"
    for _ in range(400):
        if marker.exists():
            break
        await asyncio.sleep(0.05)
    assert marker.exists()
    h = sup.running[job.id]
    await sup.cancel(job.id)
    await wait_for(env, job.id, JobStatus.cancelled)
    assert h.exitcode == -9  # SIGTERM ignored, so only kill() ends it
    assert not (env.scratch / str(job.id)).exists()


async def test_exit_zero_waits_for_late_done(env: Env) -> None:
    _, src = await env.seed()
    sup = env.make(fw.fast_worker)
    sup.done_wait_s = 0.01  # shorter than the writer flush: only exit!=0 may use it
    await sup.start()
    job = await sup.enqueue(src, None, "info")
    await wait_for(env, job.id, JobStatus.succeeded)


async def test_late_done_after_finalize_is_ignored_and_logged(
    env: Env, caplog: pytest.LogCaptureFixture
) -> None:
    sup = env.make(fw.fast_worker)
    with caplog.at_level("WARNING"):
        await sup._on_done(4242, {"status": "succeeded"})
    assert "4242" in caplog.text


async def test_cancel_during_pick_never_runs(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    _, src = await env.seed()
    sup = env.make(fw.slow_worker)
    job = await sup.enqueue(src, None, "info")
    gate = asyncio.Event()
    orig_prepare = sup._prepare

    async def slow_prepare(job_id: int, h: Any) -> Any:
        await gate.wait()
        return await orig_prepare(job_id, h)

    monkeypatch.setattr(sup, "_prepare", slow_prepare)
    orig_queued = sup._is_queued

    async def racing(job_id: int) -> bool:
        result = await orig_queued(job_id)
        await sup._start_ready()  # the pick lands while cancel awaited the DB
        return result

    monkeypatch.setattr(sup, "_is_queued", racing)
    await sup.cancel(job.id)
    assert job.id in sup.running
    h = sup.running[job.id]
    gate.set()
    await wait_for(env, job.id, JobStatus.cancelled)
    assert h.process is None  # never spawned


async def test_stop_prevents_new_picks(env: Env) -> None:
    _, src = await env.seed()
    sup = env.make(fw.fast_worker)
    await sup.enqueue(src, None, "info")
    await sup.stop()
    await sup._start_ready()
    assert sup.running == {}


async def test_concurrent_enqueue_creates_one_job(env: Env) -> None:
    _, src = await env.seed()
    sup = env.make(fw.fast_worker)
    res = await asyncio.gather(
        sup.enqueue(src, None, "info"), sup.enqueue(src, None, "info"), return_exceptions=True
    )
    assert sorted(type(r).__name__ for r in res) == ["Job", "JobConflict"]
    async with env.sf() as s:
        assert len((await s.execute(select(Job.id))).all()) == 1


async def test_skip_set_is_cleaned(env: Env) -> None:
    _, src = await env.seed()
    sup = env.make(fw.slow_worker)
    job = await sup.enqueue(src, None, "info")
    await sup.cancel(job.id)
    await wait_for(env, job.id, JobStatus.cancelled)
    await sup.start()
    await asyncio.sleep(0.3)
    assert sup._skip == set()


@pytest.mark.parametrize("case", ["success", "failed", "crash", "cancel", "revoked", "prepare"])
async def test_scratch_removed_after_every_outcome(
    env: Env, case: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, src = await env.seed(disabled=case == "revoked")
    worker = {
        "success": fw.fast_worker,
        "failed": fw.failing_worker,
        "crash": fw.crash_worker,
        "cancel": fw.slow_worker,
    }.get(case, fw.fast_worker)
    sup = env.make(worker)
    if case == "prepare":

        async def boom(job_id: int, h: Any) -> Any:
            raise RuntimeError("x")

        monkeypatch.setattr(sup, "_prepare", boom)
    job = await sup.enqueue(src, None, "info")
    leftover = env.scratch / str(job.id)
    leftover.mkdir()
    (leftover / "junk").write_text("x")
    await sup.start()
    if case == "cancel":
        await wait_for(env, job.id, JobStatus.running)
        for _ in range(400):
            if sup.running[job.id].process is not None:
                break
            await asyncio.sleep(0.05)
        await sup.cancel(job.id)
        await wait_for(env, job.id, JobStatus.cancelled)
    else:
        for _ in range(400):
            async with env.sf() as s:
                st = (await s.get(Job, job.id)).status  # type: ignore[union-attr]
            if st in (JobStatus.succeeded, JobStatus.failed):
                break
            await asyncio.sleep(0.05)
    for _ in range(100):
        if job.id not in sup.running:
            break
        await asyncio.sleep(0.05)
    assert not leftover.exists()


async def test_cancel_finished_job_raises(env: Env) -> None:
    _, src = await env.seed()
    sup = env.make(fw.fast_worker)
    await sup.start()
    job = await sup.enqueue(src, None, "info")
    await wait_for(env, job.id, JobStatus.succeeded)
    with pytest.raises(JobNotActive):
        await sup.cancel(job.id)


async def test_startup_recovery_running_to_failed_and_queued_resume(env: Env) -> None:
    _, s1 = await env.seed()
    _, s2 = await env.seed()
    orphan = env.scratch / "999"
    orphan.mkdir()
    async with env.sf() as s:
        r = Job(source_id=s1, status=JobStatus.running)
        qd = Job(source_id=s2, status=JobStatus.queued)
        s.add_all([r, qd])
        await s.commit()
    sup = env.make(fw.fast_worker)
    await sup.start()
    failed = await wait_for(env, r.id, JobStatus.failed)
    assert failed.error == "interrupted by restart"
    await wait_for(env, qd.id, JobStatus.succeeded)
    assert not orphan.exists()


async def test_access_revoked_fails_job(env: Env) -> None:
    _, src = await env.seed(disabled=True)
    sup = env.make(fw.fast_worker)
    await sup.start()
    job = await sup.enqueue(src, None, "info")
    done = await wait_for(env, job.id, JobStatus.failed)
    assert done.error == "access revoked"
    assert sup.running == {}


async def test_incremental_computed_when_job_starts(env: Env) -> None:
    t, src = await env.seed()
    sup = env.make(fw.incremental_worker)
    job = await sup.enqueue(src, None, "info")
    async with env.sf() as s:
        s.add(AssetSeen(target_id=t, source_id=src, url_hash=b"x" * 16, seen_at=1))
        await s.commit()
    await sup.start()
    done = await wait_for(env, job.id, JobStatus.succeeded)
    assert done.counters == {"incremental": True}


async def test_cancel_queued_goes_straight_to_cancelled(env: Env) -> None:
    _, src = await env.seed()
    sup = env.make(fw.slow_worker)
    job = await sup.enqueue(src, None, "info")
    await sup.cancel(job.id)
    done = await wait_for(env, job.id, JobStatus.cancelled)
    assert isinstance(done.finished_at, datetime)
    await sup.start()
    await asyncio.sleep(0.3)
    assert sup.running == {}
    async with env.sf() as s:
        assert (await s.execute(select(Job.status).where(Job.id == job.id))).scalar_one() == (
            JobStatus.cancelled
        )


async def test_lifespan_wires_runtime(settings: Settings) -> None:
    from app.main import create_app

    app = create_app(settings)
    async with app.router.lifespan_context(app):
        assert isinstance(app.state.supervisor, JobSupervisor)
    off = create_app(settings)
    off.state.runtime_enabled = False
    async with off.router.lifespan_context(off):
        assert not hasattr(off.state, "supervisor")
