"""Spec 065: la reserva de la otra familia a mitad de turno.

- T051 (requisitos 4.4, 4.5, 11.1, 11.3, 11.4), en las dos direcciones (Opus → Terra y
  Sol → Sonnet 5.5): la segunda llamada falla y la reserva termina el turno; la tercera sigue
  con la reserva; ninguna herramienta se ejecuta dos veces; el cliente recibe la respuesta;
  con todo caído, la frase de siempre; la cadena es elegido → reserva de la otra familia,
  sin reservas propias de cliente.
- T054 (requisito 4.8): un agente con Skills de Anthropic responde con el siguiente origen
  que pueda, y su reserva es de Anthropic: nunca cae a OpenAI.
- T056 (requisitos 11.1 y 11.2): la reserva del perfil solo si está habilitada para
  responder en este entorno; si no, la de hoy (Sol), como hoy.

Sin proveedor real: ``InMemoryProvider`` con un guion por modelo y los cargadores del grafo
sustituidos (``world`` de ``test_pipeline_router``).
"""

from __future__ import annotations

import dataclasses
import json
from collections import Counter
from collections.abc import Iterator
from typing import Any

import pytest
from nexus_api.core import respond_catalog
from nexus_api.core.respond_model import respond_reserve
from nexus_api.core.respond_profiles import PROFILES, SONNET_55, TERRA

import nexus_worker.runtime.llm as llm_module
import nexus_worker.runtime.pipeline as pipeline
from nexus_worker.runtime.agent_loader import AgentBundle
from nexus_worker.runtime.llm import InMemoryProvider, LLMCall, ToolCall
from tests.unit.test_pipeline_router import (  # noqa: F401
    TOOL,
    _bundle,
    _turn,
    world,
)

SOL = "openai/gpt-5.6-sol"
LUNA = "openai/gpt-5.6-luna"
OPUS = "anthropic/claude-opus-5-5"
HAIKU = "anthropic/claude-haiku-5-5"
TODAY = "legacy/fallback"  # la reserva de hoy del router de prueba (Sol en producción)
TEXT = "Te reservo el martes a las 10."
SKILLS = frozenset({"anthropic_skills"})


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_module, "_RETRY_BACKOFF_S", 0.0)


@pytest.fixture
def enabled() -> Iterator[Any]:
    """Habilita para responder los modelos que se pidan; al acabar, la semilla."""

    def enable(*models: str) -> None:
        rows = [
            {
                "model_id": m,
                "status": "active",
                "offer_label": m,
                "price_input_per_mtok": 1,
                "respond_enabled_at": "2026-11-20" if m in models else None,
            }
            for m in PROFILES
        ]
        assert respond_catalog.refresh_from_rows(rows)

    yield enable
    respond_catalog.reset()


def _scripted(
    *, fail: dict[str, set[int] | None], tools: int = 2, refuse: frozenset[str] = frozenset()
) -> InMemoryProvider:
    """Un modelo por guion: llama a ``tools`` herramientas seguidas y luego contesta.

    ``fail[model]`` son los intentos (1, 2, …) en los que ese modelo falla; ``None``, todos.
    Claude devuelve un bloque de razonamiento firmado con cada respuesta. ``tried``: cada
    intento, también los que fallan (``calls`` solo guarda los que llegan a responder)."""
    provider = InMemoryProvider()
    attempts: Counter[str] = Counter()
    tried: list[str] = []

    def responder(call: LLMCall) -> str:
        return "info" if call.role == "classify" else TEXT

    def tool_caller(call: LLMCall) -> list[ToolCall]:
        if call.extra.get("tool_choice") == "none":
            return []
        done = sum(1 for m in call.messages if m.get("role") == "tool")
        if done >= tools:
            return []
        return [ToolCall(id=f"t{done + 1}", name=TOOL, arguments={})]

    provider.responder = responder
    provider.tool_caller = tool_caller
    original = provider.acomplete_with_tools

    async def acomplete_with_tools(**kwargs: Any) -> Any:
        model = kwargs["model"]
        attempts[model] += 1
        tried.append(model)
        failing = fail.get(model, set())
        if model in fail and (failing is None or attempts[model] in failing):
            error = type("ServiceUnavailableError", (Exception,), {})
            raise error(f"{model} is down")
        response = await original(**kwargs)
        if model in refuse:
            raise llm_module.ProviderRefused(model)
        if model.startswith("anthropic/"):
            block = {"type": "thinking", "thinking": "…", "signature": f"{model}#{attempts[model]}"}
            response = dataclasses.replace(response, reasoning_blocks=(block,))
        return response

    provider.acomplete_with_tools = acomplete_with_tools  # type: ignore[method-assign]
    provider.tried = tried  # type: ignore[attr-defined]
    return provider


