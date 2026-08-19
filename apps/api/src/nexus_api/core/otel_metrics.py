"""OTel metrics — the SLIs of Fase 0 (WP-05, plataforma v2).

One module owns every instrument so the metric names, units and label sets
live in exactly one place. Recording helpers are cheap no-ops until
``install_metrics`` runs (the SDK hands out noop instruments), and recording
NEVER raises — instrumentation must not break a turn or a webhook ack.

Instruments (labels):
- ``turn_latency_ms``        histogram (tenant, intent, channel)
- ``turn_errors_total``      counter   (tenant, stage)
- ``queue_lag_entries``      obs. gauge (stream)
- ``queue_oldest_pending_seconds`` obs. gauge (stream)
- ``outbound_pending_messages``    obs. gauge (sin labels)
- ``outbound_oldest_pending_seconds`` obs. gauge (sin labels)
- ``llm_call_ms``            histogram (model, role)
- ``llm_tokens_total``       counter   (type=input|output|cache_read|cache_write, model)
- ``webhook_ack_ms``         histogram (provider)
- ``outbound_delivery_ms``   histogram (provider)
- ``meta_send_failures_total`` counter (code)

``llm_cache_read_ratio`` is deliberately NOT an instrument: it is derived in
the dashboard as ``cache_read / (input + cache_read)`` over
``llm_tokens_total`` — deriving it at query time keeps the raw counters
usable for cost math too.
"""

from __future__ import annotations

import contextlib
import threading
from typing import Any

import structlog
from opentelemetry import metrics as otel_metrics_api

log = structlog.get_logger(__name__)

_lock = threading.Lock()
_installed = False
_provider: Any | None = None
_instruments: dict[str, Any] = {}

# Latest backlog measurements per stream, read by the observable-gauge
# callbacks (OTel callbacks are sync; the claimer updates these async).
_queue_lag: dict[str, tuple[int, float]] = {}


def set_queue_lag(stream: str, *, entries: int, oldest_pending_s: float) -> None:
    """Called by the stream claimer on every tick (WP-04 hook)."""
    _queue_lag[stream] = (entries, oldest_pending_s)


def _lag_entries_callback(_options: Any) -> list[Any]:
    from opentelemetry.metrics import Observation

    return [
        Observation(entries, {"stream": stream})
        for stream, (entries, _oldest) in _queue_lag.items()
    ]


def _lag_oldest_callback(_options: Any) -> list[Any]:
    from opentelemetry.metrics import Observation

    return [
        Observation(oldest, {"stream": stream}) for stream, (_entries, oldest) in _queue_lag.items()
    ]


# Profundidad de la cola de SALIDA (``messages`` pending outbound), medida
# por el sweep del dispatcher de egress. Es una cuenta GLOBAL, no por
# tenant: es la señal de autoescalado del servicio egress (WP-24) y el
# número por tenant ni escala ni cabe como dimensión de CloudWatch.
#
# ``None`` = todavía no se ha medido nada en este proceso; el callback no
# emite observación, que es distinto de emitir un 0. Un 0 falso al arrancar
# le diría al autoescalado "no hay trabajo" antes de mirar la base.
_outbound_backlog: tuple[int, float] | None = None


def set_outbound_backlog(*, pending: int, oldest_pending_s: float) -> None:
    """Called by the outbound dispatcher on every sweep (WP-24 hook)."""
    global _outbound_backlog
    _outbound_backlog = (pending, oldest_pending_s)


def _outbound_pending_callback(_options: Any) -> list[Any]:
    from opentelemetry.metrics import Observation

    if _outbound_backlog is None:
        return []
    return [Observation(_outbound_backlog[0])]


def _outbound_oldest_callback(_options: Any) -> list[Any]:
    from opentelemetry.metrics import Observation

    if _outbound_backlog is None:
        return []
    return [Observation(_outbound_backlog[1])]


