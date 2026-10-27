"""La elección del router, con un catálogo de prueba (spec 047, T136).

Requisitos 40.1 a 40.12. La política vive en ``model_resolver.chain_for(task,
profile, ctx)`` (research D20): filtro duro, calidad certificada, orden por
precio dentro de la latencia, cadena con dos alternativas y registro. LiteLLM
solo transporta. Ninguna prueba sale a un proveedor: el catálogo es de pago y
aquí es de mentira (``_router_world``).
"""

from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from nexus_api.core.errors import IsolationViolation
from nexus_api.services.router_catalog import MissingTask, TokenEstimate, UnknownTask
from structlog.testing import capture_logs

from nexus_worker.runtime.llm import (
    ROUTE_DECISION_EVENT,
    CooldownBook,
    InMemoryProvider,
    LLMCall,
    LLMRouter,
    NoModelAvailable,
    ProviderChainExhausted,
    litellm_kwargs_contract,
)
from nexus_worker.runtime.model_resolver import (
    PIN_MIN_TTL_S,
    ClassifyResult,
    PinnedModel,
    RouteContext,
    RouteHint,
    TurnBudget,
    TurnLimitReached,
    TurnSignals,
    chain_for,
    escalation_for,
    parse_classification,
    pin_after,
    pins_from_state,
    record_escalation,
    turn_budget,
    with_pin,
)
from tests.unit._router_world import (
    AGENT,
    NEIGHBOUR,
    SIBLING,
    TENANT,
    cert,
    contract_task_table,
    dep,
    migration_taxonomy,
    profile,
    snapshot,
    taxonomy,
)

NOW = 1_800_000_000.0

# Tres despliegues de conversación en la UE, en tres proveedores, y uno fuera.
HAIKU_A = dep("eu-a/haiku", provider="prov_a", price_in="1", price_out="5")
HAIKU_B = dep("eu-b/haiku", provider="prov_b", price_in="1.1", price_out="5.5")
OPEN_C = dep("eu-c/open", provider="prov_c", family="openai-gpt-oss", price_in="0.5", price_out="2")
SONNET_A = dep(
    "eu-a/sonnet", provider="prov_a", price_in="3", price_out="15", caps={"tier": "medium"}
)
SONNET_B = dep(
    "eu-b/sonnet", provider="prov_b", price_in="3.3", price_out="16.5", caps={"tier": "medium"}
)
GLOBAL_D = dep(
    "glob-d/cheap", provider="prov_d", residency="global", price_in="0.1", price_out="0.4"
)


def _ctx(catalog: Any, **over: Any) -> RouteContext:
    base: dict[str, Any] = {
        "tenant_id": TENANT,
        "catalog": catalog,
        "agent_id": AGENT,
        "agent_version": "v3",
        "turn_id": "turn-1",
        "eu_only": True,
        "agent_certified": frozenset({HAIKU_A.key, HAIKU_B.key, OPEN_C.key}),
        "now": NOW,
    }
    base.update(over)
    return RouteContext(**base)


def _world(*extra_certs: Any) -> Any:
    deployments = [HAIKU_A, HAIKU_B, OPEN_C, SONNET_A, SONNET_B, GLOBAL_D]
    certs = [cert(d, t) for d in deployments for t in ("tool_turn", "answer", "classify")]
    certs += [cert(SONNET_A, "escalate"), cert(SONNET_B, "escalate")]
    return snapshot(deployments, [*certs, *extra_certs], profile())


def _reasons(decision: Any) -> dict[str, str]:
    return {r.deployment: r.reason for r in decision.rejected}


# ── taxonomía ───────────────────────────────────────────────────────────────


def test_the_taxonomy_has_the_fifteen_tasks_of_the_contract() -> None:
    table = contract_task_table()
    assert len(table) == 15, table
    seeded = {t["code"]: t["conversation"] for t in migration_taxonomy()}
    assert seeded == table, "la taxonomía sembrada (0180) y el contrato §1 divergen"
    assert set(taxonomy().codes) == set(table)
    assert {c for c, conv in table.items() if conv} == {"answer", "tool_turn"}


