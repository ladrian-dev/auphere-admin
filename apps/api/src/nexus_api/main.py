from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from nexus_api import __version__
from nexus_api.api import admin, embed, partners, qa, webhooks
from nexus_api.api import connectors as connectors_public
from nexus_api.config import settings
from nexus_api.core import isolation_enforcer, otel
from nexus_api.core.logging_context import LoggingContextMiddleware
from nexus_api.core.metrics import isolation_event_drainer
from nexus_api.core.qa_checkpointer import close_qa_checkpointer, init_qa_checkpointer
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

    # Block H: drainer that persists ``isolation.*`` events to the
    # ``isolation_events`` table. Best-effort; shutdown signals it to
    # finish the in-flight batch and exits within ``poll_seconds``.
    drainer_stop = asyncio.Event()
    drainer_task = asyncio.create_task(
        isolation_event_drainer(drainer_stop), name="isolation-event-drainer"
    )

    # ADR-021 Fase 1: open the QA Playground's LangGraph checkpointer
    # pool and run setup() once. The checkpointer is shared across all
    # qa.* turns and persists state in the ``langgraph`` schema
    # (migration 0029). If setup() fails we log and continue so the
    # rest of the API stays up — qa endpoints will surface the error
    # on the first call instead of crashing the whole API.
    try:
        await init_qa_checkpointer()
    except Exception:
        log.exception("qa.checkpointer.init_failed")

    log.info("api.startup", env=settings.environment, version=__version__)
    try:
        yield
    finally:
        log.info("api.shutdown")
        drainer_stop.set()
        try:
            await asyncio.wait_for(drainer_task, timeout=3.0)
        except (TimeoutError, asyncio.CancelledError):
            drainer_task.cancel()
        await close_qa_checkpointer()
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
# ADR-028: the iframe app is the ONLY browser consumer of this API —
# CORS allows exactly that origin. Everything else is server-to-server
# (admin token / partner secret key) and needs no CORS at all.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.embed_app_origin],
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,
)
app.include_router(health_router)
app.include_router(admin.router)
app.include_router(webhooks.router)
app.include_router(connectors_public.router)
app.include_router(qa.router)
# ADR-028: public partner surface (secret API key, server-to-server)
# + browser-facing embed surface (widget session JWT).
app.include_router(partners.router)
app.include_router(embed.router)