def install_metrics(service_name: str, *, extra_reader: Any | None = None) -> None:
    """Install the global MeterProvider. Exports over OTLP/HTTP when
    ``NEXUS_OTEL_ENABLED`` + ``OTEL_EXPORTER_OTLP_ENDPOINT`` are set (same
    contract as tracing); otherwise instruments exist but nothing leaves the
    process. ``extra_reader`` is for tests (InMemoryMetricReader)."""
    global _installed
    import os

    from opentelemetry.sdk.metrics import MeterProvider

    from nexus_api.config import settings
    from nexus_api.core.otel import build_resource

    with _lock:
        if _installed:
            return
        readers = []
        if extra_reader is not None:
            readers.append(extra_reader)
        if settings.otel_enabled and os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
                OTLPMetricExporter,
            )
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

            readers.append(PeriodicExportingMetricReader(OTLPMetricExporter()))
        global _provider
        _provider = MeterProvider(resource=build_resource(service_name), metric_readers=readers)
        # Best-effort global registration; the SDK only honours the FIRST
        # call per process, which is why ``_meter`` below resolves through
        # the module's own reference instead of the global API — reinstalls
        # (tests, dev all-in-one process) keep working.
        with contextlib.suppress(Exception):
            otel_metrics_api.set_meter_provider(_provider)
        _installed = True
        _instruments.clear()
        log.info("otel.metrics_installed", service=service_name, exporters=len(readers))


def _meter() -> Any:
    if _provider is not None:
        return _provider.get_meter("nexus")
    return otel_metrics_api.get_meter("nexus")


def _instrument(name: str, kind: str, *, unit: str = "", description: str = "") -> Any:
    inst = _instruments.get(name)
    if inst is not None:
        return inst
    meter = _meter()
    if kind == "histogram":
        inst = meter.create_histogram(name, unit=unit, description=description)
    elif kind == "counter":
        inst = meter.create_counter(name, unit=unit, description=description)
    else:  # pragma: no cover - guarded by callers
        raise ValueError(kind)
    _instruments[name] = inst
    return inst


def ensure_queue_gauges() -> None:
    """Register the queue-lag observable gauges (idempotent)."""
    if "queue_lag_entries" in _instruments:
        return
    meter = _meter()
    _instruments["queue_lag_entries"] = meter.create_observable_gauge(
        "queue_lag_entries",
        callbacks=[_lag_entries_callback],
        description="Pending entries (PEL) per stream consumer group",
    )
    _instruments["queue_oldest_pending_seconds"] = meter.create_observable_gauge(
        "queue_oldest_pending_seconds",
        callbacks=[_lag_oldest_callback],
        unit="s",
        description="Age of the oldest pending entry per stream",
    )


def ensure_outbound_gauges() -> None:
    """Register the outbound-backlog observable gauges (idempotent).

    Deliberately SIN labels: la política de autoescalado de egress
    (``20-services/autoscaling.tf``) declara la métrica sin dimensiones, y
    el collector ADOT corre con ``NoDimensionRollup`` — un atributo aquí
    crearía una serie que la política nunca encontraría. Cada réplica de
    egress publica la misma cuenta global, por eso la política agrega con
    ``Maximum``.
    """
    if "outbound_pending_messages" in _instruments:
        return
    meter = _meter()
    _instruments["outbound_pending_messages"] = meter.create_observable_gauge(
        "outbound_pending_messages",
        callbacks=[_outbound_pending_callback],
        description="Outbound messages waiting to be sent, across all tenants",
    )
    _instruments["outbound_oldest_pending_seconds"] = meter.create_observable_gauge(
        "outbound_oldest_pending_seconds",
        callbacks=[_outbound_oldest_callback],
        unit="s",
        description="Age of the oldest outbound message still pending",
    )


def record_turn(*, duration_ms: float, tenant_id: str, intent: str | None, channel: str) -> None:
    with contextlib.suppress(Exception):
        _instrument("turn_latency_ms", "histogram", unit="ms").record(
            duration_ms,
            {"tenant": tenant_id, "intent": intent or "unknown", "channel": channel},
        )


def record_turn_error(*, tenant_id: str, stage: str) -> None:
    with contextlib.suppress(Exception):
        _instrument("turn_errors_total", "counter").add(1, {"tenant": tenant_id, "stage": stage})


def record_llm_call(*, model: str, role: str, duration_ms: float, usage: dict[str, int]) -> None:
    with contextlib.suppress(Exception):
        _instrument("llm_call_ms", "histogram", unit="ms").record(
            duration_ms, {"model": model, "role": role}
        )
        tokens = _instrument("llm_tokens_total", "counter")
        for usage_key, label in (
            ("prompt_tokens", "input"),
            ("completion_tokens", "output"),
            ("cache_read_input_tokens", "cache_read"),
            ("cache_creation_input_tokens", "cache_write"),
        ):
            value = usage.get(usage_key)
            if value:
                tokens.add(value, {"type": label, "model": model})


