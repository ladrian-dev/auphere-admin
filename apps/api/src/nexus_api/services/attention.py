"""La regla única de atención — spec 047, T011 (requisitos 7.2 y 7.3).

Decide si un cliente «necesita atención» y por qué. Es **una** regla y vive
aquí: la lista de clientes, el Panel del partner («Necesita tu atención») y ⌘K
la leen de la API; ninguna la recalcula.

Los motivos, de más a menos grave (7.2), con el arreglo que el Panel pone en
cada fila (48.2):

1. ``no_balance`` — la bolsa está vacía → «Asignar saldo» / «Pedir saldo»;
2. ``channel_problem`` — un canal con problemas, o desconectado sin que nadie
   lo pidiera → «Arreglar»;
3. ``integration_reauth`` — una integración que hay que volver a autorizar →
   «Reconectar»;
4. ``agent_cap`` — un agente en pausa por su tope → «Subir el tope»;
5. ``agent_without_channel`` — un agente «Listo · sin canal» o «En prueba» →
   «Conectar canal»;
6. ``low_balance`` — por debajo del 20 % de la bolsa o para menos de 7 días →
   «Asignar saldo»;
7. ``no_agents`` — ningún agente sin archivar → «Nuevo agente».

El estado de cada agente y de cada canal sale de ``agent_lifecycle`` (un solo
cálculo, 25.5): un canal en pausa no es un problema, y uno «A todos» que se ha
caído sí lo es.

Una decisión que la spec no escribe: **un cliente archivado no necesita
atención**. Archivar es apartarlo a propósito —sus agentes quedan en pausa y su
bolsa no corre— y sale en «Archivados», no en «Necesitan atención».

La regla no ve importes: compara bolsas de monedas distintas por los días que
les quedan y por su porcentaje (7.5). Funciones puras, sin base ni reloj.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from nexus_api.services.agent_lifecycle import (
    AgentFacts,
    agent_visible_state,
    channel_visible_state,
)

#: Los motivos, de más a menos grave.
ATTENTION_REASONS: tuple[str, ...] = (
    "no_balance",
    "channel_problem",
    "integration_reauth",
    "agent_cap",
    "agent_without_channel",
    "low_balance",
    "no_agents",
)
#: «Saldo bajo»: por debajo de este porcentaje de la bolsa…
LOW_BALANCE_PCT = 20
#: …o para menos de estos días al ritmo de los últimos 7.
LOW_BALANCE_DAYS = 7


@dataclass(frozen=True)
class ClientFacts:
    """Lo que la regla necesita de un cliente.

    ``pct_left`` es lo que queda de la bolsa sobre su base (de 0 a 100) y
    ``days_left``, los días al ritmo de los últimos 7 días completos; ``None``
    cuando no hay datos para estimarlo (``contracts/events.md`` §1.4).
    ``ref`` identifica al cliente y desempata el orden de la lista.
    """

    ref: str
    archived: bool = False
    bag_empty: bool = False
    pct_left: float | None = None
    days_left: float | None = None
    reauth_integrations: int = 0
    agents: tuple[AgentFacts, ...] = ()


@dataclass(frozen=True)
class AttentionReason:
    """Un motivo y cuántas cosas lo causan («2 canales con problemas»)."""

    code: str
    count: int = 1


@dataclass(frozen=True)
class Attention:
    """Los motivos de un cliente, de más a menos grave."""

    reasons: tuple[AttentionReason, ...] = ()

    @property
    def needs_attention(self) -> bool:
        return bool(self.reasons)

    @property
    def top(self) -> AttentionReason | None:
        return self.reasons[0] if self.reasons else None


def _low_balance(client: ClientFacts) -> bool:
    if client.pct_left is not None and client.pct_left < LOW_BALANCE_PCT:
        return True
    return client.days_left is not None and client.days_left < LOW_BALANCE_DAYS


def attention(client: ClientFacts) -> Attention:
    """Los motivos del requisito 7.2 que se cumplen, en su orden."""
    if client.archived:
        return Attention()

    channel_problems = 0
    capped = 0
    without_channel = 0
    live_agents = 0
    for agent in client.agents:
        for channel in agent.channels:
            state = channel_visible_state(channel)
            if state.code == "problem" or (
                state.code == "disconnected" and not channel.disconnected_on_request
            ):
                channel_problems += 1
        visible = agent_visible_state(agent)
        if visible.code == "archived":
            continue
        live_agents += 1
        if visible.code == "paused" and visible.reason == "agent_cap":
            capped += 1
        elif visible.code in ("ready_no_channel", "testing"):
            without_channel += 1

    found: dict[str, int] = {}
    if client.bag_empty:
        found["no_balance"] = 1
    if channel_problems:
        found["channel_problem"] = channel_problems
    if client.reauth_integrations > 0:
        found["integration_reauth"] = client.reauth_integrations
    if capped:
        found["agent_cap"] = capped
    if without_channel:
        found["agent_without_channel"] = without_channel
    # Una bolsa vacía también está por debajo del 20 %: se dice una vez, la peor.
    if not client.bag_empty and _low_balance(client):
        found["low_balance"] = 1
    if live_agents == 0:
        found["no_agents"] = 1
    return Attention(
        tuple(AttentionReason(code, found[code]) for code in ATTENTION_REASONS if code in found)
    )


def _days_key(client: ClientFacts) -> float:
    # Una bolsa vacía no tiene días por delante aunque no haya ritmo con que
    # estimarlos; sin datos, al final de su grupo.
    if client.bag_empty:
        return 0.0
    return math.inf if client.days_left is None else client.days_left


def _pct_key(client: ClientFacts) -> float:
    if client.bag_empty:
        return 0.0
    return math.inf if client.pct_left is None else client.pct_left


def list_order(clients: Iterable[ClientFacts]) -> list[ClientFacts]:
    """7.3: primero los que necesitan atención y, dentro de cada grupo, de
    menos a más días de saldo; a igualdad de días, el porcentaje y la
    referencia, para que el orden sea estable."""
    return sorted(
        clients,
        key=lambda c: (
            not attention(c).needs_attention,
            _days_key(c),
            _pct_key(c),
            c.ref,
        ),
    )


__all__ = [
    "ATTENTION_REASONS",
    "LOW_BALANCE_DAYS",
    "LOW_BALANCE_PCT",
    "Attention",
    "AttentionReason",
    "ClientFacts",
    "attention",
    "list_order",
]
