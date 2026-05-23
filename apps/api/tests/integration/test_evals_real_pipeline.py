"""Roadmap E2 — the eval runner drives the REAL production pipeline.

Before E2 the runner drove the Bloque O sandbox: a different code path
that never executed a tool. This test proves the migration end to end:

1. ``run_eval`` runs each case through the real compiled graph — a tool
   is actually dispatched and its result is fed back into the LLM
   context (the ADR-023 loop).
2. The runner evaluates the EXACT ``agent_config`` passed in, even when
   it is a STAGED candidate that is NOT the tenant's active config. The
   tenant here has an ACTIVE v1 with an EMPTY whitelist; the run targets
   STAGED v2 whose whitelist includes ``client.get_history``. If the
   pinned loader leaked the active row, the tool would come back
   ``skipped:not_in_whitelist`` instead of ``ok``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from nexus_worker.runtime.llm import InMemoryProvider, LLMRouter, ToolCall

from nexus_api.db.models import (
    AgentConfig,
    AgentConfigStatus,
    EvalCase,
    EvalDataset,
    EvalRun,
    EvalRunResult,
    EvalRunStatus,
    Tenant,
    TenantPlan,
)
from nexus_api.services.evals import FakeJudgeProvider, run_eval, set_eval_llm_router

from ..isolation.conftest import (  # type: ignore[import-not-found]
    seed_active_agent_config,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_FINAL_ANSWER = "Tu última visita fue hace dos semanas, ¿querés repetir el mismo corte?"


async def test_eval_runner_drives_real_pipeline_against_staged_candidate(db_session) -> None:
    tenant_id = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tenant_id,
            name="EvalReal",
            slug=f"evalreal-{tenant_id.hex[:6]}",
            plan=TenantPlan.PRO,
        )
    )
    await db_session.commit()

    # ACTIVE v1 — empty whitelist. If the runner evaluated THIS instead of
    # the staged candidate, client.get_history would be rejected.
    await seed_active_agent_config(
        db_session,
        tenant_id=tenant_id,
        system_prompt="prompt v1 — sin tools",
        tools=[],
    )
    # STAGED v2 — the candidate under test, whitelists client.get_history.
    staged = AgentConfig(
        tenant_id=tenant_id,
        version=2,
        status=AgentConfigStatus.STAGED,
        system_prompt_rendered="Sos el asistente de la barbería.",
        channels=[],
        tools=["client.get_history"],
        policies={},
    )
    db_session.add(staged)
    await db_session.commit()
    await db_session.refresh(staged)

    # ── dataset + one case that expects the tool to be called ────────────
    dataset = EvalDataset(
        tenant_id=tenant_id,
        name="real-pipeline",
        description="E2 proof",
        version=1,
    )
    db_session.add(dataset)
    await db_session.flush()
    case = EvalCase(
        tenant_id=tenant_id,
        dataset_id=dataset.id,
        idx=0,
        name="lo de siempre",
        user_message="hola, lo de siempre",
        history=[],
        assertions={
            "must_emit_text": True,
            "expected_tools_called": ["client.get_history"],
            "judge_questions": ["¿usó el historial del cliente?"],
        },
    )
    db_session.add(case)
    await db_session.flush()

    run = EvalRun(
        tenant_id=tenant_id,
        dataset_id=dataset.id,
        dataset_version=dataset.version,
        agent_config_version=staged.version,
        agent_config_status=staged.status.value,
        status=EvalRunStatus.PENDING.value,
        actor="test",
        started_at=datetime.now(UTC),
    )
    db_session.add(run)
    await db_session.flush()

    # ── scripted model: classify → info; the info handler asks for the
    # tool on iteration 0, then answers once the tool result is in
    # context (the ADR-023 loop). ────────────────────────────────────────
    provider = InMemoryProvider()

    def _has_tool_msg(call: object) -> bool:
        return any(m.get("role") == "tool" for m in getattr(call, "messages", []))

    def responder(call: object) -> str:
        if getattr(call, "role", "") == "classify":
            return "info"
        return _FINAL_ANSWER if _has_tool_msg(call) else ""

    def tool_caller(call: object) -> list[ToolCall]:
        if getattr(call, "role", "") == "info" and not _has_tool_msg(call):
            return [
                ToolCall(
                    id="t1",
                    name="client.get_history",
                    arguments={"customer_id": str(uuid.uuid4()), "limit": 5},
                )
            ]
        return []

    provider.responder = responder
    provider.tool_caller = tool_caller
    router = LLMRouter(
        provider=provider,
        classify_model="t/c",
        respond_model="t/r",
        fallback_model="t/f",
    )
    set_eval_llm_router(router)
    try:
        outcome = await run_eval(
            db_session,
            tenant_id=tenant_id,
            run=run,
            dataset=dataset,
            cases=[case],
            agent_config=staged,
            judge_provider=FakeJudgeProvider(),
        )
    finally:
        set_eval_llm_router(None)

    # ── the run passed against the STAGED candidate ──────────────────────
    assert outcome.status is EvalRunStatus.PASSED
    assert outcome.pass_count == 1

    result = (
        await db_session.execute(
            EvalRunResult.__table__.select().where(EvalRunResult.run_id == run.id)
        )
    ).first()
    assert result is not None
    transcript = result.transcript
    assert transcript["intent"] == "info"
    assert transcript["assistant_message"] == _FINAL_ANSWER

    # ── the tool actually RAN through the real registry — and the pinned
    # STAGED whitelist was used (else it would be skipped). ───────────────
    tool_calls = transcript["tool_calls"]
    history_calls = [tc for tc in tool_calls if tc["name"] == "client.get_history"]
    assert history_calls, "client.get_history was never dispatched"
    assert history_calls[0]["status"] == "ok", history_calls[0]
    assert all(tc["status"] != "skipped:not_in_whitelist" for tc in tool_calls)

    # ── the decisive ADR-023 assertion: the SECOND handler LLM call
    # carries a role:"tool" message — the real result fed back. ───────────
    info_calls = [c for c in provider.calls if c.role == "info"]
    assert len(info_calls) == 2, "the handler should loop exactly twice"
    first_call, second_call = info_calls
    assert not any(m.get("role") == "tool" for m in first_call.messages)
    tool_msgs = [m for m in second_call.messages if m.get("role") == "tool"]
    assert tool_msgs, "the tool result never reached the responding LLM"
    assert tool_msgs[0]["tool_call_id"] == "t1"


async def test_eval_runner_fails_run_when_system_prompt_empty(db_session) -> None:
    """A candidate with no system prompt is a setup failure — the driver
    raises and the endpoint records the run as ``error``; here we assert
    the raise reaches the caller."""
    from nexus_api.services.evals import EvalDriverError

    tenant_id = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tenant_id,
            name="EvalEmpty",
            slug=f"evalempty-{tenant_id.hex[:6]}",
            plan=TenantPlan.PRO,
        )
    )
    await db_session.commit()

    blank = AgentConfig(
        tenant_id=tenant_id,
        version=1,
        status=AgentConfigStatus.STAGED,
        system_prompt_rendered="   ",
        channels=[],
        tools=[],
        policies={},
    )
    db_session.add(blank)
    await db_session.commit()
    await db_session.refresh(blank)

    dataset = EvalDataset(tenant_id=tenant_id, name="blank", version=1)
    db_session.add(dataset)
    await db_session.flush()
    case = EvalCase(
        tenant_id=tenant_id,
        dataset_id=dataset.id,
        idx=0,
        name="c",
        user_message="hola",
        history=[],
        assertions={"must_emit_text": True},
    )
    db_session.add(case)
    await db_session.flush()
    run = EvalRun(
        tenant_id=tenant_id,
        dataset_id=dataset.id,
        dataset_version=dataset.version,
        agent_config_version=blank.version,
        agent_config_status=blank.status.value,
        status=EvalRunStatus.PENDING.value,
        actor="test",
        started_at=datetime.now(UTC),
    )
    db_session.add(run)
    await db_session.flush()

    with pytest.raises(EvalDriverError, match="system_prompt"):
        await run_eval(
            db_session,
            tenant_id=tenant_id,
            run=run,
            dataset=dataset,
            cases=[case],
            agent_config=blank,
            judge_provider=FakeJudgeProvider(),
        )
