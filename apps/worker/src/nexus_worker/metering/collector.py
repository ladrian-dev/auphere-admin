"""Colector de consumo — emisión (WP-17, plataforma v2 Fase 2).

Cierra la mitad de B3: hoy los tokens del LLM **no se persisten en ninguna
tabla de producción**, así que no se puede cobrar por consumo ni ver dónde
se va el margen. ``usage_records`` (WP-16) es el destino; esto es lo que lo
llena.

Reparto de responsabilidades, a propósito:

- **aquí solo se cuentan CANTIDADES** (tokens, mensajes, minutos). El
  precio lo pone el consumidor (WP-18) leyendo ``model_profiles``, que es
  precio en base de datos y no en código. Un colector que además calculase
  costes obligaría a redesplegar el worker cada vez que un proveedor
  cambia su tarifa, y a reprocesar para corregir un precio mal puesto.
- **fuera del camino crítico**: los eventos se acumulan en un buffer por
  turno (``ContextVar``) y se publican de una vez en ``nexus:usage`` al
  cerrar el turno. Si Redis está caído se pierde la medición, nunca el
  turno.

**La instrumentación no puede romper un turno.** Todo lo público de este
módulo traga excepciones y las deja en un WARNING.

El volcado ocurre en un ``finally``: si el turno revienta a mitad, los
tokens ya se gastaron y hay que contarlos igual. Perder esa medición sería
regalar dinero justo en los turnos que peor van.

Idempotencia — el consumidor inserta con ``ON CONFLICT DO NOTHING`` sobre
``(idempotency_key, occurred_at)``:

- LLM: ``{turn_id}:{call_seq}:{meter}``. El ``turn_id`` es el id del
  mensaje entrante, que ya es único por turno; ``call_seq`` distingue las
  llamadas dentro del turno (classify, respond, un respond más tras una
  tool). Reprocesar el stream no duplica facturación.
- Mensajería: ``{provider_message_id}:channel``.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog

log = structlog.get_logger(__name__)

USAGE_STREAM = "nexus:usage"

# Cantidad de entradas del stream que se conservan. El consumidor (WP-18)
# escribe en Postgres, así que el stream es un buffer de reproceso, no un
# almacén: con esto cabe holgadamente un incidente de varias horas.
USAGE_STREAM_MAXLEN = 100_000

# Mapeo de las claves de uso de LiteLLM a los medidores del plan. Lo que no
# esté aquí, no se mide: un medidor inventado sobre la marcha es una
# categoría de facturación fantasma.
LLM_METERS: dict[str, str] = {
    "prompt_tokens": "llm.input_tokens",
    "completion_tokens": "llm.output_tokens",
    "cache_read_input_tokens": "llm.cache_read",
    "cache_creation_input_tokens": "llm.cache_write",
}


@dataclass(frozen=True)
class UsageEvent:
    """Un evento medible. Sin precio: lo pone el consumidor."""

    meter: str
    quantity: float
    idempotency_key: str
    occurred_at: str
    provider: str | None = None
    model: str | None = None

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "meter": self.meter,
            "quantity": self.quantity,
            "idempotency_key": self.idempotency_key,
            "occurred_at": self.occurred_at,
        }
        if self.provider:
            out["provider"] = self.provider
        if self.model:
            out["model"] = self.model
        return out


@dataclass
class _TurnScope:
    tenant_id: uuid.UUID
    turn_id: str
    conversation_id: uuid.UUID | None = None
    agent_config_id: uuid.UUID | None = None
    events: list[UsageEvent] = field(default_factory=list)
    call_seq: int = 0


_scope: ContextVar[_TurnScope | None] = ContextVar("nexus_usage_scope", default=None)


def _now() -> str:
    return datetime.now(UTC).isoformat()


@asynccontextmanager
async def usage_turn(
    *,
    tenant_id: uuid.UUID,
    turn_id: str,
    conversation_id: uuid.UUID | None = None,
    agent_config_id: uuid.UUID | None = None,
) -> AsyncIterator[None]:
    """Abre el buffer del turno y lo publica al salir, pase lo que pase."""
    scope = _TurnScope(
        tenant_id=tenant_id,
        turn_id=turn_id,
        conversation_id=conversation_id,
        agent_config_id=agent_config_id,
    )
    token = _scope.set(scope)
    try:
        yield
    finally:
        _scope.reset(token)
        await _publish(scope)


def record_usage(
    *,
    meter: str,
    quantity: float,
    provider: str | None = None,
    model: str | None = None,
    idempotency_suffix: str | None = None,
) -> None:
    """Anota un evento en el turno en curso. Fuera de turno, no-op."""
    try:
        scope = _scope.get()
        if scope is None or quantity <= 0:
            return
        suffix = idempotency_suffix or f"{scope.call_seq}:{meter}"
        scope.events.append(
            UsageEvent(
                meter=meter,
                quantity=float(quantity),
                idempotency_key=f"{scope.turn_id}:{suffix}",
                occurred_at=_now(),
                provider=provider,
                model=model,
            )
        )
    except Exception as exc:  # pragma: no cover - defensivo
        log.warning("usage.record_failed", meter=meter, error=str(exc))


def record_llm_usage(*, model: str, provider: str | None, usage: dict[str, int]) -> None:
    """Una llamada LLM → un evento por medidor con cantidad > 0.

    Se llama desde ``LiteLLMProvider._raw_complete``, el ÚNICO punto por el
    que pasan todas las llamadas del sistema (classify, respond, grader,
    multimodal): una línea allí da cobertura total.
    """
    try:
        scope = _scope.get()
        if scope is None:
            return
        scope.call_seq += 1
        for usage_key, meter in LLM_METERS.items():
            quantity = usage.get(usage_key) or 0
            if quantity:
                record_usage(meter=meter, quantity=quantity, provider=provider, model=model)
    except Exception as exc:  # pragma: no cover - defensivo
        log.warning("usage.record_llm_failed", model=model, error=str(exc))


async def record_channel_message(
    *,
    tenant_id: uuid.UUID,
    provider: str,
    provider_message_id: str | None,
    conversation_id: uuid.UUID | None = None,
) -> None:
    """Un saliente entregado = un ``channel.message``.

    Se publica de inmediato en vez de acumularse: el egress no corre dentro
    de un turno (drena en su propio bucle) y cada envío es ya su propia
    unidad. Sin ``provider_message_id`` no hay clave de idempotencia
    estable, así que no se mide — mejor un hueco que una fila duplicada en
    una factura.
    """
    if not provider_message_id:
        return
    scope = _TurnScope(tenant_id=tenant_id, turn_id="channel", conversation_id=conversation_id)
    scope.events.append(
        UsageEvent(
            meter="channel.message",
            quantity=1.0,
            idempotency_key=f"{provider_message_id}:channel",
            occurred_at=_now(),
            provider=provider,
        )
    )
    await _publish(scope)


async def _publish(scope: _TurnScope) -> None:
    """Un XADD por turno con el lote entero. Nunca lanza."""
    if not scope.events:
        return
    try:
        from nexus_api.core.redis_client import get_redis
        from nexus_api.core.streams import xadd_capped

        fields: dict[str, Any] = {
            "tenant_id": str(scope.tenant_id),
            "turn_id": scope.turn_id,
            "events": json.dumps([e.as_dict() for e in scope.events]),
        }
        if scope.conversation_id is not None:
            fields["conversation_id"] = str(scope.conversation_id)
        if scope.agent_config_id is not None:
            fields["agent_config_id"] = str(scope.agent_config_id)

        await xadd_capped(get_redis(), USAGE_STREAM, fields, maxlen=USAGE_STREAM_MAXLEN)
        log.info(
            "usage.published",
            tenant_id=str(scope.tenant_id),
            turn_id=scope.turn_id,
            events=len(scope.events),
        )
    except Exception as exc:
        # Perder la medición es un problema de negocio; romper el turno es
        # un problema de producción. Se elige el primero, ruidosamente.
        log.warning(
            "usage.publish_failed",
            tenant_id=str(scope.tenant_id),
            turn_id=scope.turn_id,
            events=len(scope.events),
            error=str(exc),
        )
    finally:
        scope.events.clear()


def drain_for_tests() -> list[UsageEvent]:
    """Vacía y devuelve el buffer del turno en curso (solo tests)."""
    scope = _scope.get()
    if scope is None:
        return []
    events = list(scope.events)
    scope.events.clear()
    return events