def _chosen(model_id: str, **more: Any) -> AgentBundle:
    return dataclasses.replace(
        _bundle(tools=frozenset({TOOL})),
        respond_model=model_id,
        respond_model_set_by="partner",
        **more,
    )


def _answering(provider: InMemoryProvider) -> list[LLMCall]:
    return [c for c in provider.calls if c.role != "classify"]


def _models(provider: InMemoryProvider) -> list[str]:
    return list(provider.tried)  # type: ignore[attr-defined]


# ── T051: la reserva termina el turno ──────────────────────────────────────


@pytest.mark.parametrize(
    ("chosen", "reserve", "enable"),
    [(OPUS, TERRA, ()), (SOL, SONNET_55, (SONNET_55,))],
    ids=["opus_a_terra", "sol_a_sonnet"],
)
async def test_the_reserve_finishes_the_turn_after_a_mid_turn_failure(
    world: Any,  # noqa: F811
    enabled: Any,
    chosen: str,
    reserve: str,
    enable: tuple[str, ...],
) -> None:
    world.catalog = None
    if enable:
        enabled(*enable)
    # La segunda llamada del elegido falla (sus dos intentos); la tercera ya no fallaría.
    provider = _scripted(fail={chosen: {2, 3}})
    out = await _turn(_chosen(chosen), provider)

    # 1.ª llamada: el elegido; 2.ª: el elegido dos veces y la reserva; 3.ª: la reserva.
    assert _models(provider) == [chosen, chosen, chosen, reserve, reserve]
    assert [c.id for c in world.dispatched] == ["t1", "t2"], "ninguna herramienta dos veces"
    assert out["response"] == TEXT
    assert out["response_model"] == reserve
    assert out["response_fell_back"] is True
    assert TODAY not in _models(provider), "sin la reserva de hoy detrás"


async def test_falling_to_terra_leaves_claudes_reasoning_behind(
    world: Any,  # noqa: F811
) -> None:
    world.catalog = None
    provider = _scripted(fail={OPUS: {3, 4}}, tools=3)
    await _turn(_chosen(OPUS), provider)
    assert _models(provider) == [OPUS, OPUS, OPUS, OPUS, TERRA, TERRA]
    for call in _answering(provider):
        carried = json.dumps(call.messages, default=str)
        assert "nexus_served_by" not in carried
        if call.model == TERRA:
            assert "thinking_blocks" not in carried and "signature" not in carried
    second = [c for c in _answering(provider) if c.model == OPUS][-1]
    [assistant] = [m for m in second.messages if m.get("role") == "assistant"]
    assert assistant["thinking_blocks"] == [
        {"type": "thinking", "thinking": "…", "signature": f"{OPUS}#1"}
    ], "a Opus le vuelve su bloque"


