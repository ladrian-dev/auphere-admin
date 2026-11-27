"""El turno de una rutina — spec 082, T015 (requisitos 4 y 5).

Un turno sin conversación y sin cliente final. No reutiliza el grafo del canal
—que clasifica intención, enruta, formatea burbujas y escala a una persona—
porque nada de eso aplica cuando no hay nadie al otro lado. Sí reutiliza lo que
importa: la versión publicada del agente, su política de operador, su
conocimiento, y el mismo despacho con lista blanca.

**Lo que hay aquí ahora es la elección de herramientas**, que es la parte que
sostiene las garantías 2 y 8 y la que no puede salir mal. El bucle que llama al
modelo va en este mismo módulo y llega con el manejador de la cola.

La elección es una resta sobre el techo del agente, nunca una suma:

1. **La que exige una conversación** se cae sola. En el canal el servidor le
   pone el ``conversation_id`` del turno. Aquí no hay ninguno que poner, y
   pedírselo al modelo es pedirle que se lo invente.
2. **La que deja al modelo elegir a una persona** tampoco entra. En el canal el
   servidor la ata al cliente final del turno. Aquí no hay a quién atarla.
3. **Lo que la activación bloquea** sigue bloqueado: una rutina hereda el
   permiso de cada conexión, no lo amplía.
4. **Lo que pide aprobación se trata como bloqueado**, y la ejecución lo
   escribe. Es provisional: hoy la pregunta sale por el canal de avisos del
   dueño del negocio y va atada a una conversación. Cuando se pueda preguntar
   desde la consola, este punto desaparece y la rutina se queda esperando en
   vez de callarse.

Nada de lo que se queda fuera se pierde en silencio: cada herramienta retenida
viaja en ``withheld`` con su porqué, y de ahí sale el estado ``partial`` de la
ejecución. Un informe al que le falta una parte y no lo dice es peor que no
tenerlo.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Final, Protocol

import structlog
from nexus_api.services.activations import ToolPolicy, needs_connector
from nexus_api.services.agent_spec.validator import end_customer_picks

log = structlog.get_logger(__name__)

#: El argumento que el servidor pone en el canal y que aquí no existe.
CONVERSATION_ARG: Final = "conversation_id"

#: Por qué una herramienta no llegó al turno. Son los cuatro motivos posibles y
#: la consola los traduce: aquí no se guarda texto para leer.
WHY: Final[tuple[str, ...]] = (
    "needs_a_conversation",
    "picks_an_end_customer",
    "needs_approval",
    "not_activated",
)


class Registry(Protocol):
    """Lo justo del registro que mira la elección."""

    def names(self) -> tuple[str, ...]: ...

    def get_tool_definitions(self, whitelist: Any) -> list[Any]: ...


@dataclass(frozen=True)
class Withheld:
    tool: str
    why: str

    def as_dict(self) -> dict[str, str]:
        return {"tool": self.tool, "why": self.why}


@dataclass(frozen=True)
class RoutineTools:
    """Lo que el turno ofrece y lo que se quedó fuera, con su porqué."""

    names: tuple[str, ...]
    withheld: tuple[Withheld, ...]

    @property
    def partial(self) -> bool:
        """Si la ejecución tiene que decir que le faltó algo. Lo que se cae por
        no tener conversación no cuenta: esas herramientas no son de una rutina
        y su ausencia no deja el trabajo a medias."""
        return any(w.why in {"needs_approval", "not_activated"} for w in self.withheld)


def _parameters(registry: Registry, name: str) -> dict[str, Any]:
    defs = registry.get_tool_definitions((name,))
    if not defs:
        return {}
    params = getattr(defs[0], "parameters", None)
    return params if isinstance(params, dict) else {}


def _needs_a_conversation(parameters: dict[str, Any]) -> bool:
    return CONVERSATION_ARG in (parameters.get("required") or [])


def _picks_an_end_customer(name: str, parameters: dict[str, Any]) -> bool:
    return bool(end_customer_picks(name, frozenset(parameters.get("properties") or {})))


def select_tools(registry: Registry, ceiling: tuple[str, ...], policy: ToolPolicy) -> RoutineTools:
    """Las herramientas de un turno de rutina, a partir del techo del agente.

    Función pura: ni base de datos ni red, para que la pueda barrer una suite
    entera herramienta a herramienta.
    """
    offered: list[str] = []
    withheld: list[Withheld] = []
    for name in sorted(set(ceiling)):
        parameters = _parameters(registry, name)
        if _needs_a_conversation(parameters):
            withheld.append(Withheld(name, "needs_a_conversation"))
        elif _picks_an_end_customer(name, parameters):
            withheld.append(Withheld(name, "picks_an_end_customer"))
        elif name in policy.blocked or (policy.closed and needs_connector(name)):
            withheld.append(Withheld(name, "not_activated"))
        elif name in policy.needs_approval:
            # Provisional: ver el punto 4 de la cabecera.
            withheld.append(Withheld(name, "needs_approval"))
        else:
            offered.append(name)
    return RoutineTools(names=tuple(offered), withheld=tuple(withheld))


async def tools_for_routine(
    registry: Registry,
    *,
    ceiling: frozenset[str],
    tenant_id: Any,
    agent_id: Any,
) -> RoutineTools:
    """Lo mismo, leyendo la política de la base. **Falla cerrada**, igual que el
    turno del canal: si la activación no se puede leer, el turno no ofrece
    ninguna herramienta de conector."""
    from nexus_api.core.tenant_context import tenant_scoped_session
    from nexus_api.db.base import get_sessionmaker
    from nexus_api.services import activations

    try:
        sm = get_sessionmaker()
        async with sm() as session, tenant_scoped_session(session, tenant_id):
            policy = await activations.tool_policy(session, tenant_id, agent_id)
    except Exception as exc:
        log.warning(
            "schedule_turn.tool_policy_failed",
            tenant_id=str(tenant_id),
            error=type(exc).__name__,
        )
        policy = ToolPolicy(closed=True)
    return select_tools(registry, tuple(ceiling), policy)


#: Vueltas antes de obligar al modelo a escribir. La última va sin herramientas:
#: si no, un modelo que se atasca pide una llamada más para siempre y la
#: ejecución termina sin una línea de respuesta.
MAX_ITERATIONS: Final = 6
#: El papel con el que se pide el modelo: el mismo con el que el agente contesta.
ROLE: Final = "respond"


@dataclass(frozen=True)
class RoutineAnswer:
    """Lo que la ejecución guarda: el texto, lo que usó y si quedó a medias."""

    text: str
    tools_used: tuple[str, ...]
    withheld: tuple[Withheld, ...]
    iterations: int
    partial: bool


def _result_text(envelope: Any) -> str:
    """El resultado de la herramienta tal cual vuelve al modelo. Nada de
    resúmenes: antes de ADR-023 el modelo escribía la respuesta final sobre un
    resumen de las llamadas y nunca veía el dato, lo que hacía decorativa toda
    herramienta de lectura."""
    try:
        return json.dumps(envelope, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(envelope)


async def run_loop(
    *,
    provider: Any,
    model: str,
    tenant_id: uuid.UUID,
    system: str,
    instruction: str,
    registry: Any,
    chosen: RoutineTools,
    max_iterations: int = MAX_ITERATIONS,
) -> RoutineAnswer:
    """El bucle del turno: pedir, despachar, devolver el resultado y repetir.

    La instrucción del partner entra como mensaje de operador y lo que devuelven
    las herramientas como resultado, nunca mezclados (constitución §III).
    """
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": instruction},
    ]
    used: list[str] = []
    failed = False
    text = ""
    rounds = 0

    for rounds in range(1, max_iterations + 1):
        last = rounds == max_iterations
        tools: list[dict[str, Any]] = (
            [] if last or not chosen.names else registry.get_openai_tools(chosen.names)
        )
        response = await provider.acomplete_with_tools(
            tenant_id=tenant_id,
            role=ROLE,
            model=model,
            messages=messages,
            tools=tools,
        )
        if not response.tool_calls:
            text = response.text
            break

        messages.append(
            {
                "role": "assistant",
                "content": response.text or None,
                "tool_calls": [
                    {
                        "id": call.id or call.name,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(call.arguments or {}, default=str),
                        },
                    }
                    for call in response.tool_calls
                ],
            }
        )
        for call in response.tool_calls:
            try:
                envelope = await registry.dispatch(
                    call.name, dict(call.arguments or {}), whitelist=chosen.names
                )
            except Exception as exc:
                # Un fallo vuelve al modelo como resultado: así puede decir qué
                # no pudo hacer, que es mejor que una ejecución sin respuesta.
                failed = True
                envelope = {"status": "error", "error": type(exc).__name__}
                log.warning(
                    "schedule_turn.tool_failed",
                    tenant_id=str(tenant_id),
                    tool=call.name,
                    error=type(exc).__name__,
                )
            else:
                used.append(call.name)
                if isinstance(envelope, dict) and envelope.get("status") not in (None, "ok"):
                    failed = True
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id or call.name,
                    "content": _result_text(envelope),
                }
            )

    return RoutineAnswer(
        text=text,
        tools_used=tuple(dict.fromkeys(used)),
        withheld=chosen.withheld,
        iterations=rounds,
        partial=chosen.partial or failed,
    )


__all__ = [
    "CONVERSATION_ARG",
    "MAX_ITERATIONS",
    "ROLE",
    "WHY",
    "RoutineAnswer",
    "RoutineTools",
    "Withheld",
    "run_loop",
    "select_tools",
    "tools_for_routine",
]