@pytest.mark.parametrize("task", [None, ""])
def test_a_call_without_task_fails(task: str | None) -> None:
    with pytest.raises(MissingTask):
        chain_for(task, profile(), _ctx(_world()))


def test_an_unknown_task_fails() -> None:
    with pytest.raises(UnknownTask):
        chain_for("respond", profile(), _ctx(_world()))


def test_the_legacy_form_still_answers_the_pipeline_of_today() -> None:
    """``pipeline.py`` llama hoy ``chain_for(bindings, rol, default_model=…)``;
    la forma nueva no la rompe hasta que C3 la cambie."""
    assert chain_for({}, "classify", default_model="m", global_fallback="f") == ("m", "f")


# ── elección ────────────────────────────────────────────────────────────────


def test_the_hard_filter() -> None:
    off = dep("eu-e/off", provider="prov_e", status="unavailable")
    leaky = dep("eu-f/leaky", provider="prov_f", zero_retention=False)
    no_tools = dep("eu-g/notools", provider="prov_g", caps={"tools": False})
    not_allowed = dep("eu-h/other", provider="prov_h")
    world = snapshot(
        [HAIKU_A, off, leaky, no_tools, not_allowed, GLOBAL_D],
        [cert(d, "tool_turn") for d in (HAIKU_A, off, leaky, no_tools, not_allowed, GLOBAL_D)],
        profile(),
    )
    allowed = frozenset({HAIKU_A.key, off.key, leaky.key, no_tools.key, GLOBAL_D.key})
    certified = frozenset(d.key for d in world.deployments.values())
    decision = chain_for(
        "tool_turn", profile(), _ctx(world, allowed=allowed, agent_certified=certified)
    )
    assert decision.chosen == HAIKU_A.key
    assert _reasons(decision) == {
        off.key: "status",
        leaky.key: "retention",
        no_tools.key: "capability:tools",
        not_allowed.key: "not_allowed",
        GLOBAL_D.key: "residency",
    }


def test_sovereign_keeps_european_open_weights_only() -> None:
    sovereign_ok = dep(
        "eu-s/open",
        provider="prov_s",
        family="mistral",
        license_id="apache-2.0",
        caps={"provider_jurisdiction": "eu"},
    )
    world = snapshot(
        [HAIKU_A, sovereign_ok],
        [cert(HAIKU_A, "classify"), cert(sovereign_ok, "classify")],
        profile(),
    )
    decision = chain_for("classify", profile(), _ctx(world, sovereign=True))
    assert decision.models == (sovereign_ok.key,)
    assert _reasons(decision) == {HAIKU_A.key: "sovereign"}


def test_only_certified_and_for_conversation_also_by_the_agent() -> None:
    uncertified = dep("eu-u/new", provider="prov_u", price_in="0.01", price_out="0.01")
    weak = dep("eu-w/weak", provider="prov_w", price_in="0.02", price_out="0.02")
    stranger = dep("eu-x/stranger", provider="prov_x", price_in="0.03", price_out="0.03")
    world = snapshot(
        [HAIKU_A, uncertified, weak, stranger],
        [cert(HAIKU_A, "tool_turn"), cert(weak, "tool_turn", 0.5), cert(stranger, "tool_turn")],
        profile(),
    )
    decision = chain_for(
        "tool_turn", profile(), _ctx(world, agent_certified=frozenset({HAIKU_A.key}))
    )
    assert decision.chosen == HAIKU_A.key
    assert _reasons(decision) == {
        uncertified.key: "not_certified",
        weak.key: "below_quality",
        stranger.key: "agent_not_certified",
    }
    # Clasificar no es de conversación: no pide la certificación del agente.
    world = snapshot(
        [HAIKU_A, stranger], [cert(HAIKU_A, "classify"), cert(stranger, "classify")], profile()
    )
    assert (
        chain_for("classify", profile(), _ctx(world, agent_certified=frozenset())).chosen
        == stranger.key
    )


