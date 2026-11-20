"""El perfil de llamada de cada modelo que puede responder — spec 065 (research.md §D12).

La única fuente de **cómo se llama** a un modelo: los parámetros que necesita con
herramientas, el razonamiento, ``max_tokens``, el plazo, su reserva de la otra familia y lo
que nunca se le manda. La base (``model_profiles``) guarda lo comercial y de operación:
precio, estado, oferta, habilitación y residencia. Cómo se llama depende de la versión de
LiteLLM y de la API del proveedor, que cambian con un despliegue, no con un dato.

Reglas:

- Un modelo sin perfil no se ofrece, no se habilita y no es reserva.
- Un modelo sin perfil que ya responde hoy por una asignación de cliente (Sonnet 4.6,
  Haiku 4.5) sigue con el comportamiento de hoy, byte a byte (CE-005).

Lo lee también el worker (depende de ``nexus-api``). ``test_respond_profiles_cover_the_catalog``
falla si falta un perfil.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Final, Literal

Family = Literal["openai", "anthropic"]

#: Lo que un modelo sabe ejecutar además de herramientas (requisito 4.8).
ANTHROPIC_SKILLS: Final = "anthropic_skills"
ANTHROPIC_MCP: Final = "anthropic_mcp"

#: La beta que acepta ``thinking.block_binding`` (research.md §D4).
BLOCK_BINDING_BETA: Final = "thinking-binding-controls-2026-08-01"

#: Un ``tool_choice`` que obliga a usar una herramienta (``any`` o una concreta).
FORCED_TOOL_CHOICE: Final = "tool_choice_forced"

SONNET_55: Final = "anthropic/claude-sonnet-5-5"
TERRA: Final = "openai/gpt-5.6-terra"


def _frozen(value: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    return None if value is None else MappingProxyType(dict(value))


@dataclass(frozen=True)
class RespondProfile:
    """Cómo se le pide una respuesta con herramientas a un modelo."""

    model_id: str
    family: Family
    #: Los kwargs que necesita con herramientas (research.md §D3-D4). Los de Claude van
    #: también sin herramientas; los de GPT-5.6, solo con ellas (sin herramientas sale como
    #: hoy).
    request: Mapping[str, Any]
    #: Lo que nunca se le manda.
    forbidden: frozenset[str]
    #: Si sus bloques de razonamiento vuelven en la siguiente llamada del turno.
    keeps_reasoning: bool
    timeout_s: float
    #: El techo de salida, con el razonamiento dentro. ``None``: el de hoy.
    max_tokens: int | None
    #: La reserva de la otra familia (research.md §D5).
    reserve: str
    #: Lo que se manda cuando entra como reserva tras herramientas de otra familia.
    cross_in_request: Mapping[str, Any] | None = None
    #: Para los que razonan: qué hacer si lo enviado cambió. Nunca junto a ``between_tools``.
    block_binding: Mapping[str, Any] | None = None
    #: Lo que lleva además una llamada del turno de respuesta, y no una tarea del router
    #: (``apply_capabilities`` solo aplica ``request``: así un ``classify`` enrutado a Haiku
    #: 5.5 conserva su ``thinking: disabled``). Para Claude 5.5: razonamiento adaptativo y
    #: la caché automática de la conversación (§D4, §D14).
    turn_request: Mapping[str, Any] | None = None
    #: Lo que gasta frente a Sol para el mismo trabajo (razonamiento, tokenizador). Solo entra
    #: en el precio estimado del selector; se cobra siempre lo gastado. 1,0 en GPT-5.6; en
    #: Claude, provisional desde la batería real (T103).
    estimate_factor: float = 1.0
    supports: frozenset[str] = field(default_factory=frozenset)


#: ``mcp_servers`` (con el token del servidor MCP del cliente) y ``container`` (sus Skills)
#: son de Anthropic: hacia OpenAI, LiteLLM los metería en el cuerpo (/cso del 2026-11-20).
_OPENAI_FORBIDDEN = frozenset(
    {
        "thinking",
        "output_config",
        "context_management",
        "cache_control",
        "temperature",
        "mcp_servers",
        "container",
    }
)
_ANTHROPIC_FORBIDDEN = frozenset({"temperature", "top_p", "top_k", "reasoning_effort"})
_ANTHROPIC_RUNS = frozenset({ANTHROPIC_SKILLS, ANTHROPIC_MCP})
_DROP_BLOCK = {"prefix_mismatch_behavior": "drop_block"}


def _gpt56(model_id: str) -> RespondProfile:
    return RespondProfile(
        model_id=model_id,
        family="openai",
        # Con herramientas, Chat Completions exige el razonamiento apagado; viaja en
        # ``extra_body`` para que LiteLLM no desvíe la llamada a ``/responses`` (§D3).
        request=MappingProxyType({"extra_body": {"reasoning_effort": "none"}}),
        forbidden=_OPENAI_FORBIDDEN,
        keeps_reasoning=False,
        timeout_s=30,
        max_tokens=None,
        reserve=SONNET_55,
    )


def _claude55(
    model_id: str,
    *,
    timeout_s: float,
    forced_tool_choice: bool,
    estimate_factor: float,
    cross_in_request: Mapping[str, Any] | None = None,
) -> RespondProfile:
    forbidden = _ANTHROPIC_FORBIDDEN | ({FORCED_TOOL_CHOICE} if not forced_tool_choice else set())
    return RespondProfile(
        model_id=model_id,
        family="anthropic",
        # El esfuerzo como ``output_config`` y no como ``reasoning_effort``: este último lo
        # traduce LiteLLM a su propio ``thinking`` (§D3).
        request=MappingProxyType({"output_config": {"effort": "low"}}),
        # Razonamiento adaptativo: el transporte le pone ``block_binding`` (o lo cambia por
        # ``cross_in_request`` en un cruce). ``cache_control`` arriba es la caché automática
        # de la conversación, que no toca los mensajes; la marca fija del ``system`` la pone
        # el transporte (§D14).
        turn_request=_frozen(
            {"thinking": {"type": "adaptive"}, "cache_control": {"type": "ephemeral"}}
        ),
        forbidden=frozenset(forbidden),
        keeps_reasoning=True,
        timeout_s=timeout_s,
        max_tokens=8192,
        reserve=TERRA,
        cross_in_request=_frozen(cross_in_request),
        block_binding=_frozen(_DROP_BLOCK),
        estimate_factor=estimate_factor,
        supports=_ANTHROPIC_RUNS,
    )


PROFILES: Final[Mapping[str, RespondProfile]] = MappingProxyType(
    {
        p.model_id: p
        for p in (
            _gpt56("openai/gpt-5.6-sol"),
            _gpt56("openai/gpt-5.6-terra"),
            _gpt56("openai/gpt-5.6-luna"),
            # ``estimate_factor`` de los Claude: **provisional** (T103). Medido en la batería real
            # del 2026-11-20 con el agente de prueba, sobre los tokens de las llamadas de turno
            # del propio modelo frente a Sol y con la salida a 5 veces la entrada (quickstart.md
            # §3). No es un techo: con prompts largos en caché pesa más la salida, y la de Claude
            # fue de 2,6 a 4,8 veces la de Sol. Revisar con un agente de tamaño real, carril a
            # carril, antes de habilitar Claude en prod.
            #
            # Opus 5.5 no deja apagar el razonamiento: nunca es la reserva del cruce.
            _claude55(
                "anthropic/claude-opus-5-5",
                timeout_s=90,
                forced_tool_choice=False,
                estimate_factor=1.9,
            ),
            # Sonnet 5.5 es la reserva de OpenAI: tras herramientas de GPT-5.6 entra con el
            # razonamiento apagado, sin ``block_binding`` (§D5.4).
            _claude55(
                SONNET_55,
                timeout_s=60,
                forced_tool_choice=False,
                estimate_factor=1.8,
                cross_in_request={"thinking": {"type": "between_tools"}},
            ),
            _claude55(
                "anthropic/claude-haiku-5-5",
                timeout_s=45,
                forced_tool_choice=True,
                estimate_factor=2.6,
            ),
        )
    }
)


def profile_for(model_id: str) -> RespondProfile | None:
    """El perfil de ``model_id``, o ``None`` si no puede responder con perfil."""
    return PROFILES.get(model_id)


def can_run(model_id: str, needs: frozenset[str]) -> bool:
    """Si ``model_id`` puede ejecutar lo que el agente usa (requisito 4.8).

    Un modelo sin perfil puede con un agente que no necesita nada especial: es el caso de
    los heredados que responden hoy (requisito 12.5). Uno heredado de Anthropic (Sonnet 4.6,
    Haiku 4.5) ejecuta también Skills y MCP, como hoy: la 0240 deja a esos agentes en él y
    al desplegar no cambian (CE-005; /cso del 2026-11-20)."""
    if not needs:
        return True
    profile = profile_for(model_id)
    if profile is None:
        return model_id.startswith("anthropic/")
    return needs <= profile.supports


__all__ = [
    "ANTHROPIC_MCP",
    "ANTHROPIC_SKILLS",
    "BLOCK_BINDING_BETA",
    "FORCED_TOOL_CHOICE",
    "PROFILES",
    "RespondProfile",
    "can_run",
    "profile_for",
]
