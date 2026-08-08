from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from nexus_api import __version__
from nexus_api.api import admin, messages, partners, partners_clients, qa, webhooks
from nexus_api.api import connectors as connectors_public
from nexus_api.config import settings
from nexus_api.core import isolation_enforcer, otel, otel_metrics
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
    # WP-05: SLI instruments (exports only when NEXUS_OTEL_ENABLED + endpoint).
    otel_metrics.install_metrics("nexus-api")

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


@app.middleware("http")
async def _webhook_ack_timing(request, call_next):  # type: ignore[no-untyped-def]
    """WP-05: ``webhook_ack_ms`` — how long a provider waits for our 200.

    Meta retries (and eventually disables) webhooks that answer slowly, so
    this is the SLI that says whether the webhook stays on the happy path.
    Only measures ``/webhook/*`` to keep the hot path of every other route
    untouched.
    """
    if not request.url.path.startswith("/webhook/"):
        return await call_next(request)
    import time as _time

    started = _time.perf_counter()
    response = await call_next(request)
    provider = request.url.path.removeprefix("/webhook/").split("/")[0] or "unknown"
    otel_metrics.record_webhook_ack(
        provider=provider, duration_ms=(_time.perf_counter() - started) * 1000
    )
    return response
# No CORS layer on purpose: every surface of this API is
# server-to-server (admin token, partner secret key, tenant key or
# webhook signature). Nothing is called from a browser, so allowing an
# origin would only widen the attack surface.
app.include_router(health_router)
app.include_router(admin.router)
app.include_router(webhooks.router)
app.include_router(connectors_public.router)
app.include_router(qa.router)
# ADR-028: public partner surface (secret API key, server-to-server).
app.include_router(partners.router)
app.include_router(partners_clients.router)
# Direct outbound sends for tenant-scoped keys (n8n, cron, scripts).
app.include_router(messages.router)