def test_a_failed_or_stale_certification_does_not_count() -> None:
    world = snapshot(
        [HAIKU_A, OPEN_C],
        [
            cert(HAIKU_A, "classify"),
            cert(OPEN_C, "classify", passed=False),
            dataclasses.replace(cert(OPEN_C, "classify"), battery_version=0),
        ],
        profile(),
    )
    decision = chain_for("classify", profile(), _ctx(world))
    assert decision.models == (HAIKU_A.key,)
    assert _reasons(decision)[OPEN_C.key] == "not_certified"


def test_the_cheapest_within_the_p95_wins() -> None:
    slow_cheap = dep("eu-s/slow", provider="prov_s", price_in="0.05", price_out="0.1")
    world = snapshot(
        [HAIKU_A, OPEN_C, slow_cheap],
        [
            cert(HAIKU_A, "classify", p95_ms=500),
            cert(OPEN_C, "classify", p95_ms=700),
            cert(slow_cheap, "classify", p95_ms=2_000),  # el objetivo es 800 ms
        ],
        profile(),
    )
    decision = chain_for("classify", profile(), _ctx(world))
    assert decision.chosen == OPEN_C.key, "el más barato de los que caben en la p95"
    assert _reasons(decision) == {slow_cheap.key: "over_latency"}
    assert decision.estimated_cost_micros is not None


def test_a_call_over_the_cost_ceiling_is_discarded() -> None:
    world = _world()
    # El techo de ``classify`` en el contrato es 200 micros por llamada.
    decision = chain_for(
        "classify",
        profile(),
        _ctx(world, estimate=TokenEstimate(input_tokens=100_000, output_tokens=200)),
    )
    assert decision.outcome in {"reserve_model", "no_model"}
    assert {r.reason for r in decision.rejected} >= {"over_cost"}


def test_the_chain_is_two_alternatives_in_other_providers_and_the_same_residency() -> None:
    other_a = dep("eu-a/other", provider="prov_a", price_in="0.9", price_out="4")
    world = snapshot(
        [HAIKU_A, HAIKU_B, OPEN_C, other_a, GLOBAL_D, SONNET_A],
        [cert(d, "tool_turn") for d in (HAIKU_A, HAIKU_B, OPEN_C, other_a, GLOBAL_D, SONNET_A)],
        profile(),
    )
    certified = frozenset(
        {HAIKU_A.key, HAIKU_B.key, OPEN_C.key, other_a.key, GLOBAL_D.key, SONNET_A.key}
    )
    decision = chain_for(
        "tool_turn", profile(), _ctx(world, agent_certified=certified, eu_only=False)
    )
    assert decision.chosen == GLOBAL_D.key  # el más barato: global, sin «Solo UE»
    # Las alternativas comparten residencia con el elegido: ninguna de la UE.
    assert decision.models == (GLOBAL_D.key,)

    decision = chain_for("tool_turn", profile(), _ctx(world, agent_certified=certified))
    assert decision.models[0] == OPEN_C.key
    assert len(decision.models) == 3
    providers = [d.provider for d in decision.chain]
    assert len(set(providers)) == 3, f"alternativas en el mismo proveedor: {providers}"
    assert {d.residency for d in decision.chain} == {"eu"}


# ── afinidad ────────────────────────────────────────────────────────────────


