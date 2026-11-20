"""La única resolución del modelo de respuesta de un agente — spec 065 (data-model.md §5).

En este orden (requisito 2.2):

1. la elección del agente (``agents.respond_model_profile_id``), de su partner o de Auphere;
2. si no, la de su versión (``policies.llm.respond_model``, que escribe una plantilla de
   semilla y no se elige desde ninguna pantalla);
3. si no, el modelo por defecto de Auphere de ese entorno
   (``platform_settings.agent_respond_default``), no ``llm_respond_model``.

Un origen que no puede ejecutar lo que el agente usa (Skills o conector MCP de Anthropic) se
salta y queda en ``skipped``, que es lo que la consola avisa (requisito 4.8). Si ninguno
puede, responde la reserva de la otra familia del modelo por defecto, y si tampoco, el
modelo por defecto: nunca se queda un agente sin modelo.

La asignación de respuesta del cliente (``tenant_model_bindings``, rol ``respond``) ya no es
un escalón (requisito 12). La usan el turno, las guardas de la spec 059, la consola y el
panel; ``test_respond_model_resolution`` barre que nadie resuelva por su cuenta.
"""

from __future__ import annotations

from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from typing import Literal

from nexus_api.core.respond_profiles import SONNET_55, can_run, profile_for

Source = Literal["agent", "agent_operator", "version", "platform"]
SetBy = Literal["partner", "operator"]


@dataclass(frozen=True)
class AgentChoice:
    """La elección de modelo guardada en un agente."""

    model_id: str
    set_by: SetBy


@dataclass(frozen=True)
class Resolved:
    """El modelo con el que responde un agente y de dónde sale."""

    model_id: str
    source: Source
    #: Orígenes saltados porque no pueden ejecutar lo que el agente usa.
    skipped: tuple[str, ...] = ()


def resolve(
    choice: AgentChoice | None,
    version_override: str | None,
    platform_default: str,
    *,
    agent_needs: frozenset[str] = frozenset(),
    enabled: AbstractSet[str] | None = None,
) -> Resolved:
    """El modelo de respuesta de un agente. Pura: no lee nada.

    ``enabled``: lo habilitado para responder en este entorno. Si nada de la cadena puede
    con el agente, la reserva del modelo por defecto solo vale si está ahí; si no, el modelo
    por defecto, como hoy (/cso del 2026-11-20). ``None``: sin esa comprobación."""
    candidates: list[tuple[str, Source]] = []
    if choice is not None and choice.model_id:
        source: Source = "agent_operator" if choice.set_by == "operator" else "agent"
        candidates.append((choice.model_id, source))
    if version_override:
        candidates.append((version_override, "version"))
    candidates.append((platform_default, "platform"))

    skipped: list[str] = []
    for model_id, origin in candidates:
        if can_run(model_id, agent_needs):
            return Resolved(model_id, origin, tuple(skipped))
        skipped.append(model_id)

    profile = profile_for(platform_default)
    if (
        profile is not None
        and can_run(profile.reserve, agent_needs)
        and (enabled is None or profile.reserve in enabled)
    ):
        return Resolved(profile.reserve, "platform", tuple(skipped))
    return Resolved(platform_default, "platform", tuple(skipped))


def respond_reserve(
    model_id: str,
    *,
    enabled: AbstractSet[str],
    agent_needs: frozenset[str] = frozenset(),
    today: str | None,
) -> str | None:
    """La reserva del turno de ``model_id`` (research.md §D5, §D10; requisitos 11 y 4.8).

    - La de su perfil, que es de la otra familia, si está habilitada para responder en este
      entorno (``enabled``: la oferta, ``respond_enabled_at``) y puede con el agente.
    - Un agente con Skills o conector MCP de Anthropic solo puede caer a Anthropic: a Sonnet
      5.5, la única que tiene modo de cruce (``cross_in_request``), si no es él mismo.
    - Si no, la de hoy (``today``, Sol en producción), salvo que no pueda con el agente: una
      reserva que no puede ejecutarlo solo añadiría un intento fallido.
    - Un modelo sin perfil (heredado, CE-005) sigue con la de hoy.

    ``None``: sin reserva. Pura: no lee nada."""
    profile = profile_for(model_id)
    if profile is not None:
        candidates = [profile.reserve]
        if not can_run(profile.reserve, agent_needs):
            candidates = [SONNET_55]
        for candidate in candidates:
            if candidate != model_id and candidate in enabled and can_run(candidate, agent_needs):
                return candidate
    if not today or (agent_needs and not can_run(today, agent_needs)):
        return None
    return today


__all__ = ["AgentChoice", "Resolved", "SetBy", "Source", "resolve", "respond_reserve"]
