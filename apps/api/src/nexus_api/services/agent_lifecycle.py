"""El estado visible del agente y del canal — spec 047, T010 (requisitos 25.3 y 25.5).

``contracts/events.md`` §1.2 y §1.3, en código. Lo que se **guarda** es la vida
del agente (``draft``, ``published``, ``paused`` con su motivo, ``archived``) y,
por canal, su estado (``active``, ``paused``, ``degraded``, ``disconnected``) y
su audiencia (``unset``, ``team_only``, ``everyone``). Lo que se **enseña** se
deriva aquí, en un solo sitio: la consola, la consola lite, la app y el Panel
del partner leen ``visible_state`` de la API y ninguno lo recalcula (25.5).

Las dos tablas se leen en orden y gana la primera regla que se cumple. De ahí
sale la regla que más se olvida: un canal en pausa o con problemas no cuenta
como «A todos» ni como «Solo mi equipo», porque su estado se evalúa antes que
su audiencia. Un agente con un único canal «A todos» que se ha caído no está
«Atendiendo»: está «Listo · sin canal».

Funciones puras: sin base, sin reloj y sin textos. Los textos («Atendiendo»,
«Pausado · {motivo}») son de la interfaz; aquí viajan el código, el tono de
``status-badge`` y, si lo hay, el motivo. Un valor fuera del vocabulario es un
error de programación (la base lo impide con sus CHECK) y se rechaza con
``ValueError`` en vez de pintarse como otra cosa.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

#: La vida del agente que se guarda (§1.1).
AGENT_LIFE_STATES: tuple[str, ...] = ("draft", "published", "paused", "archived")
#: Por qué está en pausa (§1.1).
PAUSE_REASONS: tuple[str, ...] = (
    "manual",
    "no_balance",
    "agent_cap",
    "client_paused",
    "client_archived",
)

#: El estado del canal que se guarda (§1.2), su audiencia y, si está
#: ``degraded``, su motivo.
CHANNEL_STATUSES: tuple[str, ...] = ("active", "paused", "degraded", "disconnected")
AUDIENCE_MODES: tuple[str, ...] = ("unset", "team_only", "everyone")
PROBLEM_REASONS: tuple[str, ...] = (
    "quality",
    "auth_expired",
    "coexistence_inactive",
    "meta_error",
)

#: Los estados visibles, en el orden en que se evalúan sus reglas.
CHANNEL_VISIBLE_STATES: tuple[str, ...] = (
    "pending_link",
    "disconnected",
    "problem",
    "paused",
    "unconfigured",
    "team_only",
    "everyone",
)
AGENT_VISIBLE_STATES: tuple[str, ...] = (
    "archived",
    "paused",
    "draft",
    "serving",
    "testing",
    "ready_no_channel",
)

#: El tono de ``status-badge`` de cada estado visible.
_CHANNEL_TONE: dict[str, str] = {
    "pending_link": "info",
    "disconnected": "muted",
    "problem": "danger",
    "paused": "warn",
    "unconfigured": "muted",
    "team_only": "info",
    "everyone": "positive",
}
_AGENT_TONE: dict[str, str] = {
    "archived": "muted",
    "paused": "warn",
    "draft": "muted",
    "serving": "positive",
    "testing": "info",
    "ready_no_channel": "info",
}


@dataclass(frozen=True)
class VisibleState:
    """Lo que se pinta: el código, el tono y, en pausa o con problemas, el motivo."""

    code: str
    tone: str
    reason: str | None = None


@dataclass(frozen=True)
class ChannelFacts:
    """Lo que se guarda de un canal y basta para derivar su estado visible.

    ``owner_link_pending`` y ``has_number`` describen el enlace del dueño (spec
    040): mientras está pendiente y el número aún no existe, el canal es
    «Pendiente · enlace enviado» diga lo que diga el resto de la fila.
    ``disconnected_on_request`` no cambia lo que se pinta; lo lee la regla de
    atención (``services/attention.py``), que solo avisa de una desconexión que
    nadie pidió.
    """

    status: str = "active"
    audience_mode: str = "unset"
    problem_reason: str | None = None
    owner_link_pending: bool = False
    has_number: bool = True
    disconnected_on_request: bool = False


@dataclass(frozen=True)
class AgentFacts:
    """Lo que se guarda de un agente y de sus canales."""

    life: str
    pause_reason: str | None = None
    channels: tuple[ChannelFacts, ...] = ()


def _check(value: str | None, allowed: tuple[str, ...], what: str) -> None:
    if value not in allowed:
        raise ValueError(f"unknown {what}: {value!r}")


def channel_visible_state(channel: ChannelFacts) -> VisibleState:
    """§1.2: la primera regla que se cumple, en el orden de la tabla."""
    _check(channel.status, CHANNEL_STATUSES, "channel status")
    _check(channel.audience_mode, AUDIENCE_MODES, "audience mode")
    if channel.problem_reason is not None:
        _check(channel.problem_reason, PROBLEM_REASONS, "problem reason")

    if channel.owner_link_pending and not channel.has_number:
        code = "pending_link"
    elif channel.status == "disconnected":
        code = "disconnected"
    elif channel.status == "degraded":
        return VisibleState("problem", _CHANNEL_TONE["problem"], channel.problem_reason)
    elif channel.status == "paused":
        code = "paused"
    elif channel.audience_mode == "unset":
        code = "unconfigured"
    else:
        # ``team_only`` o ``everyone``: el mismo nombre que la audiencia.
        code = channel.audience_mode
    return VisibleState(code, _CHANNEL_TONE[code])


def visible_state(
    life: str,
    *,
    pause_reason: str | None = None,
    channels: Iterable[ChannelFacts] = (),
) -> VisibleState:
    """§1.3: la primera regla que se cumple, en el orden de la tabla.

    Los canales cuentan por su estado **visible**: solo un canal que de verdad
    responde a todos hace que el agente esté «Atendiendo», y solo uno que de
    verdad responde a su equipo lo deja «En prueba».
    """
    _check(life, AGENT_LIFE_STATES, "agent life state")
    if life == "archived":
        return VisibleState("archived", _AGENT_TONE["archived"])
    if life == "paused":
        if pause_reason is not None:
            _check(pause_reason, PAUSE_REASONS, "pause reason")
        return VisibleState("paused", _AGENT_TONE["paused"], pause_reason)
    if life == "draft":
        return VisibleState("draft", _AGENT_TONE["draft"])

    answering = {channel_visible_state(c).code for c in channels}
    if "everyone" in answering:
        code = "serving"
    elif "team_only" in answering:
        code = "testing"
    else:
        code = "ready_no_channel"
    return VisibleState(code, _AGENT_TONE[code])


def agent_visible_state(agent: AgentFacts) -> VisibleState:
    """``visible_state`` sobre los hechos de un agente ya cargados."""
    return visible_state(agent.life, pause_reason=agent.pause_reason, channels=agent.channels)


__all__ = [
    "AGENT_LIFE_STATES",
    "AGENT_VISIBLE_STATES",
    "AUDIENCE_MODES",
    "CHANNEL_STATUSES",
    "CHANNEL_VISIBLE_STATES",
    "PAUSE_REASONS",
    "PROBLEM_REASONS",
    "AgentFacts",
    "ChannelFacts",
    "VisibleState",
    "agent_visible_state",
    "channel_visible_state",
    "visible_state",
]
