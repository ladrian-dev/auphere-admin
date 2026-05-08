from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from nexus_api import __version__
from nexus_api.api import admin, webhooks
from nexus_api.config import settings
from nexus_api.core import isolation_enforcer, otel
from nexus_api.core.logging_context import LoggingContextMiddleware
from nexus_api.core.redis_client import close_redis
from nexus_api.db.base import dispose_engine, get_engine
from nexus_api.health import router as health_router
from nexus_api.logging import configure_logging

configure_logging()
log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine = get_engine()
    isolation_enforcer.install(engine)
    otel.install(app, engine)
    log.info("api.startup", env=settings.environment, version=__version__)
    try:
        yield
    finally:
        log.info("api.shutdown")
        await close_redis()
        await dispose_engine()


app = FastAPI(
    title="Nexus API",
    version=__version__,
    description="Auphere agent factory backend",
    lifespan=lifespan,
    docs_url="/docs" if settings.is_dev else None,
    redoc_url=None,
)

app.add_middleware(LoggingContextMiddleware)
app.include_router(health_router)
app.include_router(admin.router)
app.include_router(webhooks.router)
