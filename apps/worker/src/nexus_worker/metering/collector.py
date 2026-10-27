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
import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog
from nexus_api.db.models.usage_record import USAGE_LINE_BY_SOURCE

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

# Quién originó el consumo. Cerrado a propósito, igual que ``USAGE_METERS``:
# un origen inventado sobre la marcha es una categoría de facturación
# fantasma. ``qa`` es gasto real de Anthropic que NO paga el cliente — el
# operador está probando su agente, no atendiendo a nadie.
SOURCE_CHANNEL = "channel"
SOURCE_QA = "qa"
# CO-01: el Companion de la consola. Gasto real de Anthropic que **tampoco**
# paga el cliente final, y que además no puede compartir tope con ``qa``: si
# lo compartiera, probar el agente y pedirle ayuda al Companion se robarían
# presupuesto entre sí.
SOURCE_COMPANION = "companion"
# Spec 047 (0177, requisito 46.4): la partida «Construcción y pruebas». Gasto
# que paga Auphere hasta el tope del partner y que nunca sale de la bolsa de un
# cliente: el constructor, las pruebas, la lectura de webs, la indexación, las
# sugerencias y las certificaciones. La lista es la de ``ck_usage_source`` y
# ``USAGE_LINE_BY_SOURCE`` del modelo; un origen fuera de ella se mediría como
# tráfico del cliente (``usage_turn``), que es justo lo que no puede pasar.
SOURCE_BUILDER = "builder"
SOURCE_TESTS = "tests"
SOURCE_READER = "reader"
SOURCE_INDEXER = "indexer"
SOURCE_SUGGESTIONS = "suggestions"
SOURCE_CERTIFICATION = "certification"
USAGE_SOURCES: frozenset[str] = frozenset(USAGE_LINE_BY_SOURCE)

# Spec 047 (requisito 40.1): la taxonomía de tareas del router, versión 1
# (``contracts/router-and-catalog.md`` §1). Es la del catálogo
# (``router_taxonomy``, sembrada en la 0180) y una prueba las ata: una tarea
# nueva es una versión nueva de la taxonomía, no una cadena inventada aquí.
LLM_TASKS: frozenset[str] = frozenset(
    {
        "classify",
        "extract",
        "answer",
        "tool_turn",
        "escalate",
        "summarize",
        "translate",
        "vision",
        "transcribe",
        "embed",
        "rerank",
        "moderate",
        "judge",
        "build",
        "read_source",
    }
)

# Una llamada a un modelo sin tarea (o con una que no está en la taxonomía)
# falla en los tests y en producción se mide igual y queda como anomalía
# (``usage.task_missing``). Lo enciende la suite con esta variable: en
# producción, tirar el turno por una etiqueta sería peor que el hueco.
REQUIRE_TASK_ENV = "NEXUS_USAGE_REQUIRE_TASK"


class UsageTaskMissing(RuntimeError):
    """Una llamada a un modelo sin tarea de la taxonomía, con el modo estricto."""


def _task_required() -> bool:
    return os.environ.get(REQUIRE_TASK_ENV, "").strip().lower() in {"1", "true", "yes"}


def _check_task(task: str | None, *, model: str) -> None:
    """La tarea de una llamada: estricto en los tests, anomalía en producción.

    Lanza **fuera** de cualquier ``try``: es lo único de este módulo que puede
    romper un turno, y solo con el modo estricto encendido.
    """
    if task in LLM_TASKS:
        return
    if _task_required():
        raise UsageTaskMissing(
            f"llamada a {model!r} sin tarea de la taxonomía (task={task!r}); "
            "cada llamada a un modelo lleva su tarea (requisito 40.1)"
        )
    scope = _scope.get()
    log.error(
        "usage.task_missing" if task is None else "usage.task_unknown",
        tenant_id=str(scope.tenant_id) if scope else None,
        turn_id=scope.turn_id if scope else None,
        source=scope.source if scope else None,
        model=model,
        task=task,
    )


def provider_of(model: str) -> str | None:
    """``anthropic/claude-sonnet-4-6`` → ``anthropic``. None si el
    identificador no lleva proveedor: la fila se mide igual y el precio se
    resuelve por ``model_id``, que es la clave única del catálogo."""
    return model.split("/", 1)[0] if "/" in model else None


