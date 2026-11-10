"""El juez y las certificaciones (spec 047, T138 · requisitos 42.1 a 42.6).

Contra la base de verdad: lo que se guarda en ``model_task_certifications``
(plataforma) y en ``agent_model_certifications`` (por cliente, con RLS), y cuándo
caduca. Ninguna prueba llama a un modelo: la batería se ejecuta con un
``run_case`` de mentira que dice qué pasó en cada repetición.

Los despliegues que se dan de alta aquí son de prueba y se borran al acabar:
``model_profiles`` es catálogo de plataforma y el ``conftest`` no lo vacía.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa
from nexus_worker.certification.battery import (
    COUNTRIES,
    REGISTERS,
    SOURCES_V1,
    Battery,
    BatteryCase,
    coverage_gaps,
    load_battery_v1,
)
from nexus_worker.certification.metrics import CaseRun, class_metrics, quality
from nexus_worker.certification.runner import (
    RUNS_PER_CASE,
    SameFamilyJudge,
    SingleClientBatch,
    SuiteTest,
    certify_agent,
    certify_class,
)
from nexus_worker.guardrails.outcome_grader import OutcomeGrader
from nexus_worker.runtime.llm import InMemoryProvider
from nexus_worker.runtime.model_resolver import RouteContext, chain_for

from nexus_api.core import respond_catalog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.services.certification import (
    MAX_REGRESSION_POINTS,
    AgentSuiteResult,
    SuiteCase,
    agent_verdict,
    background_candidates,
    certified_deployments_for_agent,
    class_fingerprint,
    expire_agent_certifications,
    expire_class_certifications,
    payer_for,
    record_agent_certification,
    record_class_certification,
)
from nexus_api.services.router_catalog import ProfilePolicy, load_snapshot

pytestmark = pytest.mark.asyncio

PREFIX = "t138-"


@pytest_asyncio.fixture
async def tenants_ab(db_session) -> dict[str, uuid.UUID]:
    from nexus_api.db.models import Tenant, TenantPlan

    ids = {"a": uuid.uuid4(), "b": uuid.uuid4()}
    db_session.add_all(
        [
            Tenant(id=t, name=f"T138 {k}", slug=f"t138-{k}-{t.hex[:6]}", plan=TenantPlan.PRO)
            for k, t in ids.items()
        ]
    )
    await db_session.commit()
    return ids


async def seed_active_agent_config(
    db_session, *, tenant_id: uuid.UUID, system_prompt: str, tools: list[str]
):
    """La versión activa del agente principal del cliente (el trigger crea el agente)."""
    from nexus_api.db.models import AgentConfig, AgentConfigStatus

    cfg = AgentConfig(
        tenant_id=tenant_id,
        version=1,
        status=AgentConfigStatus.ACTIVE,
        system_prompt_rendered=system_prompt,
        channels=[],
        tools=tools,
        policies={},
        seed_template_ref=None,
    )
    db_session.add(cfg)
    await db_session.commit()
    await db_session.refresh(cfg)
    return cfg


async def _insert_deployment(
    key: str,
    *,
    provider: str,
    family: str,
    price_in: str,
    status: str = "active",
    caps: dict[str, Any] | None = None,
) -> None:
    capabilities = {
        "tools": True,
        "strict_structured_outputs": True,
        "structured_outputs": True,
        "cache_mode": "explicit",
        "context_window": 200000,
        "reasoning_control": "effort",
        "tier": "basic",
        "quantization": "bf16",
    }
    capabilities.update(caps or {})
    async with get_sessionmaker()() as session, session.begin():
        await session.execute(
            sa.text(
                """
                INSERT INTO model_profiles (
                    provider, model_id, display_name, route, region, family, residency,
                    zero_retention, retention_how, contract_dpa, subprocessor_listed, status,
                    capabilities, supports_tools, max_context, price_input_per_mtok,
                    price_output_per_mtok, quota_weight_input, quota_weight_cache_read,
                    quota_weight_output
                ) VALUES (
                    :provider, :key, :key, :key, 'eu-south-2', :family, 'eu',
                    true, 'store=false', true, true, :status,
                    CAST(:caps AS jsonb), true, 200000, :pin, :pout, 0.2, 0.02, 1
                )
                """
            ),
            {
                "provider": provider,
                "key": key,
                "family": family,
                "status": status,
                "caps": json.dumps(capabilities),
                "pin": Decimal(price_in),
                "pout": Decimal(price_in) * 5,
            },
        )
        await session.execute(
            sa.text(
                "INSERT INTO model_prices (deployment_id, valid_from, input, output, source_url) "
                "SELECT id, DATE '2026-10-01', price_input_per_mtok, price_output_per_mtok, "
                "'https://example.invalid' FROM model_profiles WHERE model_id = :key"
            ),
            {"key": key},
        )


@pytest_asyncio.fixture
async def catalog() -> AsyncIterator[dict[str, str]]:
    keys = {
        "claude": f"{PREFIX}prov-a/claude-basic",
        "claude_b": f"{PREFIX}prov-b/claude-basic",
        "oss": f"{PREFIX}prov-c/gpt-oss",
        "judge": f"{PREFIX}prov-d/judge",
    }
    await _insert_deployment(
        keys["claude"], provider="prov_a", family="anthropic-claude", price_in="1"
    )
    await _insert_deployment(
        keys["claude_b"], provider="prov_b", family="anthropic-claude", price_in="1.1"
    )
    await _insert_deployment(
        keys["oss"], provider="prov_c", family="openai-gpt-oss", price_in="0.2"
    )
    await _insert_deployment(keys["judge"], provider="prov_d", family="openai-gpt", price_in="0.5")
    try:
        yield keys
    finally:
        async with get_sessionmaker()() as session, session.begin():
            await session.execute(
                sa.text("DELETE FROM model_profiles WHERE model_id LIKE :p"), {"p": f"{PREFIX}%"}
            )
        respond_catalog.reset()


async def _snapshot() -> Any:
    async with get_sessionmaker()() as session:
        return await load_snapshot(session)


def _battery(task: str = "tool_turn") -> Battery:
    cases = tuple(
        BatteryCase(
            id=f"c{i}",
            source=SOURCES_V1[i % len(SOURCES_V1)],
            task=task,
            persona=None,
            user_message=f"caso {i}",
            history=(),
            assertions={},
        )
        for i in range(20)
    )
    return Battery.build(
        version=1,
        cases=cases,
        weights={"pass3": 0.6, "tool_args_valid": 0.2, "reasks": 0.1, "language_drift": 0.1},
        threshold=0.9,
    )


def _runner(fail_case: str | None = None) -> Any:
    async def run_case(case: BatteryCase, deployment: Any, attempt: int) -> CaseRun:
        ok = not (case.id == fail_case and attempt == 2)
        return CaseRun(
            passed=ok, tool_args_valid=True, latency_ms=300 + attempt * 10, reasoning=attempt == 0
        )

    return run_case


# ── la batería ──────────────────────────────────────────────────────────────


def test_battery_v1_is_spanish_from_five_countries_with_tu_and_usted() -> None:
    assert set(COUNTRIES) == {"ES", "MX", "AR", "CO", "CL"}
    assert set(REGISTERS) == {"tu", "usted"}
    assert set(SOURCES_V1) == {"driver", "tau_bench_es", "reservas"}
    battery = load_battery_v1(tau_bench_path=None)
    # Los 95 casos del driver de evaluación y el dominio propio de reservas.
    assert sum(1 for c in battery.cases if c.source == "driver") == 95
    reservas = [c for c in battery.cases if c.source == "reservas"]
    assert {(c.persona.country, c.persona.register) for c in reservas if c.persona} == {
        (country, register) for country in COUNTRIES for register in REGISTERS
    }
    # Sin el paquete ``es`` de τ-bench la batería está incompleta y lo dice.
    gaps = coverage_gaps(battery)
    assert any("tau_bench_es" in g for g in gaps), gaps
    assert battery.version == 1
    assert battery.weights["pass3"] == max(battery.weights.values()), "pass^3 manda"


def test_the_metrics_of_a_battery() -> None:
    runs = {
        "a": [
            CaseRun(passed=True, latency_ms=100),
            CaseRun(passed=True, latency_ms=200),
            CaseRun(passed=True, latency_ms=300),
        ],
        "b": [
            CaseRun(passed=True, reasks=1, tool_args_valid=False, latency_ms=400, reasoning=True),
            CaseRun(
                passed=False,
                unsupported_claims=2,
                language_drift=True,
                latency_ms=500,
                reasoning=True,
            ),
            CaseRun(passed=True, tool_args_valid=True, latency_ms=600, reasoning=True),
        ],
    }
    m = class_metrics(runs)
    assert m["pass3"] == 0.5
    assert m["reasks"] == 0.5
    assert m["unsupported_claims"] == 1.0
    assert m["tool_args_valid"] == 0.5
    assert m["language_drift"] == pytest.approx(1 / 6)
    assert m["latency_p50_ms"] == 200 and m["latency_p95_ms"] == 300
    assert m["latency_p50_ms_reasoning"] == 500 and m["latency_p95_ms_reasoning"] == 600
    weights = {"pass3": 0.6, "tool_args_valid": 0.2, "reasks": 0.1, "language_drift": 0.1}
    # pass^3 manda: con todo lo demás perfecto, un pass^3 bajo no llega.
    perfect_but = {**m, "pass3": 0.5, "tool_args_valid": 1.0, "reasks": 0.0, "language_drift": 0.0}
    assert quality(perfect_but, weights) < 0.9


# ── por clase: qué guarda y cuándo caduca ───────────────────────────────────


async def test_a_class_certification_stores_what_it_measured(catalog, db_session) -> None:
    snap = await _snapshot()
    target, judge = snap.deployments[catalog["oss"]], snap.deployments[catalog["judge"]]
    result = await certify_class(_battery(), target, "tool_turn", run_case=_runner(), judge=judge)
    assert result.passed and result.quality >= result.threshold
    async with get_sessionmaker()() as session, session.begin():
        await record_class_certification(session, target, result)

    row = (
        await db_session.execute(
            sa.text(
                "SELECT c.task, c.battery_version, c.scores, c.quality, c.passed, c.certified_at, "
                "c.invalidated_at FROM model_task_certifications c JOIN model_profiles p "
                "ON p.id = c.deployment_id WHERE p.model_id = :k"
            ),
            {"k": target.key},
        )
    ).one()
    assert row.task == "tool_turn" and row.battery_version == 1
    assert row.passed is True and row.invalidated_at is None and row.certified_at is not None
    for metric in ("pass3", "reasks", "unsupported_claims", "tool_args_valid", "language_drift"):
        assert metric in row.scores["metrics"], metric
    assert row.scores["threshold"] == 0.9
    assert row.scores["fingerprint"] == class_fingerprint(target, 1)
    assert row.scores["judge"] == judge.key

    snap = await _snapshot()
    assert snap.class_cert(target.key, "tool_turn") is not None


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("route", "otra-ruta"),
        ("region", "eu-west-3"),
        ("provider", "prov_z"),
        ("capabilities", '{"quantization": "fp8"}'),
    ],
)
async def test_a_class_certification_expires_when_the_deployment_changes(
    catalog, db_session, column: str, value: str
) -> None:
    snap = await _snapshot()
    target, judge = snap.deployments[catalog["oss"]], snap.deployments[catalog["judge"]]
    result = await certify_class(_battery(), target, "tool_turn", run_case=_runner(), judge=judge)
    async with get_sessionmaker()() as session, session.begin():
        await record_class_certification(session, target, result)

    expr = "capabilities || CAST(:v AS jsonb)" if column == "capabilities" else ":v"
    await db_session.execute(
        sa.text(f"UPDATE model_profiles SET {column} = {expr} WHERE model_id = :k"),
        {"v": value, "k": target.key},
    )
    await db_session.commit()
    snap = await _snapshot()
    async with get_sessionmaker()() as session, session.begin():
        expired = await expire_class_certifications(
            session, snap.deployments.values(), battery_version=1
        )
    assert (target.key, "tool_turn") in expired
    assert (await _snapshot()).class_cert(target.key, "tool_turn") is None


async def test_a_price_change_does_not_expire_it_and_a_new_battery_does(
    catalog, db_session
) -> None:
    snap = await _snapshot()
    target, judge = snap.deployments[catalog["oss"]], snap.deployments[catalog["judge"]]
    result = await certify_class(_battery(), target, "tool_turn", run_case=_runner(), judge=judge)
    async with get_sessionmaker()() as session, session.begin():
        await record_class_certification(session, target, result)
    await db_session.execute(
        sa.text(
            "INSERT INTO model_prices (deployment_id, valid_from, input, output) "
            "SELECT id, :d, 9, 45 FROM model_profiles WHERE model_id = :k"
        ),
        {"d": date(2026, 10, 20), "k": target.key},
    )
    await db_session.commit()
    snap = await _snapshot()
    async with get_sessionmaker()() as session, session.begin():
        assert (
            await expire_class_certifications(session, snap.deployments.values(), battery_version=1)
            == []
        )
        expired = await expire_class_certifications(
            session, snap.deployments.values(), battery_version=2
        )
    assert (target.key, "tool_turn") in expired


async def test_a_failing_run_does_not_certify(catalog) -> None:
    snap = await _snapshot()
    target, judge = snap.deployments[catalog["oss"]], snap.deployments[catalog["judge"]]
    # Un caso falla en la tercera repetición: ese caso no hace pass^3.
    result = await certify_class(
        _battery(), target, "tool_turn", run_case=_runner(fail_case="c3"), judge=judge
    )
    assert result.metrics["pass3"] == 19 / 20
    assert RUNS_PER_CASE == 3


# ── el juez ─────────────────────────────────────────────────────────────────


async def test_the_judge_is_of_another_family(catalog) -> None:
    snap = await _snapshot()
    claude, claude_b = snap.deployments[catalog["claude"]], snap.deployments[catalog["claude_b"]]
    with pytest.raises(SameFamilyJudge):
        await certify_class(_battery(), claude, "tool_turn", run_case=_runner(), judge=claude_b)
    # El router lo aplica también: la tarea ``judge`` descarta la familia juzgada.
    judge_policy = ProfilePolicy.from_row("platform", 1, {"tasks": {"judge": {"min_quality": 0.0}}})
    from nexus_api.services.router_catalog import CatalogSnapshot, ClassCertification

    certs = tuple(
        ClassCertification(
            deployment_key=k,
            task="judge",
            battery_version=1,
            quality=0.95,
            passed=True,
            scores={},
            certified_at=None,
            invalidated_at=None,
        )
        for k in snap.deployments
    )
    world = CatalogSnapshot(
        taxonomy=snap.taxonomy,
        deployments=snap.deployments,
        class_certs=certs,
        profiles={},
        battery_version=1,
    )
    ctx = RouteContext(
        tenant_id=uuid.uuid4(), catalog=world, judged_family="anthropic-claude", now=1.0
    )
    decision = chain_for("judge", judge_policy, ctx)
    assert decision.chain and all(d.family != "anthropic-claude" for d in decision.chain)
    assert {r.reason for r in decision.rejected if r.deployment in {claude.key, claude_b.key}} == {
        "same_family"
    }


async def test_the_turn_grader_asks_for_a_judge_of_another_family() -> None:
    provider = InMemoryProvider(responder=lambda c: '{"overall": "pass", "feedback": ""}')
    picked: list[str | None] = []

    def judge_for(judged_family: str | None) -> tuple[str, ...]:
        picked.append(judged_family)
        return ("openai/judge-model",) if judged_family == "anthropic-claude" else ("anthropic/j",)

    grader = OutcomeGrader(provider=provider, judge_for=judge_for)
    verdict = await grader.grade(
        tenant_id=uuid.uuid4(),
        intent="info",
        rubric_body="- correcto",
        draft_response="hola",
        tool_envelopes=[],
        judged_family="anthropic-claude",
    )
    assert verdict.overall == "pass"
    assert picked == ["anthropic-claude"]
    assert provider.calls[-1].model == "openai/judge-model"
    assert provider.calls[-1].role == "grader"


# ── por agente ──────────────────────────────────────────────────────────────


def _suite(*passes: int, score: float, reference: float) -> AgentSuiteResult:
    return AgentSuiteResult(
        cases=tuple(
            SuiteCase(test_id=f"t{i}", critical=True, passes=p) for i, p in enumerate(passes)
        ),
        score=score,
        reference_score=reference,
        reference_deployment="ref",
    )


@pytest.mark.parametrize(
    ("result", "ok"),
    [
        (_suite(3, 3, score=90, reference=91), True),
        (_suite(3, 3, score=89, reference=91), True),  # justo 2 puntos
        (_suite(3, 3, score=88.9, reference=91), False),
        (_suite(3, 2, score=95, reference=91), False),  # una crítica en 2 de 3
    ],
)
def test_the_agent_certifies_with_all_criticals_three_of_three_and_two_points(
    result: AgentSuiteResult, ok: bool
) -> None:
    verdict = agent_verdict(result)
    assert verdict.passed is ok, verdict.reasons
    assert MAX_REGRESSION_POINTS == 2


async def test_an_agent_certification_is_stored_per_client_and_per_agent(
    catalog, db_session, tenants_ab
) -> None:
    a = tenants_ab["a"]
    cfg = await seed_active_agent_config(db_session, tenant_id=a, system_prompt="A", tools=[])
    snap = await _snapshot()
    target = snap.deployments[catalog["oss"]]
    async with get_sessionmaker()() as session, tenant_scoped_session(session, a):
        await record_agent_certification(
            session,
            tenant_id=a,
            agent_id=cfg.agent_id,
            agent_config_id=cfg.id,
            deployment=target,
            suite_revision=1,
            result=_suite(3, 3, score=90, reference=90),
            launched_by="partner",
        )
    async with get_sessionmaker()() as session, tenant_scoped_session(session, a):
        keys = await certified_deployments_for_agent(
            session, agent_id=cfg.agent_id, agent_config_id=cfg.id, suite_revision=1
        )
        assert keys == frozenset({target.key})
        # Otra versión o otra suite: caduca.
        assert not await certified_deployments_for_agent(
            session, agent_id=cfg.agent_id, agent_config_id=cfg.id, suite_revision=2
        )
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenants_ab["b"]):
        assert not await certified_deployments_for_agent(
            session, agent_id=cfg.agent_id, agent_config_id=cfg.id, suite_revision=1
        )
    paid = (
        await db_session.execute(sa.text("SELECT paid_by FROM agent_model_certifications"))
    ).scalar_one()
    assert paid == "partner"

    async with get_sessionmaker()() as session, tenant_scoped_session(session, a):
        n = await expire_agent_certifications(session, agent_id=cfg.agent_id, reason="new_spec")
        assert n == 1
        assert not await certified_deployments_for_agent(
            session, agent_id=cfg.agent_id, agent_config_id=cfg.id, suite_revision=1
        )


async def test_agent_suites_are_single_client_batches(tenants_ab) -> None:
    async def run_test(test: SuiteTest, deployment: Any, attempt: int) -> bool:
        return True

    mixed = [
        SuiteTest(tenant_id=tenants_ab["a"], test_id="t1", critical=True),
        SuiteTest(tenant_id=tenants_ab["b"], test_id="t2", critical=True),
    ]
    with pytest.raises(SingleClientBatch):
        await certify_agent(
            tenant_id=tenants_ab["a"],
            tests=mixed,
            deployment=None,
            reference_score=90,
            reference_deployment="ref",
            run_test=run_test,
        )


# ── en segundo plano y quién paga ───────────────────────────────────────────


async def test_a_cheaper_deployment_is_certified_for_the_agent_in_the_background(
    catalog, db_session, tenants_ab
) -> None:
    a = tenants_ab["a"]
    cfg = await seed_active_agent_config(db_session, tenant_id=a, system_prompt="A", tools=[])
    snap = await _snapshot()
    current, cheaper, judge = (
        snap.deployments[catalog["claude"]],
        snap.deployments[catalog["oss"]],
        snap.deployments[catalog["judge"]],
    )
    async with get_sessionmaker()() as session, session.begin():
        for d in (current, cheaper):
            for task in ("tool_turn", "answer"):
                result = await certify_class(
                    _battery(task), d, task, run_case=_runner(), judge=judge
                )
                await record_class_certification(session, d, result)
    snap = await _snapshot()
    async with get_sessionmaker()() as session, tenant_scoped_session(session, a):
        await record_agent_certification(
            session,
            tenant_id=a,
            agent_id=cfg.agent_id,
            agent_config_id=cfg.id,
            deployment=current,
            suite_revision=1,
            result=_suite(3, score=90, reference=90),
            launched_by="partner",
        )
        todo = await background_candidates(
            session,
            snap,
            agent_id=cfg.agent_id,
            agent_config_id=cfg.id,
            suite_revision=1,
            current_key=current.key,
        )
    assert [d.key for d in todo] == [cheaper.key]

    policy = ProfilePolicy.from_row("auto", 1, {"tasks": {"tool_turn": {"min_quality": 0.9}}})

    async def chosen() -> str | None:
        async with get_sessionmaker()() as session, tenant_scoped_session(session, a):
            certified = await certified_deployments_for_agent(
                session, agent_id=cfg.agent_id, agent_config_id=cfg.id, suite_revision=1
            )
        ctx = RouteContext(
            tenant_id=a,
            catalog=snap,
            agent_id=cfg.agent_id,
            eu_only=True,
            agent_certified=certified,
            now=1.0,
        )
        return chain_for("tool_turn", policy, ctx).chosen

    # Hasta que no pase su suite, el router no lo usa con este agente.
    assert await chosen() == current.key
    async with get_sessionmaker()() as session, tenant_scoped_session(session, a):
        await record_agent_certification(
            session,
            tenant_id=a,
            agent_id=cfg.agent_id,
            agent_config_id=cfg.id,
            deployment=cheaper,
            suite_revision=1,
            result=_suite(3, 2, score=95, reference=90),
            launched_by="auphere",
        )
    assert await chosen() == current.key, "suspendió: sigue el de antes"
    async with get_sessionmaker()() as session, tenant_scoped_session(session, a):
        await record_agent_certification(
            session,
            tenant_id=a,
            agent_id=cfg.agent_id,
            agent_config_id=cfg.id,
            deployment=cheaper,
            suite_revision=1,
            result=_suite(3, 3, score=89, reference=90),
            launched_by="auphere",
        )
    assert await chosen() == cheaper.key
    payers = (
        (
            await db_session.execute(
                sa.text("SELECT paid_by FROM agent_model_certifications ORDER BY certified_at")
            )
        )
        .scalars()
        .all()
    )
    assert payers == ["partner", "auphere", "auphere"]


def test_who_pays() -> None:
    partner = payer_for("partner")
    assert (partner.paid_by, partner.usage_source) == ("partner", "tests")
    auphere = payer_for("auphere")
    assert (auphere.paid_by, auphere.usage_source) == ("auphere", "certification")
    with pytest.raises(ValueError):
        payer_for("client")