def test_affinity_lasts_at_least_the_provider_cache_and_holds_against_a_cheaper_one() -> None:
    world = _world()
    first = chain_for("tool_turn", profile(), _ctx(world))
    assert first.chosen == OPEN_C.key
    pin = pin_after(first, served=OPEN_C.key, now=NOW)
    assert pin is not None
    assert pin.expires_at - pin.pinned_at >= PIN_MIN_TTL_S >= 3600

    cheaper = dep("eu-z/cheaper", provider="prov_z", price_in="0.01", price_out="0.01")
    world = snapshot(
        [*world.deployments.values(), cheaper],
        [*world.class_certs, cert(cheaper, "tool_turn")],
        profile(),
    )
    ctx = _ctx(
        world,
        pinned=pin,
        now=NOW + 1800,
        agent_certified=frozenset({OPEN_C.key, cheaper.key, HAIKU_A.key}),
    )
    again = chain_for("tool_turn", profile(), ctx)
    assert again.outcome == "pinned"
    assert again.chosen == OPEN_C.key, "la afinidad no cambia por un modelo más barato"


@pytest.mark.parametrize(
    ("change", "why"),
    [
        ({"now": NOW + PIN_MIN_TTL_S + 1}, "expired"),
        ({"agent_version": "v4"}, "new_version"),
    ],
)
def test_affinity_only_changes_by_expiry_or_a_new_version(change: dict[str, Any], why: str) -> None:
    world = _world()
    pin = PinnedModel(
        deployment=HAIKU_B.key, agent_version="v3", pinned_at=NOW, expires_at=NOW + PIN_MIN_TTL_S
    )
    decision = chain_for("tool_turn", profile(), _ctx(world, pinned=pin, **change))
    assert decision.outcome == "routed"
    assert decision.chosen == OPEN_C.key
    assert decision.pin_broken == why


def test_affinity_changes_when_its_provider_fails_or_the_deployment_goes() -> None:
    world = _world()
    pin = PinnedModel(
        deployment=OPEN_C.key, agent_version="v3", pinned_at=NOW, expires_at=NOW + PIN_MIN_TTL_S
    )
    decision = chain_for("tool_turn", profile(), _ctx(world, pinned=pin))
    # El proveedor del fijado cayó y respondió la alternativa: la afinidad se mueve.
    moved = pin_after(decision, served=decision.models[1], now=NOW + 5, previous=pin)
    assert moved is not None and moved.deployment == decision.models[1]
    # Un despliegue «No disponible» deja de usarse desde el siguiente turno.
    gone = dataclasses.replace(OPEN_C, status="unavailable")
    world = snapshot(
        [HAIKU_A, HAIKU_B, gone],
        [cert(d, "tool_turn") for d in (HAIKU_A, HAIKU_B, gone)],
        profile(),
    )
    decision = chain_for("tool_turn", profile(), _ctx(world, pinned=pin))
    assert decision.chosen == HAIKU_A.key
    assert decision.pin_broken == "status"


def test_a_new_version_re_pins_even_on_the_same_deployment() -> None:
    """Con la versión nueva la afinidad se rehace, aunque gane el mismo modelo:
    si guardara la versión vieja se rompería en cada turno."""
    old = PinnedModel(
        deployment=OPEN_C.key, agent_version="v2", pinned_at=NOW - 60, expires_at=NOW + 600
    )
    decision = chain_for("tool_turn", profile(), _ctx(_world(), pinned=old))
    assert decision.pin_broken == "new_version" and decision.chosen == OPEN_C.key
    pin = pin_after(decision, served=OPEN_C.key, now=NOW, previous=old)
    assert pin is not None and pin.agent_version == "v3" and pin.pinned_at == NOW
    again = chain_for("tool_turn", profile(), _ctx(_world(), pinned=pin, now=NOW + 10))
    assert again.outcome == "pinned"