def usage_fields(response: Any) -> dict[str, int]:
    """Extrae el consumo de tokens de una respuesta de LiteLLM.

    Vive aquí y no en ``runtime.llm`` porque hay más de una llamada a
    LiteLLM en el sistema: además del proveedor del runtime, el
    ``MediaProcessor`` invoca ``acompletion`` por su cuenta para la visión.
    Mientras el extractor era privado de ``llm.py``, esas llamadas no
    tenían con qué medirse y sus tokens no aparecían en ninguna factura.

    Tolera respuestas con forma de dict y de objeto, y campos ausentes:
    devuelve solo lo que hay y nunca lanza — instrumentar no puede romper
    un turno.
    """

    def _get(obj: Any, key: str) -> Any:
        if obj is None:
            return None
        if hasattr(obj, "get"):
            try:
                return obj.get(key)
            except Exception:
                return None
        return getattr(obj, key, None)

    usage = _get(response, "usage")
    if usage is None:
        return {}
    out: dict[str, int] = {}
    for key in (
        "prompt_tokens",
        "completion_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
    ):
        val = _get(usage, key)
        if isinstance(val, int):
            out[key] = val
    # Anthropic a veces reporta el acierto de caché en ``prompt_tokens_details``.
    if "cache_read_input_tokens" not in out:
        cached = _get(_get(usage, "prompt_tokens_details"), "cached_tokens")
        if isinstance(cached, int):
            out["cache_read_input_tokens"] = cached
    return out


@dataclass(frozen=True)
class UsageEvent:
    """Un evento medible. Sin precio: lo pone el consumidor."""

    meter: str
    quantity: float
    idempotency_key: str
    occurred_at: str
    provider: str | None = None
    model: str | None = None
    # Spec 047 (0177): the router's task and its decision, per call.
    task: str | None = None
    route_decision_id: str | None = None

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
        if self.task:
            out["task"] = self.task
        if self.route_decision_id:
            out["route_decision_id"] = self.route_decision_id
        return out


@dataclass
class _TurnScope:
    tenant_id: uuid.UUID
    turn_id: str
    conversation_id: uuid.UUID | None = None
    agent_config_id: uuid.UUID | None = None
    # Spec 030: the client's agent the turn ran for (spend per agent).
    agent_id: uuid.UUID | None = None
    source: str = SOURCE_CHANNEL
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
    source: str = SOURCE_CHANNEL,
    agent_id: uuid.UUID | None = None,
) -> AsyncIterator[None]:
    """Abre el buffer del turno y lo publica al salir, pase lo que pase.

    ``source`` distingue el turno de un cliente del de un operador
    probando en el QA Playground. Por defecto ``channel`` para que
    cualquier camino nuevo que olvide declararlo cuente como tráfico real
    — es el error que se nota, frente a un consumo que se cuela como
    interno y desaparece de la factura.

    Spec 047 (requisito 46.4): la partida sale de ``source``. Todo lo que es
    «Construcción y pruebas» abre su propio buffer con su origen —el trabajo
    del constructor, la lectura de una web, la indexación, las pruebas o las
    sugerencias—, con el id del trabajo como ``turn_id``::

        async with usage_turn(tenant_id=t, turn_id=f"job:{job_id}", source=SOURCE_READER):
            ...

    El consumidor lo escribe con ``line = build`` (una certificación de
    Auphere, con ``platform``): no baja la bolsa del cliente ni alimenta su
    presupuesto (solo ``channel`` lo hace).
    """
    scope = _TurnScope(
        tenant_id=tenant_id,
        turn_id=turn_id,
        conversation_id=conversation_id,
        agent_config_id=agent_config_id,
        agent_id=agent_id,
        source=source if source in USAGE_SOURCES else SOURCE_CHANNEL,
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
    task: str | None = None,
    route_decision_id: uuid.UUID | None = None,
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
                task=task,
                route_decision_id=str(route_decision_id) if route_decision_id else None,
            )
        )
    except Exception as exc:  # pragma: no cover - defensivo
        log.warning("usage.record_failed", meter=meter, error=str(exc))


def record_llm_usage(
    *,
    model: str,
    provider: str | None,
    usage: dict[str, int],
    task: str | None = None,
    route_decision_id: uuid.UUID | None = None,
) -> None:
    """Una llamada LLM → un evento por medidor con cantidad > 0.

    Se llama desde ``LiteLLMProvider._raw_complete``, el ÚNICO punto por el
    que pasan todas las llamadas del sistema (classify, respond, grader,
    multimodal): una línea allí da cobertura total.

    Spec 047: ``task`` es la tarea de la taxonomía y ``route_decision_id`` la
    decisión del router que eligió el modelo. Sin tarea, falla con el modo
    estricto (los tests) y en producción se mide igual, como anomalía.
    """
    if _scope.get() is not None:
        _check_task(task, model=model)
    try:
        scope = _scope.get()
        if scope is None:
            return
        scope.call_seq += 1
        for usage_key, meter in LLM_METERS.items():
            quantity = usage.get(usage_key) or 0
            if quantity:
                record_usage(
                    meter=meter,
                    quantity=quantity,
                    provider=provider,
                    model=model,
                    task=task,
                    route_decision_id=route_decision_id,
                )
    except Exception as exc:  # pragma: no cover - defensivo
        log.warning("usage.record_llm_failed", model=model, error=str(exc))


