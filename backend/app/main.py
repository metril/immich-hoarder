import asyncio
import multiprocessing
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import async_sessionmaker
from starlette.middleware.sessions import SessionMiddleware

from app import __version__
from app.api.v1 import api_router
from app.api.v1 import auth as auth_api
from app.auth.oidc import BearerVerifier, build_oauth
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.engine import dispose_engine, init_engine
from app.db.migrate import upgrade_head_async
from app.runtime.bus import EventBus
from app.runtime.scheduler import SourceScheduler
from app.runtime.supervisor import JobSupervisor
from app.runtime.writer import IpcBridge, JobWriter, make_ipc_queue


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
                writer.start()
                bridge = IpcBridge(ipc_q, writer, asyncio.get_running_loop())
                bridge.start()
                supervisor = JobSupervisor(sf, writer, settings, mp_ctx=ctx, ipc_queue=ipc_q)
                await supervisor.start()
                scheduler = SourceScheduler(supervisor, sf)
                await scheduler.start()
                _app.state.scheduler = scheduler
                _app.state.bus = bus
                _app.state.job_writer = writer
                _app.state.supervisor = supervisor
            yield
        finally:
            if scheduler is not None:
                scheduler.shutdown(wait=False)
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
    app.state.runtime_enabled = True
    app.state.immich_transport = None
    app.state.oauth = build_oauth(settings)
    app.state.verifier = BearerVerifier(settings)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret.get_secret_value(),
        max_age=8 * 3600,
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

    return app
