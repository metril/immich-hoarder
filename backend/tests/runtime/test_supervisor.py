import asyncio
import multiprocessing as mp
import os
import signal
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
    Credential,
    CredentialKind,
    ImmichTarget,
    Job,
    JobStatus,
    Setting,
    Source,
    User,
)
from app.runtime.bus import EventBus
from app.runtime.supervisor import JobConflict, JobNotActive, JobSupervisor, RunHandle
from app.runtime.worker import worker_main
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
        scratch_dir=scratch,
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


async def wait_until(cond: Callable[[], bool], timeout: float = 20) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not cond():
        assert asyncio.get_running_loop().time() < deadline, "condition not met"
        await asyncio.sleep(0.02)


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


JAR = ".reddit.com\tTRUE\t/\tTRUE\t4102444800\treddit_session\tNEWVALUE\n"


async def _cookie_source(env: Env, secret: str) -> tuple[int, int, bytes]:
    box = SecretBox(KEY)
    _, src_id = await env.seed()
    async with env.sf() as s:
        cred = Credential(
            owner_id=env.owner_id,
            name="c",
            site="reddit",
            kind=CredentialKind.cookies,
            secret_enc=box.encrypt(secret.encode()),
        )
        s.add(cred)
        await s.flush()
        (await s.get(Source, src_id)).credential_id = cred.id  # type: ignore[union-attr]
        await s.commit()
        return cred.id, src_id, cred.secret_enc


async def _secret(env: Env, cid: int) -> str:
    async with env.sf() as s:
        row = await s.get(Credential, cid)
        return SecretBox(KEY).decrypt(row.secret_enc).decode()  # type: ignore[union-attr]


OLD = ".reddit.com\tTRUE\t/\tTRUE\t4102444700\treddit_session\tOLDVALUE\n"


async def test_renewed_cookies_saved_after_success(env: Env) -> None:
    cid, src, _ = await _cookie_source(env, OLD)
    sup = env.make(fw.renewing_worker)
    await sup.start()
    job = await sup.enqueue(src, None, "info")
    await wait_for(env, job.id, JobStatus.succeeded)
    await wait_until(lambda: not sup.running)
    assert "NEWVALUE" in await _secret(env, cid)
    async with env.sf() as s:
        evs = (await s.execute(select(Job).where(Job.id == job.id))).scalars().all()
        assert "NEWVALUE" not in repr([(e.error, e.counters) for e in evs])


async def test_renewed_cookies_skipped_when_secret_changed(env: Env) -> None:
    cid, src, old_enc = await _cookie_source(env, OLD)
    sup = env.make(fw.fast_worker)
    h = RunHandle(1, src, None, credential_id=cid, secret_enc=old_enc)
    async with env.sf() as s:
        (await s.get(Credential, cid)).secret_enc = SecretBox(KEY).encrypt(b"pasted")  # type: ignore[union-attr]
        await s.commit()
    await sup._save_cookies(1, h, JAR)
    assert await _secret(env, cid) == "pasted"
    h.secret_enc = await _enc(env, cid)
    await sup._save_cookies(1, h, JAR)
    assert await _secret(env, cid) == JAR


