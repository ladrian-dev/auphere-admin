from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from nexus_api import __version__
from nexus_api.config import settings
from nexus_api.health import router as health_router
from nexus_api.logging import configure_logging

configure_logging()
log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("api.startup", env=settings.environment, version=__version__)
    yield
    log.info("api.shutdown")


app = FastAPI(
    title="Nexus API",
    version=__version__,
    description="Auphere agent factory backend",
    lifespan=lifespan,
    docs_url="/docs" if settings.environment == "dev" else None,
    redoc_url=None,
)

app.include_router(health_router)