def test_the_pin_lives_in_the_thread_state_per_agent() -> None:
    decision = chain_for("tool_turn", profile(), _ctx(_world()))
    pin = pin_after(decision, served=decision.chosen or "", now=NOW)
    assert pin is not None
    state_value = with_pin({}, AGENT, pin)
    state_value = with_pin(state_value, SIBLING, dataclasses.replace(pin, deployment=HAIKU_B.key))
    back = pins_from_state({"pinned_model": state_value})
    assert back[str(AGENT)] == pin
    assert back[str(SIBLING)].deployment == HAIKU_B.key
    # Solo las tareas de conversación fijan modelo.
    classify = chain_for("classify", profile(), _ctx(_world()))
    assert pin_after(classify, served=classify.chosen or "", now=NOW) is None


def test_a_pinned_model_policy_covers_only_conversation() -> None:
    """Requisito 39.8: «Fijar un modelo» cubre responder y el turno con
    herramientas; clasificar sigue la política."""
    world = _world()
    ctx = _ctx(world, agent_pinned_deployment=HAIKU_B.key)
    assert chain_for("tool_turn", profile(), ctx).chosen == HAIKU_B.key
    assert chain_for("tool_turn", profile(), ctx).outcome == "agent_pinned"
    assert chain_for("classify", profile(), ctx).chosen == OPEN_C.key


# ── escalado ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "signals",
    [
        TurnSignals(tool_args_rejected=True),
        TurnSignals(repeated_ask=2),
        TurnSignals(judge_red=True),
        TurnSignals(intents=2),
        TurnSignals(tool_iterations=5),
    ],
)
def test_graph_signals_escalate_in_a_subcall(signals: TurnSignals) -> None:
    world = _world()
    verdict = escalation_for(
        signals,
        origin_task="tool_turn",
        profile=profile(),
        ctx=_ctx(world, agent_certified=frozenset({SONNET_A.key, SONNET_B.key})),
        current_tier="basic",
        escalations_at=[],
    )
    assert verdict.action == "subcall"
    assert verdict.signals
    assert verdict.decision is not None and verdict.decision.escalated
    assert verdict.decision.task == "escalate"
    assert verdict.decision.chosen in {SONNET_A.key, SONNET_B.key}
    assert all(d.capabilities.tier == "medium" for d in verdict.decision.chain)


def test_no_signal_no_escalation_and_the_main_loop_keeps_its_model() -> None:
    world = _world()
    first = chain_for("tool_turn", profile(), _ctx(world))
    pin = pin_after(first, served=first.chosen or "", now=NOW)
    quiet = escalation_for(
        TurnSignals(repeated_ask=1, tool_iterations=4),
        origin_task="tool_turn",
        profile=profile(),
        ctx=_ctx(world, pinned=pin),
        current_tier="basic",
        escalations_at=[],
    )
    assert quiet.action == "none"
    loud = escalation_for(
        TurnSignals(judge_red=True),
        origin_task="tool_turn",
        profile=profile(),
        ctx=_ctx(world, pinned=pin),
        current_tier="basic",
        escalations_at=[],
    )
    # La subllamada no toca la afinidad del bucle principal.
    again = chain_for("tool_turn", profile(), _ctx(world, pinned=pin))
    assert loud.action == "subcall" and again.chosen == first.chosen


def test_economy_does_not_escalate_it_hands_over_to_a_person() -> None:
    verdict = escalation_for(
        TurnSignals(judge_red=True),
        origin_task="tool_turn",
        profile=profile("economy"),
        ctx=_ctx(_world()),
        current_tier="basic",
        escalations_at=[],
    )
    assert verdict.action == "handoff"
    assert verdict.reason == "escalated"
    assert verdict.decision is None


def test_three_escalations_an_hour_then_a_person() -> None:
    at = record_escalation([], now=NOW - 3000)
    at = record_escalation(at, now=NOW - 2000)
    at = record_escalation([NOW - 7200, *at], now=NOW - 1000)
    assert len(at) == 3, "lo de hace más de una hora no cuenta"
    verdict = escalation_for(
        TurnSignals(judge_red=True),
        origin_task="tool_turn",
        profile=profile(),
        ctx=_ctx(_world()),
        current_tier="basic",
        escalations_at=at,
    )
    assert verdict.action == "handoff"
    assert verdict.reason == "turn_limit"