async def test_prepare_skips_saveback_when_secret_differs(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.runtime.supervisor as sup_mod

    cid, src, _ = await _cookie_source(env, OLD)
    real = sup_mod.build_snapshots

    async def fake(s: Any, source: Any, box: Any) -> Any:
        a, b, c = await real(s, source, box)
        return a, b, c.model_copy(update={"secret": SecretStr("other")})

    monkeypatch.setattr(sup_mod, "build_snapshots", fake)
    sup = env.make(fw.fast_worker)
    h = RunHandle(1, src, None)
    job = await sup.enqueue(src, None, "info")
    await sup._prepare(job.id, h)
    assert h.credential_id is None and h.secret_enc is None


async def _enc(env: Env, cid: int) -> bytes:
    async with env.sf() as s:
        return (await s.get(Credential, cid)).secret_enc  # type: ignore[union-attr, no-any-return]


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


async def test_same_target_runs_concurrently_and_concurrency_cap(env: Env) -> None:
    t1, a = await env.seed()
    _, b = await env.seed(target=t1)
    _, c = await env.seed()
    _, d = await env.seed()
    async with env.sf() as s:
        s.add(Setting(key="runtime", value={"max_concurrent_jobs": 3}))
        await s.commit()
    sup = env.make(fw.slow_worker)
    await sup.start()
    ja = await sup.enqueue(a, None, "info")
    jb = await sup.enqueue(b, None, "info")  # same target as a: runs together
    jc = await sup.enqueue(c, None, "info")
    jd = await sup.enqueue(d, None, "info")  # cap=3: must wait
    for j in (ja, jb, jc):
        await wait_for(env, j.id, JobStatus.running)
    await asyncio.sleep(0.5)
    assert set(sup.running) == {ja.id, jb.id, jc.id}
    async with env.sf() as s:
        assert (await s.get(Job, jd.id)).status == JobStatus.queued  # type: ignore[union-attr]
    await sup.cancel(ja.id)  # frees a slot
    await wait_for(env, ja.id, JobStatus.cancelled)
    await wait_for(env, jd.id, JobStatus.running)
    for j in (jb, jc, jd):
        await sup.cancel(j.id)


async def test_max_jobs_per_target_cap(env: Env) -> None:
    t1, a = await env.seed()
    _, b = await env.seed(target=t1)
    _, c = await env.seed(target=t1)
    _, d = await env.seed()
    async with env.sf() as s:
        s.add(Setting(key="runtime", value={"max_jobs_per_target": 2}))
        await s.commit()
    sup = env.make(fw.slow_worker)
    await sup.start()
    ja, jb, jc, jd = [await sup.enqueue(x, None, "info") for x in (a, b, c, d)]
    for j in (ja, jb, jd):
        await wait_for(env, j.id, JobStatus.running)
    await asyncio.sleep(0.5)
    assert set(sup.running) == {ja.id, jb.id, jd.id}  # c waits behind its target's cap
    await sup.cancel(ja.id)
    await wait_for(env, jc.id, JobStatus.running)
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
    # `running` is cleared after the status is committed: wait for it, don't assume
    await wait_until(lambda: sup.running == {})


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


async def _until_exited(sup: JobSupervisor, job_id: int) -> Any:
    for _ in range(600):
        h = sup.running.get(job_id)
        if h is not None and h.exitcode is not None:
            return h
        await asyncio.sleep(0.05)
    raise AssertionError("worker never exited")


async def test_stop_while_waiting_for_done_after_clean_exit(env: Env) -> None:
    _, src = await env.seed()
    sup = env.make(fw.silent_exit_worker)
    sup.stop_join_s = 0.2
    await sup.start()
    job = await sup.enqueue(src, None, "info")
    h = await _until_exited(sup, job.id)
    assert h.exitcode == 0 and h.process is None
    await sup.stop()
    assert not (env.scratch / str(job.id)).exists()


async def test_cancel_during_await_done_logs_no_error(
    env: Env, caplog: pytest.LogCaptureFixture
) -> None:
    _, src = await env.seed()
    sup = env.make(fw.silent_after_cancel_worker)
    sup.stop_join_s = 0.2
    await sup.start()
    job = await sup.enqueue(src, None, "info")
    marker = env.scratch / str(job.id) / "f"
    for _ in range(400):
        if marker.exists():
            break
        await asyncio.sleep(0.05)
    with caplog.at_level("ERROR"):
        await sup.cancel(job.id)
        await _until_exited(sup, job.id)
        await asyncio.sleep(0.6)  # past the escalation grace
        await sup.stop()
    assert [r for r in caplog.records if r.levelname == "ERROR"] == []


async def test_escalation_after_sigterm_exit_raises_nothing(
    env: Env, caplog: pytest.LogCaptureFixture
) -> None:
    _, src = await env.seed()
    sup = env.make(fw.hang_worker)
    await sup.start()
    job = await sup.enqueue(src, None, "info")
    marker = env.scratch / str(job.id) / "f"
    for _ in range(400):
        if marker.exists():
            break
        await asyncio.sleep(0.05)
    h = sup.running[job.id]
    with caplog.at_level("ERROR"):
        await sup.cancel(job.id)
        esc = h.escalation
        assert esc is not None
        (res,) = await asyncio.gather(esc, return_exceptions=True)
        await wait_for(env, job.id, JobStatus.cancelled)
    assert res is None
    assert [r for r in caplog.records if r.levelname == "ERROR"] == []


async def test_global_notify_sent_after_final_status(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    import apprise

    from app.db.models import Setting

    calls: list[str] = []
    monkeypatch.setattr(
        apprise.plugins.NotifyBase,
        "notify",
        lambda self, body="", title="", **k: calls.append(title) or True,
    )
    async with env.sf() as s:
        s.add(Setting(key="notify", value={"urls": ["json://localhost/"], "on": ["success"]}))
        await s.commit()
    _, src = await env.seed()
    sup = env.make(fw.fast_worker)
    await sup.start()
    job = await sup.enqueue(src, None, "info")
    await wait_for(env, job.id, JobStatus.succeeded)
    for _ in range(100):
        if calls:
            break
        await asyncio.sleep(0.05)
    assert calls == ["immich-hoarder: s succeeded"]


async def _src_cred_env(
    env: Env, url: str, monkeypatch: pytest.MonkeyPatch
) -> tuple[int, list[str]]:
    import apprise

    from app.db.models import Credential, CredentialKind

    calls: list[str] = []
    monkeypatch.setattr(
        apprise.plugins.NotifyBase,
        "notify",
        lambda self, body="", title="", **k: calls.append(title) or True,
    )
    _, src = await env.seed()
    async with env.sf() as s:
        c = Credential(
            owner_id=env.owner_id,
            name="n",
            site="n",
            kind=CredentialKind.apprise,
            secret_enc=SecretBox(KEY).encrypt(url.encode()),
        )
        s.add(c)
        await s.flush()
        row = await s.get(Source, src)
        assert row is not None
        row.notify = {"credential_ids": [c.id], "on": ["success"]}
        await s.commit()
    return src, calls


async def test_source_credential_url_notifies(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    src, calls = await _src_cred_env(env, "json://example.com/", monkeypatch)
    sup = env.make(fw.fast_worker)
    await sup.start()
    job = await sup.enqueue(src, None, "info")
    await wait_for(env, job.id, JobStatus.succeeded)
    for _ in range(100):
        if calls:
            break
        await asyncio.sleep(0.05)
    assert calls == ["immich-hoarder: s succeeded"]


async def test_private_source_credential_url_skipped(
    env: Env, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    src, calls = await _src_cred_env(env, "json://10.9.8.7/secretpath", monkeypatch)
    sup = env.make(fw.fast_worker)
    await sup.start()
    job = await sup.enqueue(src, None, "info")
    await wait_for(env, job.id, JobStatus.succeeded)
    for _ in range(100):
        if "skipped" in caplog.text:
            break
        await asyncio.sleep(0.05)
    assert calls == []
    assert "skipped" in caplog.text
    assert "10.9.8.7" not in caplog.text and "secretpath" not in caplog.text


async def test_worker_stuck_in_download_hook_killed_after_grace(env: Env) -> None:
    _, src = await env.seed()
    sup = env.make(fw.stuck_download_worker)
    sup.grace_override_s = 0.3
    await sup.start()
    job = await sup.enqueue(src, None, "info")
    marker = env.scratch / str(job.id) / "f"
    await wait_until(marker.exists)
    h = sup.running[job.id]
    t0 = asyncio.get_running_loop().time()
    await sup.cancel(job.id)
    await wait_for(env, job.id, JobStatus.cancelled)
    assert asyncio.get_running_loop().time() - t0 >= 0.3  # not before the grace period
    assert h.exitcode == -9  # the hook ignores cancel and SIGTERM: only kill() ends it
    assert not (env.scratch / str(job.id)).exists()


async def test_stop_finalizes_stuck_job_as_interrupted_with_metrics(env: Env) -> None:
    from app.runtime.metrics import Metrics

    m = Metrics()
    m.attach(env.writer)
    _, src = await env.seed()
    sup = env.make(fw.stuck_download_worker)
    sup.grace_override_s = 0.2
    sup.kill_delay_s = 0.2
    sup.stop_join_s = 0.3
    await sup.start()
    job = await sup.enqueue(src, None, "info")
    await wait_until((env.scratch / str(job.id) / "f").exists)
    h = sup.running[job.id]
    await sup.stop()
    assert h.escalation is None or h.escalation.done()
    done = await wait_for(env, job.id, JobStatus.failed)
    assert done.error == "interrupted by restart"
    assert m.jobs_total.labels("failed")._value.get() == 1


async def test_startup_recovery_counted_in_metrics(env: Env) -> None:
    from app.runtime.metrics import Metrics

    m = Metrics()
    m.attach(env.writer)
    _, s1 = await env.seed()
    async with env.sf() as s:
        r = Job(source_id=s1, status=JobStatus.running)
        s.add(r)
        await s.commit()
    sup = env.make(fw.fast_worker)
    await sup.start()
    assert m.jobs_total.labels("failed")._value.get() == 1


async def test_cooperative_cancel_on_stop_ends_failed_but_user_cancel_stays_cancelled(
    env: Env,
) -> None:
    _, s1 = await env.seed()
    _, s2 = await env.seed()
    sup = env.make(fw.slow_worker)
    await sup.start()
    j1 = await sup.enqueue(s1, None, "info")
    await wait_until(lambda: (env.scratch / str(j1.id) / "f").exists())
    await sup.cancel(j1.id)
    await wait_for(env, j1.id, JobStatus.cancelled)
    j2 = await sup.enqueue(s2, None, "info")
    await wait_until(lambda: (env.scratch / str(j2.id) / "f").exists())
    await sup.stop()
    done = await wait_for(env, j2.id, JobStatus.failed)
    assert done.error == "interrupted by restart"


SHA = b"\x07" * 20


async def _marker(env: Env, job_id: int, name: str, timeout: float = 20) -> Path:
    p = env.scratch / str(job_id) / name
    await wait_until(p.exists, timeout)
    return p


async def test_claim_freed_by_committed_release_message(env: Env) -> None:
    t, a = await env.seed()
    _, b = await env.seed(target=t)
    sup = env.make(fw.claim_release_worker)
    await sup.start()
    ja = await sup.enqueue(a, None, "info")
    await _marker(env, ja.id, "released")  # A recorded, released and is still running
    jb = await sup.enqueue(b, None, "info")
    await _marker(env, jb.id, "got")  # B's claim on the same content was granted
    async with env.sf() as s:
        rows = (await s.execute(select(AssetSeen))).scalars().all()
    assert len(rows) >= 1
    for j in (ja, jb):
        await sup.cancel(j.id)


async def test_sigkilled_job_frees_its_claims_after_sweep(env: Env) -> None:
    t, a = await env.seed()
    _, b = await env.seed(target=t)
    sup = env.make(fw.claim_hold_worker)
    await sup.start()
    ja = await sup.enqueue(a, None, "info")
    pid_file = await _marker(env, ja.id, "held")
    jb = await sup.enqueue(b, None, "info")
    await wait_for(env, jb.id, JobStatus.running)
    await asyncio.sleep(0.6)
    assert not (env.scratch / str(jb.id) / "got").exists()  # blocked behind A's claim
    os.kill(int(pid_file.read_text()), signal.SIGKILL)
    await wait_for(env, ja.id, JobStatus.failed)
    await _marker(env, jb.id, "got")
    assert sup.claims.table.held(ja.id) == 0
    await sup.cancel(jb.id)


async def test_clean_exit_frees_claims_at_done(env: Env) -> None:
    t, a = await env.seed()
    _, b = await env.seed(target=t)
    sup = env.make(fw.claim_leak_worker)  # claims and exits without releasing
    await sup.start()
    ja = await sup.enqueue(a, None, "info")
    await wait_for(env, ja.id, JobStatus.succeeded)
    jb = await sup.enqueue(b, None, "info")
    await wait_for(env, jb.id, JobStatus.succeeded)
    assert sup.claims.table.held() == 0


# -- real worker processes against a mock Immich ------------------------------------------


class _Site:
    """Serves two re-encodings of one picture and the slice of the Immich API the rip uses."""

    def __init__(self, upload_delay: float) -> None:
        import io
        import json
        import threading
        import time
        import uuid
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        from PIL import Image

        img = Image.effect_noise((128, 96), 80).convert("RGB")
        self.imgs: dict[str, bytes] = {}
        for name, q in (("a", 92), ("b", 60)):
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=q)
            self.imgs[name] = buf.getvalue()
        self.uploads: list[str] = []
        self.linked: list[str] = []
        lock = threading.Lock()
        site = self

        class H(BaseHTTPRequestHandler):
            def _send(self, code: int, body: Any) -> None:
                raw = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(raw)

            def _body(self) -> bytes:
                return self.rfile.read(int(self.headers.get("Content-Length") or 0))

            def do_GET(self) -> None:
                if self.path.startswith("/img/"):
                    self._send(200, site.imgs[self.path[5:6]])
                elif self.path.endswith("/albums"):
                    self._send(200, [])
                else:
                    self._send(404, {})

            def do_POST(self) -> None:
                body = self._body()
                if self.path.endswith("/bulk-upload-check"):
                    items = json.loads(body)["assets"]
                    res = [{"id": i["id"], "action": "accept"} for i in items]
                    self._send(200, {"results": res})
                elif self.path.endswith("/albums"):
                    self._send(201, {"id": str(uuid.uuid4()), "albumName": "x", "assetCount": 0})
                elif self.path.endswith("/assets"):
                    time.sleep(upload_delay)
                    aid = str(uuid.uuid4())
                    with lock:
                        site.uploads.append(aid)
                    self._send(201, {"id": aid, "status": "created"})
                else:
                    self._send(404, {})

            def do_PUT(self) -> None:
                body = self._body()
                if "/albums/" in self.path:
                    ids = json.loads(body)["ids"]
                    with lock:
                        site.linked.extend(ids)
                    self._send(200, [{"id": i, "success": True} for i in ids])
                else:
                    self._send(200, {})

            def log_message(self, *a: object) -> None:
                pass

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.thread = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def close(self) -> None:
        self.srv.shutdown()
        self.srv.server_close()


async def test_two_real_workers_dedupe_near_duplicates_on_one_target(env: Env) -> None:

    site = await asyncio.to_thread(_Site, 1.0)
    try:
        box = SecretBox(KEY)
        async with env.sf() as s:
            s.add(
                Setting(
                    key="rip",
                    value={
                        "allow_private_hosts": True,
                        "rate_limits": {"default": {"sleep_request": 0, "sleep": 0, "retries": 0}},
                    },
                )
            )
            t = ImmichTarget(
                owner_id=env.owner_id,
                name="real",
                url=site.base,
                api_key_enc=box.encrypt(b"k"),
            )
            s.add(t)
            await s.flush()
            srcs = []
            for name in ("a", "b"):  # same picture, different bytes (and so SHA-1)
                src = Source(
                    owner_id=env.owner_id,
                    name=name,
                    url=f"{site.base}/img/{name}.jpg",
                    extractor="directlink",
                    target_id=t.id,
                )
                s.add(src)
                srcs.append(src)
            await s.commit()
            ids = [x.id for x in srcs]
        sup = env.make(worker_main)  # real worker processes
        sup.done_wait_s = 10
        await sup.start()
        jobs = [await sup.enqueue(i, None, "info") for i in ids]
        done = [await wait_for(env, j.id, JobStatus.succeeded, timeout=90) for j in jobs]
        counters = [d.counters for d in done]
        assert sum(c["uploaded"] for c in counters) == 1, counters
        assert sum(c["linked"] for c in counters) == 1, counters
        assert len(site.uploads) == 1
        assert sup.claims.table.held() == 0 and sup.claims.table.waiting() == 0
    finally:
        await asyncio.to_thread(site.close)
