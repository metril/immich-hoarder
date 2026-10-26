import asyncio
import multiprocessing
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker
from starlette.middleware.sessions import SessionMiddleware

from app import __version__
from app.api.v1 import api_router
from app.api.v1 import auth as auth_api
from app.auth.authz import require_scope
from app.auth.csrf_cookie import CsrfCookieRenewal
from app.auth.deps import SESSION_MAX_AGE, current_principal
from app.auth.oidc import BearerVerifier, build_oauth
from app.auth.principal import Principal
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.engine import dispose_engine, init_engine, session_scope
from app.db.migrate import upgrade_head_async
from app.db.models import Job, JobStatus
from app.runtime.bus import EventBus
from app.runtime.metrics import Metrics
from app.runtime.scheduler import SourceScheduler
from app.runtime.supervisor import JobSupervisor
from app.runtime.writer import IpcBridge, JobWriter, make_ipc_queue
from app.web.spa import mount_spa


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await upgrade_head_async(settings.database_url)
        engine = init_engine(settings.database_url)
        writer: JobWriter | None = None
        bridge: IpcBridge | None = None
        supervisor: JobSupervisor | None = None
        scheduler: SourceScheduler | None = None
        try:
            if _app.state.runtime_enabled:
                sf = async_sessionmaker(engine, expire_on_commit=False)
                ctx = multiprocessing.get_context("spawn")
                ipc_q = make_ipc_queue(ctx)
                bus = EventBus()
                writer = JobWriter(sf, bus)
                _app.state.metrics.attach(writer)
                writer.start()
                bridge = IpcBridge(ipc_q, writer, asyncio.get_running_loop())
                bridge.start()
                supervisor = JobSupervisor(sf, writer, settings, mp_ctx=ctx, ipc_queue=ipc_q)
                await supervisor.start()
                scheduler = SourceScheduler(supervisor, sf, settings)
                await scheduler.start()
                _app.state.scheduler = scheduler
                _app.state.bus = bus
                _app.state.job_writer = writer
                _app.state.bridge = bridge
                _app.state.supervisor = supervisor
            yield
        finally:
            if scheduler is not None:
                await scheduler.stop()
                _app.state.scheduler = None
            if supervisor is not None:
                await supervisor.stop()
            if bridge is not None:
                await asyncio.to_thread(bridge.stop)
            if writer is not None:
                await writer.stop()
            await dispose_engine()

    app = FastAPI(
        lifespan=lifespan,
        title="immich-hoarder",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.metrics = Metrics()
    app.state.runtime_enabled = True
    app.state.immich_transport = None
    app.state.oauth = build_oauth(settings)
    app.state.verifier = BearerVerifier(settings)
    secure = settings.public_url.startswith("https")
    app.add_middleware(CsrfCookieRenewal, secure=secure)  # inside SessionMiddleware
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret.get_secret_value(),
        max_age=SESSION_MAX_AGE,
        same_site="lax",
        https_only=settings.public_url.startswith("https"),
    )
    app.include_router(auth_api.router)
    app.include_router(api_router)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_req: Request, exc: RequestValidationError) -> JSONResponse:
        # Same shape as FastAPI's default, minus input/ctx which can echo secrets.
        detail = [{k: v for k, v in e.items() if k not in ("input", "ctx")} for e in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": jsonable_encoder(detail)})

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    async def readyz() -> JSONResponse:
        failing: list[str] = []

        async def _db() -> None:
            async with session_scope() as s:
                await s.execute(text("SELECT 1"))

        try:
            await asyncio.wait_for(_db(), 2.0)
        except Exception:
            failing.append("db")
        sched = getattr(app.state, "scheduler", None)
        if sched is None or not sched.running:
            failing.append("scheduler")
        sup = getattr(app.state, "supervisor", None)
        if sup is None or not sup.alive:
            failing.append("supervisor")
        wr = getattr(app.state, "job_writer", None)
        if wr is None or not wr.alive:
            failing.append("writer")
        br = getattr(app.state, "bridge", None)
        if br is None or not br.alive:
            failing.append("bridge")
        if failing:
            return JSONResponse(
                status_code=503, content={"status": "unavailable", "failing": failing}
            )
        return JSONResponse({"status": "ok"})

    @app.get("/metrics", include_in_schema=False)
    async def metrics(p: Principal = Depends(current_principal)) -> Response:
        if p.scopes is None:
            if not p.is_admin:  # session/JWT users: admins only
                raise HTTPException(403, "forbidden")
        else:
            require_scope(p, "metrics:read")
        m: Metrics = app.state.metrics
        sup = getattr(app.state, "supervisor", None)
        m.jobs_running.set(len(sup.running) if sup is not None else 0)

        async def _queued() -> int:
            async with session_scope() as s:
                n = await s.scalar(
                    select(func.count()).select_from(Job).where(Job.status == JobStatus.queued)
                )
            return n or 0

        try:
            m.jobs_queued.set(await asyncio.wait_for(_queued(), 2.0))
        except Exception:
            pass  # keep the last value
        m.set_scratch(settings.scratch_dir)
        return Response(generate_latest(m.registry), media_type=CONTENT_TYPE_LATEST)

    mount_spa(app, settings.web_dir)
    return app
