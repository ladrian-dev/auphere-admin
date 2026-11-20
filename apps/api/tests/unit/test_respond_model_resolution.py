"""Spec 065, T004 (requisitos 2.2 y 4.8): una sola resolución del modelo de respuesta.

El modelo con el que responde un agente se decide en este orden: su elección; si no, la de
su versión (``policies.llm.respond_model``, que escribe una plantilla de semilla); si no, el
modelo por defecto de Auphere de ese entorno (``platform_settings.agent_respond_default``).
Un origen que no puede ejecutar lo que el agente usa (Skills o conector MCP de Anthropic)
se salta. La asignación del cliente ya no es un escalón (requisito 12).

Y un barrido: los sitios que deciden el modelo de respuesta pasan por ``resolve()``, y nadie
lee el rol ``respond`` de ``tenant_model_bindings``.
"""

from __future__ import annotations

import re
from itertools import product
from pathlib import Path

import pytest

from nexus_api.core.respond_model import AgentChoice, Resolved, resolve

SOL = "openai/gpt-5.6-sol"
TERRA = "openai/gpt-5.6-terra"
LUNA = "openai/gpt-5.6-luna"
HAIKU = "anthropic/claude-haiku-5-5"
SONNET = "anthropic/claude-sonnet-5-5"
SKILLS = frozenset({"anthropic_skills"})


def test_the_agents_own_choice_wins() -> None:
    got = resolve(AgentChoice(TERRA, "partner"), LUNA, SOL)
    assert got == Resolved(TERRA, "agent")


def test_a_choice_made_by_auphere_says_so() -> None:
    assert resolve(AgentChoice(TERRA, "operator"), None, SOL) == Resolved(TERRA, "agent_operator")


def test_without_a_choice_the_version_decides() -> None:
    assert resolve(None, LUNA, SOL) == Resolved(LUNA, "version")


def test_without_choice_nor_version_auphere_default() -> None:
    assert resolve(None, None, SOL) == Resolved(SOL, "platform")
    assert resolve(None, None, HAIKU) == Resolved(HAIKU, "platform")


@pytest.mark.parametrize(
    ("choice", "version", "default"),
    list(product([None, AgentChoice(TERRA, "partner")], [None, LUNA], [SOL, HAIKU])),
)
def test_every_combination_of_gaps_picks_the_first_present(
    choice: AgentChoice | None, version: str | None, default: str
) -> None:
    got = resolve(choice, version, default)
    expected = (choice.model_id if choice else None) or version or default
    assert got.model_id == expected


def test_an_origin_that_cannot_run_the_skills_is_skipped() -> None:
    """Requisito 4.8: Terra no ejecuta Skills; responde el siguiente origen que pueda."""
    got = resolve(AgentChoice(TERRA, "partner"), None, HAIKU, agent_needs=SKILLS)
    assert got.model_id == HAIKU
    assert got.source == "platform"
    assert got.skipped == (TERRA,)


def test_if_no_origin_can_run_it_the_cross_family_reserve_answers() -> None:
    """Con Sol por defecto y Skills, la reserva de Sol (Sonnet 5.5) sí puede."""
    got = resolve(AgentChoice(TERRA, "partner"), None, SOL, agent_needs=SKILLS)
    assert got.model_id == SONNET
    assert got.skipped == (TERRA, SOL)


def test_a_model_without_profile_answers_as_today_when_nothing_is_needed() -> None:
    """Un modelo heredado sin perfil (Sonnet 4.6) sigue respondiendo (requisito 12.5)."""
    got = resolve(AgentChoice("anthropic/claude-sonnet-4-6", "operator"), None, SOL)
    assert got == Resolved("anthropic/claude-sonnet-4-6", "agent_operator")


# ── Barrido ─────────────────────────────────────────────────────────────────

_APPS = Path(__file__).resolve().parents[3]

