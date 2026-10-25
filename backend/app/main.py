from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.engine import dispose_engine, init_engine
from app.db.migrate import upgrade_head_async


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await upgrade_head_async(settings.database_url)
        init_engine(settings.database_url)
        try:
            yield
        finally:
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

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app
