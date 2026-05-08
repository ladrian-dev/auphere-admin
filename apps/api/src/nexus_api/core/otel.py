"""OpenTelemetry instrumentation. Auto-instruments FastAPI + SQLAlchemy + Redis.

No exporter is configured here — that's wired in block H. The instrumentation
runs locally to attach span attributes (tenant_id, channel_id) so once the
exporter ships we have the data. Tests can read attributes off the in-memory
processor.
"""

from __future__ import annotations

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from sqlalchemy.ext.asyncio import AsyncEngine

_provider: TracerProvider | None = None
_installed_apps: set[int] = set()
_installed_engines: set[int] = set()
_redis_installed = False


def install(app: FastAPI, engine: AsyncEngine) -> None:
    global _provider, _redis_installed
    if _provider is None:
        _provider = TracerProvider()
        trace.set_tracer_provider(_provider)
    if id(app) not in _installed_apps:
        FastAPIInstrumentor.instrument_app(app)
        _installed_apps.add(id(app))
    if id(engine) not in _installed_engines:
        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
        _installed_engines.add(id(engine))
    if not _redis_installed:
        RedisInstrumentor().instrument()
        _redis_installed = True


def get_current_trace_id() -> str | None:
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx.trace_id == 0:
        return None
    return f"{ctx.trace_id:032x}"