#: Los sitios que deciden con qué modelo responde un agente. Cada uno pasa por ``resolve()``.
#: Crece con cada tarea que lleva la resolución a un sitio nuevo (tasks.md, T004).
DECIDERS = (
    "worker/src/nexus_worker/runtime/pipeline.py",
    "api/src/nexus_api/services/agent_model.py",
    # T081: el uso de un modelo (059) y el ciclo de vida, con la elección de cada agente.
    "api/src/nexus_api/services/model_lifecycle.py",
)

#: Leer el rol ``respond`` de las asignaciones de cliente: la resolución de antes.
_RESPOND_BINDING = re.compile(
    r"""bindings\.get\(\s*["']respond["']\s*\)|role\s*==\s*["']respond["']|"""
    # ``default_models()["respond"]`` es el uso de la plataforma, no una asignación de cliente.
    r"""(?<!default_models\(\))\[\s*["']respond["']\s*\]"""
)


@pytest.mark.parametrize("relative", DECIDERS)
def test_each_decider_goes_through_resolve(relative: str) -> None:
    text = (_APPS / relative).read_text(encoding="utf-8")
    assert "respond_model import" in text and "resolve" in text, (
        f"{relative} decide el modelo de respuesta sin nexus_api.core.respond_model.resolve"
    )


#: Sitios que todavía leen la asignación de cliente, con la tarea que los cambia. Cuando una
#: tarea los arregla, esta prueba falla hasta que salen de aquí: la lista no se queda vieja.
PENDING: dict[str, str] = {}

#: Los que nombran el rol sin leerlo, con el motivo.
ALLOWED: dict[str, str] = {
    "api/src/nexus_api/api/admin/model_bindings.py": "T034: rechaza el rol respond (422)",
}


def test_nobody_reads_the_clients_respond_binding() -> None:
    offenders = []
    for root in (_APPS / "api/src", _APPS / "worker/src"):
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "model_binding" not in text and "TenantModelBinding" not in text:
                continue
            if _RESPOND_BINDING.search(text):
                offenders.append(path.relative_to(_APPS).as_posix())
    offenders = [o for o in offenders if o not in ALLOWED]
    assert sorted(offenders) == sorted(PENDING), (
        f"leen la asignación de cliente del rol respond: {sorted(offenders)}; "
        f"pendientes declarados: {sorted(PENDING)}"
    )


# ── /cso 2026-11-20 (T093): un heredado de Anthropic y la reserva no habilitada ───────────

MCP = frozenset({"anthropic_mcp"})


def test_a_legacy_anthropic_choice_keeps_running_skills_and_mcp() -> None:
    """CE-005: la 0240 deja a un agente con MCP en Sonnet 4.6, que hoy los ejecuta. Al
    desplegar sigue igual, no salta al modelo por defecto ni a una reserva."""
    from nexus_api.core.respond_profiles import ANTHROPIC_MCP, ANTHROPIC_SKILLS, can_run

    legacy = "anthropic/claude-sonnet-4-6"
    assert can_run(legacy, frozenset({ANTHROPIC_MCP, ANTHROPIC_SKILLS}))
    assert not can_run("openai/gpt-4o", frozenset({ANTHROPIC_MCP}))
    got = resolve(
        AgentChoice(legacy, "operator"), None, SOL, agent_needs=frozenset({ANTHROPIC_MCP})
    )
    assert (got.model_id, got.source, got.skipped) == (legacy, "agent_operator", ())


def test_the_defaults_reserve_is_used_only_if_enabled() -> None:
    """Un agente con MCP sin elección: el modelo por defecto (Sol) no puede, y su reserva
    (Sonnet 5.5) solo vale si está habilitada para responder en el entorno. Si no, el de
    siempre, como hoy, en vez de un modelo que no pasó la batería."""
    from nexus_api.core.respond_profiles import ANTHROPIC_MCP

    needs = frozenset({ANTHROPIC_MCP})
    off = resolve(None, None, SOL, agent_needs=needs, enabled=frozenset({SOL, TERRA, LUNA}))
    assert (off.model_id, off.source) == (SOL, "platform")
    on = resolve(None, None, SOL, agent_needs=needs, enabled=frozenset({SOL, SONNET}))
    assert (on.model_id, on.source) == (SONNET, "platform")