def record_webhook_ack(*, provider: str, duration_ms: float) -> None:
    with contextlib.suppress(Exception):
        _instrument("webhook_ack_ms", "histogram", unit="ms").record(
            duration_ms, {"provider": provider}
        )


def record_outbound_delivery(*, provider: str, duration_ms: float) -> None:
    with contextlib.suppress(Exception):
        _instrument("outbound_delivery_ms", "histogram", unit="ms").record(
            duration_ms, {"provider": provider}
        )


def record_meta_send_failure(*, code: str) -> None:
    with contextlib.suppress(Exception):
        _instrument("meta_send_failures_total", "counter").add(1, {"code": code})


# ── el Companion (CO-08, §11 de CONTRACT-V2 / §17 de la investigación) ──
#
# Los nombres los FIJA el contrato para que no se renombren a mitad del
# piloto y la serie se parta en dos. Son contadores crudos y las razones se
# derivan en la consulta, igual que ``llm_cache_read_ratio``: guardar el
# ratio perdería los numeradores, que sirven para otras preguntas.
#
# **Sin etiquetas, a propósito.** Ni partner, ni rol, ni ``kind``. La
# campaña de carga WP-15 dejó la lección escrita: una dimensión de más en
# CloudWatch parte la serie y deja ciega la alarma que la usaba. El corte
# por partner sale de ``scripts/companion_pilot_metrics.py``, que es donde
# tiene sentido mirarlo — una vez, al cerrar el piloto.
#
# La razón que MANDA es cancelled/proposed, con objetivo < 15 %: un
# Companion que propone cosas que la gente cancela es peor que no tener
# Companion, porque enseña a desconfiar.

COMPANION_COUNTERS: tuple[str, ...] = (
    "companion.thread.opened",
    "companion.task.completed",
    "companion.hitl.proposed",
    "companion.hitl.cancelled",
    "companion.turn.total",
    "companion.turn.unsupported",
    "companion.verify.total",
    "companion.verify.failed",
)


def record_companion(name: str, *, value: int = 1) -> None:
    """Suma uno a un contador del Companion. Nunca lanza.

    ``name`` tiene que estar en :data:`COMPANION_COUNTERS`: un nombre suelto
    crearía una serie que ningún panel busca, y el fallo sería silencioso.
    Aquí se registra y se sigue — la instrumentación no tumba un turno.
    """
    if name not in COMPANION_COUNTERS:  # pragma: no cover - error de programación
        log.warning("otel.companion_counter_unknown", counter=name)
        return
    with contextlib.suppress(Exception):
        _instrument(name, "counter").add(value)


def record_rate_limit_rejection(*, surface: str, degraded: bool) -> None:
    """Una petición de partner rechazada por el limitador.

    ``degraded`` distingue el rechazo normal (el partner se pasó de su
    límite) del rechazo con Redis caído, que se atiende con el cubo en
    memoria por réplica. Son la misma métrica con dimensión distinta
    porque el operador quiere ver los dos en el mismo panel: un pico de
    rechazos degradados es una incidencia de infraestructura, no un
    partner portándose mal.
    """
    with contextlib.suppress(Exception):
        _instrument("partner_rate_limit_rejections_total", "counter").add(
            1, {"surface": surface, "degraded": str(degraded).lower()}
        )


def record_rate_limit_degraded(*, surface: str) -> None:
    """El limitador perdió Redis y está corriendo en memoria.

    Se cuenta APARTE de los rechazos: mientras Redis esté caído el
    límite efectivo es por réplica, así que el número real que se está
    aplicando ya no es el configurado. Esta es la señal que debe
    alarmar, y tiene que verse aunque no se rechace ni una petición.
    """
    with contextlib.suppress(Exception):
        _instrument("partner_rate_limit_degraded_total", "counter").add(1, {"surface": surface})


def reset_for_tests() -> None:
    global _installed, _provider, _outbound_backlog
    with _lock:
        _installed = False
        _provider = None
        _instruments.clear()
        _queue_lag.clear()
        _outbound_backlog = None