async def test_sonnet_crossing_after_gpt_tools_reasons_off_the_rest_of_the_turn(
    world: Any,  # noqa: F811
    enabled: Any,
) -> None:
    world.catalog = None
    enabled(SONNET_55)
    provider = _scripted(fail={SOL: {2, 3}})
    await _turn(_chosen(SOL), provider)
    sonnet = [c for c in _answering(provider) if c.model == SONNET_55]
    assert len(sonnet) == 2
    for call in sonnet:
        assert call.extra["thinking"] == {"type": "between_tools"}
        headers = call.extra.get("extra_headers") or {}
        assert "thinking-binding" not in str(headers)
    # Su bloque de progreso vuelve a Sonnet; el turno de GPT no lleva ninguno.
    assistants = [m for m in sonnet[1].messages if m.get("role") == "assistant"]
    assert "thinking_blocks" not in assistants[0]
    assert assistants[1]["thinking_blocks"][0]["signature"] == f"{SONNET_55}#1"


async def test_with_everything_down_the_customer_gets_the_usual_phrase(
    world: Any,  # noqa: F811
) -> None:
    world.catalog = None
    provider = _scripted(fail={OPUS: None, TERRA: None})
    out = await _turn(_chosen(OPUS), provider)
    assert out["response"] == pipeline._EMPTY_RESPONSE_FALLBACK
    assert out["turn_failure"]["kind"] == "llm_failed"
    # La cadena: el elegido y la reserva de la otra familia, dos intentos cada uno. Nada más.
    assert _models(provider) == [OPUS, OPUS, TERRA, TERRA]


async def test_a_refusal_goes_to_the_reserve_without_a_second_try(
    world: Any,  # noqa: F811
) -> None:
    world.catalog = None
    provider = _scripted(fail={}, refuse=frozenset({OPUS}), tools=0)
    out = await _turn(_chosen(OPUS), provider)
    assert _models(provider) == [OPUS, TERRA]
    assert (out["response"], out["response_model"]) == (TEXT, TERRA)


# ── T056: la reserva, solo si está habilitada ──────────────────────────────


@pytest.mark.parametrize(
    ("chosen", "enable", "served"),
    [
        (LUNA, (), TODAY),  # Sonnet 5.5 sin habilitar (como al desplegar): Sol, como hoy
        (LUNA, (SONNET_55,), SONNET_55),
        (OPUS, (OPUS,), TODAY),  # Terra deshabilitada en este entorno
        (OPUS, (OPUS, TERRA), TERRA),
    ],
)
async def test_the_profiles_reserve_only_when_enabled_else_today(
    world: Any,  # noqa: F811
    enabled: Any,
    chosen: str,
    enable: tuple[str, ...],
    served: str,
) -> None:
    world.catalog = None
    enabled(*enable)
    provider = _scripted(fail={chosen: None}, tools=0)
    out = await _turn(_chosen(chosen), provider)
    assert _models(provider) == [chosen, chosen, served]
    assert out["response_model"] == served


@pytest.mark.parametrize(
    ("model", "enabled_", "needs", "today", "expected"),
    [
        (SOL, {SONNET_55}, frozenset(), SOL, SONNET_55),
        (SOL, set(), frozenset(), SOL, SOL),
        (OPUS, {TERRA}, frozenset(), SOL, TERRA),
        (OPUS, set(), frozenset(), SOL, SOL),
        (HAIKU, {TERRA, SONNET_55}, frozenset(), SOL, TERRA),
        # Con Skills, la reserva es de Anthropic: Sonnet 5.5, la que tiene modo de cruce.
        (OPUS, {TERRA, SONNET_55}, SKILLS, SOL, SONNET_55),
        (OPUS, {TERRA}, SKILLS, SOL, None),
        (SONNET_55, {TERRA, SONNET_55}, SKILLS, SOL, None),
        # Un heredado sin perfil sigue con la de hoy (CE-005).
        ("anthropic/claude-sonnet-4-6", {TERRA, SONNET_55}, frozenset(), SOL, SOL),
        # Sin reserva de hoy (las simulaciones), nada.
        (OPUS, set(), frozenset(), "", None),
    ],
)
def test_the_reserve_rule(
    model: str, enabled_: set[str], needs: frozenset[str], today: str, expected: str | None
) -> None:
    got = respond_reserve(model, enabled=frozenset(enabled_), agent_needs=needs, today=today)
    assert got == expected