# ── clasificación ───────────────────────────────────────────────────────────


def test_classification_runs_on_the_cheapest_certified_apart_from_the_answer_model() -> None:
    tiny = dep(
        "eu-t/tiny", provider="prov_t", family="openai-gpt-oss", price_in="0.02", price_out="0.1"
    )
    world = snapshot(
        [HAIKU_A, OPEN_C, tiny],
        [cert(HAIKU_A, "classify"), cert(OPEN_C, "classify"), cert(HAIKU_A, "tool_turn")],
        profile(),
    )
    ctx = _ctx(world, agent_pinned_deployment=HAIKU_A.key, agent_certified=frozenset({HAIKU_A.key}))
    assert chain_for("tool_turn", profile(), ctx).chosen == HAIKU_A.key
    decision = chain_for("classify", profile(), ctx)
    assert decision.chosen == OPEN_C.key, "el clasificador no sigue al de respuesta"
    assert _reasons(decision) == {tiny.key: "not_certified"}
    assert decision.reasoning == "none"


def test_the_classification_is_a_typed_object_validated_always() -> None:
    good = parse_classification(
        '{"intent": "book", "needs_tools": true, "risk": "high", "complexity": "low",'
        ' "language": "es", "intents": 2}'
    )
    assert good == ClassifyResult(
        intent="book", needs_tools=True, risk="high", complexity="low", language="es", intents=2
    )
    # Estricta: todas las propiedades son obligatorias (``strict`` de OpenAI).
    assert set(ClassifyResult.model_json_schema()["required"]) == set(ClassifyResult.model_fields)
    for bad in (
        "book",
        '{"intent": "book"}',
        '{"intent": "book", "needs_tools": true, "risk": "high", "complexity": "low", "language": "es"}',
        '{"intent": "book", "needs_tools": "yes", "risk": "high", "complexity": "low", "language": "es", "intents": 1}',
        '{"intent": "book", "needs_tools": true, "risk": "extreme", "complexity": "low", "language": "es", "intents": 1}',
        '{"intent": "book", "needs_tools": true, "risk": "high", "complexity": "low", "language": "es", "intents": 0}',
        '{"intent": "book", "needs_tools": true, "risk": "high", "complexity": "low", "language": "es", "intents": 1, "x": 1}',
    ):
        assert parse_classification(bad) is None, bad


# ── fallos ──────────────────────────────────────────────────────────────────


class _ServiceUnavailableError(Exception):
    """Mismo nombre de clase que el error de LiteLLM: el router los reconoce por nombre."""


_ServiceUnavailableError.__name__ = "ServiceUnavailableError"


def _router(fail: Callable[[LLMCall], bool] | None = None) -> tuple[LLMRouter, InMemoryProvider]:
    provider = InMemoryProvider()
    if fail is not None:
        original = provider.acomplete

        async def acomplete(**kwargs: Any) -> str:
            call = LLMCall(
                tenant_id=kwargs["tenant_id"],
                role=kwargs["role"],
                model=kwargs["model"],
                messages=[],
            )
            if fail(call):
                provider.calls.append(call)
                raise _ServiceUnavailableError(f"{call.model} is down")
            return await original(**kwargs)

        provider.acomplete = acomplete  # type: ignore[method-assign]
    clock = [NOW]
    router = LLMRouter(
        provider=provider,
        classify_model="legacy/classify",
        respond_model="legacy/respond",
        fallback_model="legacy/fallback",
        cooldowns=CooldownBook(clock=lambda: clock[0]),
        retry_backoff_s=0.0,
    )
    return router, provider


