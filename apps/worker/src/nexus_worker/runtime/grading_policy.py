"""Cuándo graduar un turno en el momento y cuándo después (WP-21).

El grader es la mayor partida de coste y latencia que NO produce la
respuesta del cliente: una llamada extra de LLM por turno, y hasta tres
más si reescribe. Graduarlo todo síncronamente paga ese precio también
en el turno que solo dice "gracias".

La decisión se toma con tres preguntas, en orden:

1. ¿El agente pide ``sync``? Entonces siempre, y se acabó.
2. ¿Es un turno de riesgo? Reservar, escalar a un humano o haber
   ejecutado una herramienta que ESCRIBE. En esos, una respuesta mala
   tiene consecuencias fuera del chat, así que se corrige antes de
   enviarla, cueste lo que cueste.
3. Si no, se gradúa una muestra en el momento y el resto se difiere.

Lo que se pierde está asumido: en ~90% de los turnos de bajo riesgo ya
no hay corrección *antes* de responder. Se compensa con que el veredicto
diferido sigue guardándose (alimenta los evals y la mejora de prompt) y
con que los turnos que de verdad podían hacer daño no se muestrean nunca.

**El muestreo es determinista sobre el id del turno**, no aleatorio. Dos
motivos, los dos operativos: un reintento del mismo turno toma la misma
decisión (si fuese ``random()``, reintentar podría graduar lo que ya se
decidió no graduar, y el coste dejaría de ser predecible), y un test
puede fijar el resultado sin parchear el generador global.
"""

from __future__ import annotations

import time
import zlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
import structlog
from nexus_api.db.base import get_sessionmaker

log = structlog.get_logger(__name__)

# Intents cuya respuesta tiene efectos fuera de la conversación. Nunca se
# muestrean: si el agente confirma mal una reserva o escala mal, el daño
# ya está hecho cuando llegue el veredicto diferido.
RISKY_INTENTS: frozenset[str] = frozenset({"book", "escalate"})

_SAMPLE_BUCKETS = 10_000


@dataclass(frozen=True)
class GradingDecision:
    """Qué hacer con el grader en este turno."""

    # ``sync`` corre ahora y puede reescribir la respuesta; ``deferred``
    # publica un trabajo y deja pasar el turno; ``off`` no gradúa nunca.
    mode: str
    # Para logs y para que el operador entienda por qué un turno concreto
    # se graduó (o no) sin reconstruir la lógica de memoria.
    reason: str

    @property
    def is_sync(self) -> bool:
        return self.mode == "sync"

    @property
    def is_deferred(self) -> bool:
        return self.mode == "deferred"


def turn_writes(tool_calls: Iterable[Mapping[str, Any]], read_only_tools: frozenset[str]) -> bool:
    """¿Este turno ejecutó alguna herramienta que escribe?

    Fail-safe a propósito: una herramienta que no está en el conjunto de
    solo-lectura cuenta como escritura. El error caro es el contrario —
    tratar como inocuo un turno que acaba de cobrar, cancelar o mandar
    algo— y una herramienta nueva sin clasificar debe ser cara, no
    invisible.

    Solo cuentan las llamadas que SALIERON BIEN: una herramienta de
    escritura que falló no cambió nada fuera, así que el turno no
    necesita el trato de riesgo por ella.
    """
    for call in tool_calls:
        status = str(call.get("status") or "").lower()
        if status not in {"ok", "success", "succeeded"}:
            continue
        name = str(call.get("tool") or "")
        if name and name not in read_only_tools:
            return True
    return False


def decide(
    *,
    grader_enabled: bool,
    grader_mode: str,
    sample_rate: float,
    intent: str | None,
    wrote: bool,
    turn_key: str,
) -> GradingDecision:
    """Decide qué hacer con el grader en este turno."""
    if not grader_enabled:
        # El interruptor maestro del agent_config gana sobre el modo: un
        # agente con el grader apagado no gradúa ni difiere nada.
        return GradingDecision("off", "grader_disabled")
    if grader_mode == "off":
        return GradingDecision("off", "mode_off")
    if grader_mode == "sync":
        return GradingDecision("sync", "mode_sync")

    if intent in RISKY_INTENTS:
        return GradingDecision("sync", f"risky_intent:{intent}")
    if wrote:
        return GradingDecision("sync", "write_tool")

    if _in_sample(turn_key, sample_rate):
        return GradingDecision("sync", "sampled_in")
    return GradingDecision("deferred", "sampled_out")


# ── catálogo de herramientas de solo-lectura ──────────────────────────

# El catálogo cambia con despliegues, no con turnos: cachear 5 min evita
# una consulta por turno sin que una herramienta reclasificada tarde nada
# en surtir efecto.
_CATALOG_TTL_S = 300.0
_read_only: frozenset[str] | None = None
_read_only_at: float = 0.0

_READ_ONLY_SQL = sa.text("SELECT name FROM tool_catalog WHERE read_only IS TRUE")


async def load_read_only_tools(*, force: bool = False) -> frozenset[str]:
    """Nombres de las herramientas marcadas como solo-lectura.

    Si la consulta falla se devuelve el conjunto VACÍO, no el caché ni un
    valor optimista: con el conjunto vacío toda llamada cuenta como
    escritura y el turno se gradúa síncronamente. Se paga de más, que es
    el lado correcto en el que equivocarse.
    """
    global _read_only, _read_only_at
    now = time.monotonic()
    if not force and _read_only is not None and (now - _read_only_at) < _CATALOG_TTL_S:
        return _read_only
    try:
        sm = get_sessionmaker()
        async with sm() as session:
            names = (await session.execute(_READ_ONLY_SQL)).scalars().all()
        _read_only = frozenset(str(n) for n in names)
        _read_only_at = now
    except Exception as exc:
        log.warning("grading_policy.read_only_catalog_failed", error=str(exc))
        return _read_only if _read_only is not None else frozenset()
    return _read_only


def reset_read_only_cache() -> None:
    global _read_only, _read_only_at
    _read_only = None
    _read_only_at = 0.0


def _in_sample(turn_key: str, rate: float) -> bool:
    if rate <= 0:
        return False
    if rate >= 1:
        return True
    # CRC32 y no ``hash()``: el hash de str de Python lleva sal por
    # proceso, así que dos réplicas decidirían distinto sobre el MISMO
    # turno y el muestreo dejaría de ser reproducible.
    bucket = zlib.crc32(turn_key.encode()) % _SAMPLE_BUCKETS
    return bucket < int(rate * _SAMPLE_BUCKETS)
