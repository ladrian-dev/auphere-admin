"""El transporte se adapta a las capacidades del despliegue (spec 047, T137).

Requisitos 41.3 y 41.4. Lo que sale hacia el proveedor se mira **en el sitio
donde sale**: ``litellm.acompletion`` interceptado, sin red. Cada despliegue de
prueba declara sus capacidades como lo haría una fila del catálogo; la llamada
va enrutada (``routed(hop)``), que es como la hará el router.

Una llamada **sin** salto enrutado —todo el código de hoy— no cambia: lo cubren
``test_llm_resilience``, ``test_litellm_proxy`` y ``test_prompt_cache_breakpoints``.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from nexus_api.core import respond_catalog
from nexus_api.services.router_catalog import Deployment, MissingTask
from structlog.testing import capture_logs

from nexus_worker.runtime import llm as llm_module
from nexus_worker.runtime.llm import (
    InMemoryProvider,
    LiteLLMProvider,
    LLMRouter,
    RetentionNotGuaranteed,
    RouteHop,
    StructuredOutputInvalid,
    UnknownRetention,
    routed,
)
from nexus_worker.runtime.model_resolver import (
    ClassifyResult,
    RouteContext,
    TurnBudget,
    cache_key_for,
    chain_for,
    turn_budget,
)
from tests.unit._router_world import TENANT, cert, dep, profile, snapshot

EXPLICIT = dep(
    "anthropic/claude-haiku-9",
    provider="anthropic",
    caps={
        "cache_mode": "explicit",
        "tool_name_charset": "dotted_ok",
        "reasoning_control": "budget",
    },
)
GEMINI = dep(
    "gemini/gemini-9-flash",
    provider="google",
    family="google-gemini",
    retention_how="store=false",
    caps={"cache_mode": "implicit", "tool_name_charset": "no_dots", "reasoning_control": "none"},
)
OPEN = dep(
    "mistral/open-9",
    provider="prov_m",
    family="mistral",
    retention_how="store=false",
    caps={
        "cache_mode": "none",
        "tool_name_charset": "no_dots",
        "strict_structured_outputs": False,
        "structured_outputs": True,
        "reasoning_control": "none",
    },
)
OPENAI = dep(
    "openai/gpt-9-mini",
    provider="openai",
    family="openai-gpt",
    retention_how="store=false",
    caps={
        "cache_mode": "implicit",
        "cache_key": True,
        "tool_name_charset": "no_dots",
        "reasoning_control": "effort",
    },
)
LEAKY = dep("prov-x/leaky", provider="prov_x", zero_retention=False)
STRANGE = dep("prov-y/strange", provider="prov_y", retention_how="magic:on")
ALL = (EXPLICIT, GEMINI, OPEN, OPENAI, LEAKY, STRANGE)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "client.get_history",
            "description": "historial",
            "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "parameters": {"properties": {"day": {"type": "string"}}, "type": "object"},
            "name": "booking.check_availability",
            "description": "huecos",
        },
    },
]
MESSAGES = [
    {"role": "system", "content": "Eres el agente."},
    {"role": "user", "content": "hola"},
]


@pytest.fixture(autouse=True)
def _catalog_knows_the_test_deployments() -> Iterator[None]:
    """El hop solo acepta ids del catálogo, que ahora sale de los datos: las
    filas de prueba entran como entraría una fila nueva de ``model_profiles``."""
    respond_catalog.refresh_from_rows(
        [{"model_id": d.key, "status": "active", "offer_label": None} for d in ALL]
    )
    yield
    respond_catalog.reset()


@pytest.fixture
def wire(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    import litellm

    sent: list[dict[str, Any]] = []

    async def fake_acompletion(**kwargs: Any) -> dict[str, Any]:
        sent.append(json.loads(json.dumps(kwargs, default=str)))
        names = [t["function"]["name"] for t in kwargs.get("tools") or []]
        calls = [
            {"id": "c1", "type": "function", "function": {"name": n, "arguments": "{}"}}
            for n in names[:1]
        ]
        return {
            "choices": [{"message": {"content": '{"ok": true}', "tool_calls": calls}}],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 100},
        }

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
    return sent


def _hop(deployment: Deployment, **over: Any) -> RouteHop:
    base: dict[str, Any] = {
        "task": "tool_turn",
        "deployment": deployment,
        "decision_id": uuid.uuid4(),
        "reasoning": "none",
    }
    base.update(over)
    return RouteHop(**base)


async def _call(deployment: Deployment, *, tools: bool = True, **hop: Any) -> Any:
    provider = LiteLLMProvider(context_management=None)
    with routed(_hop(deployment, **hop)):
        if tools:
            return await provider.acomplete_with_tools(
                tenant_id=TENANT, role="book", model=deployment.key, messages=MESSAGES, tools=TOOLS
            )
        return await provider.acomplete(
            tenant_id=TENANT, role="classify", model=deployment.key, messages=MESSAGES
        )


# ── caché ───────────────────────────────────────────────────────────────────


async def test_cache_marks_only_where_the_provider_takes_them(wire) -> None:
    await _call(EXPLICIT)
    assert "cache_control" in json.dumps(wire[-1]["messages"])
    for implicit_or_none in (GEMINI, OPEN):
        await _call(implicit_or_none)
        assert "cache_control" not in json.dumps(wire[-1]), implicit_or_none.key
    # En Gemini, solo la implícita: el prefijo va tal cual, sin bloques marcados.
    assert wire[-2]["messages"][0] == MESSAGES[0]


async def test_the_cache_key_is_per_client_and_version_where_there_is_one(wire) -> None:
    key_a = cache_key_for(TENANT, "v3")
    key_b = cache_key_for(uuid.uuid4(), "v3")
    assert key_a != key_b and key_a != cache_key_for(TENANT, "v4")
    await _call(OPENAI, cache_key=key_a)
    assert wire[-1]["prompt_cache_key"] == key_a
    await _call(EXPLICIT, cache_key=key_a)
    assert "prompt_cache_key" not in wire[-1], "Anthropic no tiene clave de caché"


# ── nombres con punto ───────────────────────────────────────────────────────


async def test_dotted_tool_names_are_translated_for_every_provider_without_dots(wire) -> None:
    for no_dots in (GEMINI, OPEN, OPENAI):
        result = await _call(no_dots)
        names = {t["function"]["name"] for t in wire[-1]["tools"]}
        assert names == {"client__get_history", "booking__check_availability"}, no_dots.key
        # Y la respuesta vuelve con los nombres del catálogo.
        assert all("." in tc.name for tc in result.tool_calls), result.tool_calls
    await _call(EXPLICIT)
    assert {t["function"]["name"] for t in wire[-1]["tools"]} == {
        "client.get_history",
        "booking.check_availability",
    }


# ── salidas estructuradas ───────────────────────────────────────────────────


SCHEMA = ClassifyResult.model_json_schema()


async def test_strict_structured_outputs_where_they_exist(wire) -> None:
    await _call(
        EXPLICIT, tools=False, task="classify", response_schema=SCHEMA, schema_name="classify"
    )
    fmt = wire[-1]["response_format"]
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["strict"] is True
    assert fmt["json_schema"]["name"] == "classify"
    await _call(OPEN, tools=False, task="classify", response_schema=SCHEMA)
    assert wire[-1]["response_format"] == {"type": "json_object"}
    await _call(GEMINI, tools=False, task="classify", response_schema=SCHEMA)
    assert wire[-1]["response_format"]["json_schema"]["strict"] is True


async def test_our_own_validation_runs_always_even_when_strict(wire) -> None:
    world = snapshot([EXPLICIT], [cert(EXPLICIT, "classify")], profile())
    decision = chain_for(
        "classify",
        profile(),
        RouteContext(tenant_id=TENANT, catalog=world, eu_only=True, now=1.0),
    )
    router = LLMRouter(
        provider=LiteLLMProvider(context_management=None),
        classify_model="x",
        respond_model="x",
        fallback_model="",
    )
    # El proveedor «estricto» devuelve un JSON que no es un ClassifyResult.
    with pytest.raises(StructuredOutputInvalid):
        await router.complete_structured(
            decision=decision, tenant_id=TENANT, messages=MESSAGES, output=ClassifyResult
        )
    assert wire[-1]["response_format"]["json_schema"]["strict"] is True


# ── retención ───────────────────────────────────────────────────────────────


async def test_retention_store_false_and_data_retention_mode_none(wire) -> None:
    await _call(GEMINI)
    assert wire[-1]["store"] is False
    await _call(EXPLICIT)
    assert wire[-1]["data_retention_mode"] == "none"
    assert "store" not in wire[-1]


async def test_a_retention_the_transport_cannot_apply_never_leaves(wire) -> None:
    with pytest.raises(UnknownRetention):
        await _call(STRANGE)
    with pytest.raises(RetentionNotGuaranteed):
        await _call(LEAKY)
    assert wire == [], "nada sale hacia un proveedor que puede guardar"


# ── razonamiento ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("deployment", "level", "expected"),
    [
        (OPENAI, "low", {"reasoning_effort": "low"}),
        (OPENAI, "none", {"reasoning_effort": "none"}),
        (EXPLICIT, "medium", {"thinking": {"type": "enabled", "budget_tokens": 4096}}),
        (EXPLICIT, "none", {}),
        (OPEN, "high", {}),
    ],
)
async def test_the_reasoning_level_goes_by_task(
    wire, deployment: Deployment, level: str, expected: dict[str, Any]
) -> None:
    await _call(deployment, tools=False, task="classify", reasoning=level)
    sent = wire[-1]
    got = {k: sent[k] for k in ("reasoning_effort", "thinking") if k in sent}
    assert got == expected


# ── prefijo estable ─────────────────────────────────────────────────────────


async def test_the_prefix_is_stable_tools_sorted_and_json_ordered(wire) -> None:
    await _call(EXPLICIT)
    first = wire[-1]["tools"]
    provider = LiteLLMProvider(context_management=None)
    shuffled = [json.loads(json.dumps(t)) for t in reversed(TOOLS)]
    with routed(_hop(EXPLICIT)):
        await provider.acomplete_with_tools(
            tenant_id=TENANT, role="book", model=EXPLICIT.key, messages=MESSAGES, tools=shuffled
        )
    assert wire[-1]["tools"] == first
    assert [t["function"]["name"] for t in first] == sorted(t["function"]["name"] for t in first)
    for tool in first:
        assert json.dumps(tool) == json.dumps(tool, sort_keys=True)


# ── medidor ─────────────────────────────────────────────────────────────────


@pytest.fixture
def metered(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(llm_module, "record_llm_usage", lambda **kw: seen.append(kw))
    return seen


async def test_a_routed_call_meters_its_task_and_its_decision(wire, metered) -> None:
    hop = _hop(OPENAI, task="tool_turn")
    provider = LiteLLMProvider(context_management=None)
    budget = TurnBudget(max_calls=12, cost_ceiling_micros=None)
    with turn_budget(budget), routed(hop):
        await provider.acomplete_with_tools(
            tenant_id=TENANT, role="book", model=OPENAI.key, messages=MESSAGES, tools=TOOLS
        )
    assert metered[-1]["task"] == "tool_turn"
    assert metered[-1]["route_decision_id"] == hop.decision_id
    assert metered[-1]["provider"] == "openai"
    assert budget.cost_micros > 0, "lo que gasta el turno entra en su techo"


@pytest.mark.parametrize(
    ("role", "tools", "task"),
    [
        ("classify", False, "classify"),
        ("grader", False, "judge"),
        ("book", True, "tool_turn"),
        ("info", False, "answer"),
        ("companion", True, "build"),
        # Spec 047 (requisito 15.7): the builder's draft job calls with role
        # ``build`` (``jobs/handlers/agent_draft.py``); without it in
        # ``TASK_BY_ROLE`` it logged ``llm.task_missing`` and was metered
        # without a task.
        ("build", False, "build"),
        ("build", True, "build"),
        # Spec 047, enmienda (61.1): el cliente simulado de las pruebas.
        ("customer_sim", False, "answer"),
    ],
)
async def test_calls_of_today_carry_a_task_too(
    wire, metered, role: str, tools: bool, task: str
) -> None:
    provider = LiteLLMProvider(context_management=None)
    model = "openai/gpt-9-mini"
    if tools:
        await provider.acomplete_with_tools(
            tenant_id=TENANT, role=role, model=model, messages=MESSAGES, tools=TOOLS
        )
    else:
        await provider.acomplete(tenant_id=TENANT, role=role, model=model, messages=MESSAGES)
    assert metered[-1]["task"] == task
    assert metered[-1]["route_decision_id"] is None


async def test_a_call_without_task_is_an_anomaly_and_fails_under_strict(wire, metered) -> None:
    provider = LiteLLMProvider(context_management=None)
    with capture_logs() as logs:
        await provider.acomplete(
            tenant_id=TENANT, role="mystery", model=OPENAI.key, messages=MESSAGES
        )
    assert metered[-1]["task"] is None
    assert any(e["event"] == "llm.task_missing" and e["role"] == "mystery" for e in logs)

    strict = LiteLLMProvider(context_management=None, require_task=True)
    calls = len(wire)
    with pytest.raises(MissingTask):
        await strict.acomplete(
            tenant_id=TENANT, role="mystery", model=OPENAI.key, messages=MESSAGES
        )
    assert len(wire) == calls, "sin tarea no sale nada"


async def test_the_in_memory_double_sees_the_hop_too() -> None:
    """Los tests del grafo (C3) usan el doble: tiene que ver la tarea."""
    provider = InMemoryProvider()
    with routed(_hop(OPENAI, task="answer")):
        await provider.acomplete(tenant_id=TENANT, role="info", model=OPENAI.key, messages=MESSAGES)
    assert provider.calls[-1].extra["task"] == "answer"