# ── T054: lo que el modelo elegido no puede ejecutar ───────────────────────


def _with_skills(**more: Any) -> AgentBundle:
    return _chosen(
        TERRA,
        runtime_skills=({"skill_id": "pdf", "version": "1"},),
        policies={"llm": {"respond_model": OPUS}},
        **more,
    )


async def test_an_agent_with_skills_answers_with_the_next_source_that_can(
    world: Any,  # noqa: F811
) -> None:
    world.catalog = None
    provider = _scripted(fail={}, tools=0)
    out = await _turn(_with_skills(), provider)
    assert _models(provider) == [OPUS], "Terra no ejecuta Skills: responde la versión"
    assert out["response_model"] == OPUS
    beta = _answering(provider)[0].extra["extra_headers"]["anthropic-beta"].split(",")
    assert "skills-2025-10-02" in beta and "thinking-binding-controls-2026-08-01" in beta


@pytest.mark.parametrize(
    ("enable", "expected"),
    [((OPUS, TERRA), [OPUS, OPUS]), ((OPUS, TERRA, SONNET_55), [OPUS, OPUS, SONNET_55])],
    ids=["sin_sonnet_ninguna", "con_sonnet"],
)
async def test_its_reserve_is_anthropic_never_openai(
    world: Any,  # noqa: F811
    enabled: Any,
    enable: tuple[str, ...],
    expected: list[str],
) -> None:
    world.catalog = None
    enabled(*enable)
    provider = _scripted(fail={OPUS: None}, tools=0)
    await _turn(_with_skills(), provider)
    assert _models(provider) == expected


async def test_a_skills_agent_on_claude_only_appends_up_to_the_close(
    world: Any,  # noqa: F811
) -> None:
    """Research §D4.2: la segunda cosa que rompía «solo se añade» era quitar
    ``code_execution`` en el cierre. Con Claude, el cierre conserva las herramientas y el
    contenedor de Skills, y solo añade ``tool_choice: none``; sin la nota del cierre."""
    world.catalog = None
    provider = _scripted(fail={}, tools=99)
    out = await _turn(_with_skills(), provider)
    calls = _answering(provider)
    assert len(calls) == pipeline.MAX_TOOL_ITERATIONS
    assert {c.model for c in calls} == {OPUS}
    first, closing = calls[0], calls[-1]
    assert any(t.get("type", "").startswith("code_execution") for t in closing.tools)
    assert closing.tools == first.tools
    assert closing.extra["container"] == first.extra["container"]
    assert set(closing.extra) - set(first.extra) == {"tool_choice"}
    assert closing.extra["tool_choice"] == "none"
    assert closing.messages[: len(first.messages)] == first.messages
    assert pipeline.FINAL_ANSWER_NOTE not in json.dumps(closing.messages, ensure_ascii=False)
    assert out["response"] == TEXT


async def test_a_skills_agent_falling_from_opus_to_sonnet_leaves_opus_blocks_behind(
    world: Any,  # noqa: F811
    enabled: Any,
) -> None:
    """Dentro de Anthropic también: los bloques de Opus no van a Sonnet, y Sonnet entra
    tras herramientas de otro modelo con el razonamiento apagado."""
    world.catalog = None
    enabled(OPUS, TERRA, SONNET_55)
    provider = _scripted(fail={OPUS: {2, 3}})
    out = await _turn(_with_skills(), provider)
    assert _models(provider) == [OPUS, OPUS, OPUS, SONNET_55, SONNET_55]
    sonnet = [c for c in _answering(provider) if c.model == SONNET_55]
    for call in sonnet:
        assert call.extra["thinking"] == {"type": "between_tools"}
        assert "container" in call.extra, "las Skills siguen con Sonnet"
        [opus_turn, *_] = [m for m in call.messages if m.get("role") == "assistant"]
        assert "thinking_blocks" not in opus_turn
    assert out["response_model"] == SONNET_55