async def test_a_provider_down_falls_to_the_alternative_in_the_same_turn_and_cools() -> None:
    world = _world()
    decision = chain_for("tool_turn", profile(), _ctx(world))
    down = decision.models[0]
    router, _ = _router(fail=lambda c: c.model == down)

    result = await router.complete_routed(
        decision=decision, tenant_id=TENANT, messages=[{"role": "user", "content": "hola"}]
    )
    assert result.served == decision.models[1]
    assert result.fallback_used
    assert result.cooled == (down,)
    assert router.cooldowns.is_cool(down)

    # El siguiente turno ya no lo considera mientras dure el enfriamiento.
    later = chain_for("tool_turn", profile(), _ctx(world, cooled=router.cooldowns.active()))
    assert _reasons(later)[down] == "cooldown"
    assert down not in later.models


async def test_when_every_alternative_fails_it_is_a_provider_failure() -> None:
    decision = chain_for("tool_turn", profile(), _ctx(_world()))
    router, _ = _router(fail=lambda c: True)
    with pytest.raises(ProviderChainExhausted) as err:
        await router.complete_routed(decision=decision, tenant_id=TENANT, messages=[])
    assert err.value.reason == "provider_failure"


async def test_without_a_model_in_the_clients_residency_it_is_no_model() -> None:
    world = snapshot([GLOBAL_D], [cert(GLOBAL_D, "tool_turn")], profile())
    decision = chain_for(
        "tool_turn", profile(), _ctx(world, agent_certified=frozenset({GLOBAL_D.key}))
    )
    assert decision.outcome == "no_model"
    assert decision.models == ()
    assert decision.anomaly == "no_model"
    router, provider = _router()
    with pytest.raises(NoModelAvailable) as err:
        await router.complete_routed(decision=decision, tenant_id=TENANT, messages=[])
    assert err.value.reason == "no_model"
    assert provider.calls == [], "el turno no sale de la residencia del cliente"


def test_without_certificates_the_reserve_model_if_it_meets_the_residency() -> None:
    world = snapshot([HAIKU_A, GLOBAL_D], [], profile("auto", vision={"reserve": HAIKU_A.key}))
    decision = chain_for("vision", world.profiles["auto"], _ctx(world))
    assert decision.outcome == "reserve_model"
    assert decision.anomaly == "reserve_model"
    assert decision.models == (HAIKU_A.key,)

    world = snapshot([HAIKU_A, GLOBAL_D], [], profile("auto", vision={"reserve": GLOBAL_D.key}))
    decision = chain_for("vision", world.profiles["auto"], _ctx(world))
    assert decision.outcome == "no_model", "la reserva tampoco sale de la residencia"


# ── registro y límites ──────────────────────────────────────────────────────


async def test_every_decision_is_logged_with_its_fields_and_no_text() -> None:
    world = _world()
    decision = chain_for("tool_turn", profile(), _ctx(world))
    router, _ = _router()
    with capture_logs() as logs:
        await router.complete_routed(
            decision=decision,
            tenant_id=TENANT,
            messages=[{"role": "user", "content": "MENSAJE-SECRETO"}],
        )
    events = [e for e in logs if e["event"] == ROUTE_DECISION_EVENT]
    assert len(events) == 1
    event = events[0]
    assert event["tenant_id"] == str(TENANT)
    assert event["agent_id"] == str(AGENT)
    assert event["turn_id"] == "turn-1"
    assert event["task"] == "tool_turn"
    assert event["profile"] == "auto"
    assert event["policy_version"] == 3
    assert event["chosen"] == decision.chosen
    assert event["fallback_used"] is None
    assert event["escalated"] is False
    assert isinstance(event["candidates_rejected"], list)
    assert {"latency_ms", "cost_micros", "price_micros"} <= event.keys()
    assert "MENSAJE-SECRETO" not in repr(logs)