def record_voice_minutes(
    *, model: str, provider: str | None, seconds: float, task: str = "transcribe"
) -> None:
    """Transcripción de una nota de voz → medidor ``voice.minutes``.

    Whisper se factura por minuto de audio, no por token, así que no cabe
    en ``record_llm_usage``. Los segundos vienen de la respuesta del
    proveedor (``verbose_json``): estimarlos a partir del tamaño del
    fichero daría una cifra plausible y falsa, y una factura creíble es
    peor que un hueco visible.

    Incrementa ``call_seq`` igual que ``record_llm_usage`` — un turno con
    dos notas de voz necesita dos claves de idempotencia distintas o la
    segunda se descartaría en el ``ON CONFLICT`` del consumidor.

    Spec 047: siempre es la tarea ``transcribe`` de la taxonomía.
    """
    try:
        scope = _scope.get()
        if scope is None or seconds <= 0:
            return
        scope.call_seq += 1
        record_usage(
            meter="voice.minutes",
            quantity=seconds / 60.0,
            provider=provider,
            model=model,
            task=task,
        )
    except Exception as exc:  # pragma: no cover - defensivo
        log.warning("usage.record_voice_failed", model=model, error=str(exc))


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


# Medidores de multimedia (0083 / CP-23). Un adjunto = una unidad de su
# tipo; para audio, además los segundos si el proveedor los dio. Cerrado,
# como todo lo demás: ``media.gif`` no existe hasta que exista aquí.
MEDIA_KINDS: frozenset[str] = frozenset({"image", "audio", "document", "video", "sticker"})


async def record_media_unit(
    *,
    tenant_id: uuid.UUID,
    kind: str,
    provider: str,
    provider_message_id: str | None,
    conversation_id: uuid.UUID | None = None,
    audio_seconds: float | None = None,
    source: str = SOURCE_CHANNEL,
) -> None:
    """Un adjunto (entrante procesado o saliente aceptado) = ``media.<kind>``.

    Publica de inmediato, como ``record_channel_message``: el saliente no
    corre dentro de un turno y el entrante se procesa ANTES de que el turno
    de LLM abra su buffer. Idempotencia por ``{provider_message_id}:media.
    {kind}`` — el mismo adjunto reprocesado no suma dos veces; sin id de
    proveedor no se mide (mejor un hueco que una fila duplicada).

    Para ``audio`` con duración conocida se emite además
    ``media.audio_seconds`` (misma clave + sufijo). No se estima: una
    duración inventada es una cifra plausible que nadie cuestiona.
    """
    if not provider_message_id or kind not in MEDIA_KINDS:
        return
    scope = _TurnScope(
        tenant_id=tenant_id,
        turn_id="media",
        conversation_id=conversation_id,
        source=source if source in USAGE_SOURCES else SOURCE_CHANNEL,
    )
    now = _now()
    scope.events.append(
        UsageEvent(
            meter=f"media.{kind}",
            quantity=1.0,
            idempotency_key=f"{provider_message_id}:media.{kind}",
            occurred_at=now,
            provider=provider,
        )
    )
    if kind == "audio" and audio_seconds is not None and audio_seconds > 0:
        scope.events.append(
            UsageEvent(
                meter="media.audio_seconds",
                quantity=float(audio_seconds),
                idempotency_key=f"{provider_message_id}:media.audio_seconds",
                occurred_at=now,
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
            "source": scope.source,
            "events": json.dumps([e.as_dict() for e in scope.events]),
        }
        if scope.conversation_id is not None:
            fields["conversation_id"] = str(scope.conversation_id)
        if scope.agent_config_id is not None:
            fields["agent_config_id"] = str(scope.agent_config_id)
        if scope.agent_id is not None:
            fields["agent_id"] = str(scope.agent_id)

        await xadd_capped(get_redis(), USAGE_STREAM, fields, maxlen=USAGE_STREAM_MAXLEN)
        log.info(
            "usage.published",
            tenant_id=str(scope.tenant_id),
            turn_id=scope.turn_id,
            source=scope.source,
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
