"""OpenTelemetry instrumentation. Auto-instruments FastAPI + SQLAlchemy + Redis.

WP-01 (plataforma v2, Fase 0): the provider now carries a proper ``Resource``
(service.name / service.version / deployment.environment) and — when
``NEXUS_OTEL_ENABLED=true`` and ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set — a
``BatchSpanProcessor`` shipping spans over OTLP/HTTP. Endpoint, headers and
sampler are read from the standard ``OTEL_*`` env vars by the SDK itself, so
operators configure Grafana Cloud without touching code.

Trace context crosses the Redis Stream boundary via ``inject_trace_fields``:
webhooks stamp ``traceparent`` into the ``XADD`` fields and the worker's
consumer extracts it, so one WhatsApp message is one trace end-to-end
(webhook → queue → runner → LLM → egress).
"""

from __future__ import annotations

import structlog
from fastapi import FastAPI
from opentelemetry import propagate, trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from sqlalchemy.ext.asyncio import AsyncEngine

log = structlog.get_logger(__name__)

_provider: TracerProvider | None = None
_installed_apps: set[int] = set()
_installed_engines: set[int] = set()
_redis_installed = False


def build_resource(service_name: str) -> Resource:
    """Resource shared by API and worker processes. ``service.version`` is
    the package version (the deploy pipeline bakes the commit SHA into it);
    ``deployment.environment`` distinguishes prod/staging/dev in Grafana."""
    from nexus_api import __version__
    from nexus_api.config import settings

    return Resource.create(
        {
            "service.name": service_name,
            "service.version": __version__,
            "deployment.environment": settings.environment,
        }
    )


def _maybe_attach_otlp_exporter(provider: TracerProvider) -> None:
    """Attach the OTLP/HTTP batch exporter when the operator enabled it.

    Deliberately quiet-by-default: with ``NEXUS_OTEL_ENABLED=false`` (the
    default everywhere today) the provider still exists so span attributes
    keep flowing to tests via in-memory processors, but nothing leaves the
    process. Misconfiguration (enabled without an endpoint) logs a warning
    instead of pointing the exporter at localhost and failing silently.
    """
    import os

    from nexus_api.config import settings

    if not settings.otel_enabled:
        return
    if not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        log.warning(
            "otel.enabled_without_endpoint",
            hint="set OTEL_EXPORTER_OTLP_ENDPOINT or flip NEXUS_OTEL_ENABLED off",
        )
        return
    # Imported lazily so environments without the exporter wheel (and every
    # test run) never pay for it.
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    log.info("otel.otlp_exporter_attached")


def build_provider(service_name: str) -> TracerProvider:
    """Provider with Resource + (optional) OTLP exporter. The sampler is the
    SDK default, which honours ``OTEL_TRACES_SAMPLER`` /
    ``OTEL_TRACES_SAMPLER_ARG`` from the environment."""
    provider = TracerProvider(resource=build_resource(service_name))
    _maybe_attach_otlp_exporter(provider)
    return provider


def install(app: FastAPI, engine: AsyncEngine) -> None:
    global _provider, _redis_installed
    if _provider is None:
        _provider = build_provider("nexus-api")
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


def inject_trace_fields(fields: dict[str, str]) -> dict[str, str]:
    """Stamp the current trace context (``traceparent`` + optional
    ``tracestate``) into a Redis Stream entry's fields, in place.

    No-op when there is no active recording span — fields stay clean and the
    consumer simply starts a fresh trace.
    """
    propagate.inject(fields)
    return fields


def get_current_trace_id() -> str | None:
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx.trace_id == 0:
        return None
    return f"{ctx.trace_id:032x}"
