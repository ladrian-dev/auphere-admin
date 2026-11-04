"""Un modelo que no respondió en el playground o en una pasada de pruebas.

El handler del grafo contesta con un texto de emergencia cuando el modelo falla, y
eso es correcto para un cliente de verdad. Aquí esa respuesta no es del agente: el
agente **no se ha probado** (bug ``el-probador-tapa-los-fallos-del-modelo``).

**Por qué no cuenta para ``turn_error_burst``.** Esa alerta escribe
``platform.turn_error_burst`` y ``streams/operator_alerts.py`` lo convierte en un
WhatsApp al dueño del negocio. Un partner que prueba su borrador no puede despertar
al negocio, ni el negocio puede hacer nada. Estos fallos tienen su contador y su alerta
(``simulated_model_failure_burst``), sin fila de auditoría: la lee Auphere.
"""

from __future__ import annotations

import contextlib
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final, Literal

import structlog
from nexus_api.core import redis_client
from nexus_api.core.otel_metrics import record_turn_error

log = structlog.get_logger(__name__)

#: ``<prefijo>:<tenant>:<ventana>``: lo lee ``streams/platform_watcher.py``.
COUNTER_PREFIX: Final = "nexus:alert:simulated_model_failures"
WINDOW_S: Final = 600
_COUNTER_TTL_S: Final = 1_200

Who = Literal["agent", "customer", "judge"]
Reason = Literal["llm_failed", "no_model", "empty_response"]

_WHOSE: Final[dict[Who, str]] = {
    "agent": "del agente",
    "customer": "del cliente simulado",
    "judge": "del juez",
}
#: Un ``handoff``, o un ``llm_failed`` con estos motivos, lo decidió el router: llegó
#: al modelo y paró por su techo o porque tocaba pasar a una persona.
_ROUTER_DECIDED: Final = frozenset({"turn_limit", "escalated"})


@dataclass(frozen=True)
class ModelFailure:
    who: Who
    reason: Reason
    #: Lo que dijo el proveedor. Para el registro: nunca sale hacia la consola.
    detail: str | None = None

    @property
    def why(self) -> str:
        """Lo que enseña la consola de una prueba que no se pudo probar."""
        whose = _WHOSE[self.who]
        if self.reason == "no_model":
            return f"No hay ningún modelo {whose} disponible para este cliente."
        if self.reason == "empty_response":
            return f"El modelo {whose} devolvió una respuesta vacía."
        return f"El modelo {whose} no respondió."


def failure_of_turn(final: Mapping[str, Any]) -> ModelFailure | None:
    """Lo que dejó el handler en ``AgentState.turn_failure``, si fue del modelo."""
    raw = final.get("turn_failure")
    if not isinstance(raw, Mapping):
        return None
    kind, reason = raw.get("kind"), raw.get("reason")
    if kind == "empty_response":
        return ModelFailure("agent", "empty_response")
    if kind != "llm_failed" or reason in _ROUTER_DECIDED:
        return None
    detail = raw.get("detail")
    return ModelFailure(
        "agent",
        "no_model" if reason == "no_model" else "llm_failed",
        str(detail) if detail else None,
    )


def failure_of_call(who: Who, exc: BaseException) -> ModelFailure:
    """Una llamada que el modelo del cliente simulado o el del juez no contestó."""
    return ModelFailure(who, "llm_failed", f"{type(exc).__name__}: {exc}")


async def note_model_failure(tenant_id: uuid.UUID, failure: ModelFailure) -> None:
    """Deja el rastro: el registro, la métrica y el contador de la alerta. Nunca lanza."""
    log.warning(
        "simulation.model_failed",
        tenant_id=str(tenant_id),
        who=failure.who,
        reason=failure.reason,
        detail=(failure.detail or "")[:200] or None,
    )
    record_turn_error(tenant_id=str(tenant_id), stage="simulation")
    with contextlib.suppress(Exception):
        key = f"{COUNTER_PREFIX}:{tenant_id}:{int(time.time()) // WINDOW_S}"
        redis = redis_client.get_redis()
        await redis.incr(key)
        await redis.expire(key, _COUNTER_TTL_S)


__all__ = [
    "COUNTER_PREFIX",
    "WINDOW_S",
    "ModelFailure",
    "Reason",
    "Who",
    "failure_of_call",
    "failure_of_turn",
    "note_model_failure",
]