async def test_a_no_model_decision_is_logged_too() -> None:
    world = snapshot([GLOBAL_D], [cert(GLOBAL_D, "classify")], profile())
    decision = chain_for("classify", profile(), _ctx(world))
    router, _ = _router()
    with capture_logs() as logs, pytest.raises(NoModelAvailable):
        await router.complete_routed(decision=decision, tenant_id=TENANT, messages=[])
    [event] = [e for e in logs if e["event"] == ROUTE_DECISION_EVENT]
    assert event["chosen"] is None
    assert {"deployment": GLOBAL_D.key, "reason": "residency"} in event["candidates_rejected"]


async def test_twelve_calls_per_turn_then_a_person() -> None:
    decision = chain_for("classify", profile(), _ctx(_world()))
    router, provider = _router()
    budget = TurnBudget.for_profile(profile())
    assert budget.max_calls == 12
    with turn_budget(budget):
        for _ in range(12):
            await router.complete_routed(decision=decision, tenant_id=TENANT, messages=[])
        with pytest.raises(TurnLimitReached) as err:
            await router.complete_routed(decision=decision, tenant_id=TENANT, messages=[])
    assert err.value.reason == "turn_limit" and err.value.limit == "calls"
    assert len(provider.calls) == 12


def test_the_turn_cost_ceiling() -> None:
    budget = TurnBudget.for_profile(profile())
    assert budget.cost_ceiling_micros == 80_000
    budget.before_call()
    budget.add_cost(80_000)
    with pytest.raises(TurnLimitReached) as err:
        budget.before_call()
    assert err.value.limit == "cost"


def test_the_typed_model_never_replaces_the_hard_filter() -> None:
    world = _world()
    hint = RouteHint(prefer=GLOBAL_D.key, complexity="low", risk="low")
    decision = chain_for("tool_turn", profile(), _ctx(world, hint=hint))
    assert GLOBAL_D.key not in decision.models
    assert _reasons(decision)[GLOBAL_D.key] == "residency"
    # Dentro de lo que pasó el filtro, sí puede preferir.
    hint = RouteHint(prefer=HAIKU_B.key)
    assert chain_for("tool_turn", profile(), _ctx(world, hint=hint)).chosen == HAIKU_B.key


async def test_no_batch_mixes_clients() -> None:
    assert litellm_kwargs_contract() == {"enable_batching": False, "group_by": None}
    decision = chain_for("tool_turn", profile(), _ctx(_world()))
    router, provider = _router()
    # Una decisión de un cliente no sirve para la llamada de otro.
    with pytest.raises(IsolationViolation):
        await router.complete_routed(decision=decision, tenant_id=NEIGHBOUR, messages=[])
    assert provider.calls == []
    await router.complete_routed(decision=decision, tenant_id=TENANT, messages=[])
    assert [c.tenant_id for c in provider.calls] == [TENANT]


async def test_the_catalog_is_read_once_per_ttl_not_per_turn(monkeypatch) -> None:
    """El catálogo son decenas de filas que cambian casi nunca: se lee con TTL,
    como el de precios, y ``invalidate_catalog`` lo fuerza."""
    from nexus_worker.runtime import model_resolver

    reads: list[int] = []

    async def fake_load() -> Any:
        reads.append(1)
        return _world()

    monkeypatch.setattr(model_resolver, "_load_snapshot_from_db", fake_load)
    model_resolver.invalidate_catalog()
    first = await model_resolver.get_catalog_snapshot()
    again = await model_resolver.get_catalog_snapshot()
    assert first is again and len(reads) == 1
    model_resolver.invalidate_catalog()
    await model_resolver.get_catalog_snapshot()
    assert len(reads) == 2
    model_resolver.invalidate_catalog()


def test_decisions_carry_the_client_and_agent_and_a_fresh_id() -> None:
    world = _world()
    one = chain_for("tool_turn", profile(), _ctx(world))
    two = chain_for("tool_turn", profile(), _ctx(world))
    assert one.tenant_id == TENANT and one.agent_id == AGENT
    assert isinstance(one.id, uuid.UUID) and one.id != two.id
