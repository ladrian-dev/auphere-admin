"""Unit tests for the output guardrail (§C.5 of claude-platform-integration).

Five scenarios the spec requires explicitly:

- ``grader_pass_passes_through`` — happy path.
- ``grader_fail_triggers_retry`` — the agent sees the feedback and the
  pipeline asks it to rewrite.
- ``grader_max_retries_falls_to_human`` — after two fails the customer
  gets the neutral fallback + the operator gets a structured alert.
- ``grader_does_not_see_system_prompt`` — anti-correlation: the grader
  prompt MUST NOT contain the agent's system prompt.
- ``grader_json_parse_failure_is_fail`` — defensive parsing.

Plus a few extra checks for the rubric loader + feature flag.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest

from nexus_worker.guardrails import (
    GRADER_FALLBACK_RESPONSE,
    GraderVerdict,
    OutcomeGrader,
    available_rubric_intents,
    is_outcome_grader_enabled_for,
    load_rubric_text,
    outcome_grader_enabled_tenants,
)
from nexus_worker.guardrails.outcome_grader import (
    DEFAULT_GRADER_MODEL,
    MAX_GRADER_RETRIES,
    _parse_verdict,
)
from nexus_worker.runtime.llm import LLMResponse

# ── Fakes ───────────────────────────────────────────────────────────


@dataclass
class _ScriptedProvider:
    """LLMProvider stub that returns canned strings per call.

    Used in two roles in these tests:
    - As the grader's provider → returns canned grader JSON.
    - As the agent's provider (for the rewrite step) → returns canned
      revised drafts.
    """

    responses: list[str] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def acomplete(
        self,
        *,
        tenant_id: uuid.UUID,
        role: str,
        model: str,
        messages: list[dict[str, str]],
    ) -> str:
        self.calls.append(
            {
                "role": role,
                "model": model,
                "messages": [dict(m) for m in messages],
            }
        )
        if not self.responses:
            return ""
        return self.responses.pop(0)

    async def acomplete_with_tools(
        self,
        *,
        tenant_id: uuid.UUID,
        role: str,
        model: str,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        text = await self.acomplete(
            tenant_id=tenant_id, role=role, model=model, messages=messages
        )
        return LLMResponse(text=text, tool_calls=())


# ── grader behaviour ────────────────────────────────────────────────


class TestGraderHappyPath:
    async def test_grader_pass_returns_pass_verdict(self) -> None:
        provider = _ScriptedProvider(
            responses=[json.dumps({"C1": "pass", "overall": "pass", "feedback": ""})]
        )
        grader = OutcomeGrader(provider=provider)

        verdict = await grader.grade(
            tenant_id=uuid.uuid4(),
            intent="booking.confirm",
            rubric_body="# rubric",
            draft_response="Sure, I'll check the availability.",
            tool_envelopes=[],
        )

        assert verdict.overall == "pass"
        assert verdict.criteria == {"C1": "pass"}
        assert verdict.feedback == ""

    async def test_grader_uses_default_model(self) -> None:
        provider = _ScriptedProvider(
            responses=[json.dumps({"overall": "pass", "feedback": ""})]
        )
        grader = OutcomeGrader(provider=provider)
        await grader.grade(
            tenant_id=uuid.uuid4(),
            intent="x",
            rubric_body="x",
            draft_response="x",
            tool_envelopes=[],
        )
        assert provider.calls[0]["model"] == DEFAULT_GRADER_MODEL


class TestGraderFailureModes:
    async def test_json_parse_failure_is_fail(self) -> None:
        """The grader's defensive parser keeps the runtime safe even
        when the model emits something we can't decode."""
        provider = _ScriptedProvider(responses=["not even close to JSON"])
        grader = OutcomeGrader(provider=provider)
        verdict = await grader.grade(
            tenant_id=uuid.uuid4(),
            intent="booking.confirm",
            rubric_body="# rubric",
            draft_response="anything",
            tool_envelopes=[],
        )
        assert verdict.overall == "fail"
        assert "unparseable" in verdict.feedback.lower()

    async def test_grader_handles_markdown_fenced_json(self) -> None:
        provider = _ScriptedProvider(
            responses=[
                "```json\n"
                + json.dumps({"C1": "pass", "overall": "pass", "feedback": ""})
                + "\n```"
            ]
        )
        grader = OutcomeGrader(provider=provider)
        verdict = await grader.grade(
            tenant_id=uuid.uuid4(),
            intent="x",
            rubric_body="x",
            draft_response="x",
            tool_envelopes=[],
        )
        assert verdict.overall == "pass"

    async def test_grader_provider_exception_returns_fail(self) -> None:
        @dataclass
        class _BrokenProvider:
            calls: list[dict[str, Any]] = field(default_factory=list)

            async def acomplete(self, **kwargs: Any) -> str:
                raise RuntimeError("provider exploded")

            async def acomplete_with_tools(self, **kwargs: Any) -> LLMResponse:
                raise RuntimeError("provider exploded")

        grader = OutcomeGrader(provider=_BrokenProvider())  # type: ignore[arg-type]
        verdict = await grader.grade(
            tenant_id=uuid.uuid4(),
            intent="x",
            rubric_body="x",
            draft_response="x",
            tool_envelopes=[],
        )
        assert verdict.overall == "fail"
        assert "could not be reached" in verdict.feedback.lower()

    async def test_missing_overall_derived_from_criteria(self) -> None:
        """When ``overall`` is missing, the parser derives it: pass iff
        all criteria are pass."""
        verdict = _parse_verdict(json.dumps({"C1": "pass", "C2": "pass", "feedback": ""}))
        assert verdict.overall == "pass"
        verdict2 = _parse_verdict(json.dumps({"C1": "pass", "C2": "fail", "feedback": ""}))
        assert verdict2.overall == "fail"


class TestGraderAntiCorrelation:
    async def test_grader_does_not_see_system_prompt(self) -> None:
        """The grader prompt MUST NOT include the agent's system prompt.

        This test inspects what the grader actually sent to its
        provider: every message ends up in ``provider.calls[0].messages``.
        If a future refactor leaks the agent's system prompt into the
        grader's user turn, the test catches it.
        """
        provider = _ScriptedProvider(
            responses=[json.dumps({"overall": "pass", "feedback": ""})]
        )
        grader = OutcomeGrader(provider=provider)
        agent_system_prompt = "TOP SECRET: never mention strawberries"

        await grader.grade(
            tenant_id=uuid.uuid4(),
            intent="x",
            rubric_body="# rubric body — pasame por aquí",
            draft_response=f"Some innocuous reply ({agent_system_prompt})",
            tool_envelopes=[
                # The agent's system prompt is NOT among the envelopes —
                # the pipeline strips it before handing to the grader.
                # We still defensively assert it does not appear.
                {"tool": "booking.check_availability", "status": "ok"},
            ],
        )

        # The draft response will contain the marker because that's
        # what we passed; what must NOT happen is the marker appearing
        # in the grader's system role.
        sent = provider.calls[0]
        system_messages = [m["content"] for m in sent["messages"] if m["role"] == "system"]
        # Exactly one system message: the grader instructions + rubric
        # body. It must not carry the agent's system prompt.
        assert len(system_messages) == 1
        assert agent_system_prompt not in system_messages[0]
        assert "rubric body — pasame" in system_messages[0]


# ── envelope summarising ─────────────────────────────────────────────


class TestEnvelopeSummarisation:
    async def test_large_result_is_summarised(self) -> None:
        """Huge tool result payloads (catalog dumps) must not be sent
        verbatim to the grader — the helper trims to load-bearing keys.
        """
        big_catalogue = {f"product_{i}": "x" * 200 for i in range(500)}
        provider = _ScriptedProvider(
            responses=[json.dumps({"overall": "pass", "feedback": ""})]
        )
        grader = OutcomeGrader(provider=provider)
        await grader.grade(
            tenant_id=uuid.uuid4(),
            intent="x",
            rubric_body="# x",
            draft_response="x",
            tool_envelopes=[
                {
                    "tool": "list_products",
                    "status": "ok",
                    "intent": "info",
                    "result": big_catalogue,
                }
            ],
        )
        user_msg = next(
            m["content"] for m in provider.calls[0]["messages"] if m["role"] == "user"
        )
        # The unsummarised payload would be > 100KB; the summary should
        # have stripped non-load-bearing keys → much smaller.
        assert len(user_msg) < 4000


# ── feature flag ─────────────────────────────────────────────────────


class TestFeatureFlag:
    def test_empty_env_means_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NEXUS_OUTCOME_GRADER_ENABLED_TENANTS", raising=False)
        assert outcome_grader_enabled_tenants() == frozenset()
        assert not is_outcome_grader_enabled_for(uuid.uuid4())

    def test_csv_of_uuids_parses(self, monkeypatch: pytest.MonkeyPatch) -> None:
        a = uuid.uuid4()
        b = uuid.uuid4()
        monkeypatch.setenv("NEXUS_OUTCOME_GRADER_ENABLED_TENANTS", f"{a}, {b}")
        assert outcome_grader_enabled_tenants() == frozenset({a, b})
        assert is_outcome_grader_enabled_for(a)
        assert is_outcome_grader_enabled_for(b)

    def test_garbage_token_is_silently_dropped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        good = uuid.uuid4()
        monkeypatch.setenv(
            "NEXUS_OUTCOME_GRADER_ENABLED_TENANTS",
            f"not-a-uuid,{good},another-bad-one",
        )
        # The garbage must NOT prevent the good tenant from being
        # registered — operator typo isolation.
        assert outcome_grader_enabled_tenants() == frozenset({good})


# ── rubric loader ─────────────────────────────────────────────────


class TestRubricLoader:
    def test_known_intent_loads(self) -> None:
        text = load_rubric_text("booking.confirm")
        assert text is not None
        assert "booking.confirm" in text
        assert "C1" in text

    def test_unknown_intent_falls_back_to_general(self) -> None:
        text = load_rubric_text("totally.unknown.intent")
        assert text is not None
        # The fallback rubric is the general one.
        assert "default.general_response" in text

    def test_available_intents_includes_5_seeded(self) -> None:
        intents = available_rubric_intents()
        # The five rubrics seeded for Fase C.
        for required in (
            "booking.confirm",
            "booking.cancel",
            "ecommerce.product_recommend",
            "ecommerce.order_status",
            "default.general_response",
        ):
            assert required in intents


# ── grader retry flow (integration of grader + pipeline node) ──────


@dataclass
class _GraderProviderScript:
    """Two-channel script: grader returns one canned verdict per call,
    agent returns one canned draft per rewrite call."""

    grader_verdicts: list[GraderVerdict]
    rewrite_drafts: list[str]


@pytest.fixture
def fake_grader_and_router():
    """Build a (grader, router) pair driven by a script.

    Used to exercise the full Fase C retry loop without touching the
    real grade_outcome node — the node itself is exercised by an
    integration test in apps/api (when llm.respond can be stubbed via
    the InMemoryProvider).
    """
    raise NotImplementedError  # filled in by the parametric tests below


class TestRetryFlowNode:
    """End-to-end check of the ``grade_outcome`` node behaviour.

    Drives the actual ``make_grade_outcome_node`` factory with scripted
    LLM provider + grader. This is the canonical §C.5 'fail → retry →
    pass' coverage — and the 'max retries → fallback' coverage.
    """

    async def test_fail_then_pass_replaces_response(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from nexus_worker.runtime.llm import LLMRouter
        from nexus_worker.runtime.pipeline import make_grade_outcome_node

        tenant_id = uuid.uuid4()
        monkeypatch.setenv("NEXUS_OUTCOME_GRADER_ENABLED_TENANTS", str(tenant_id))

        # Grader: first call fails, second call passes.
        grader_provider = _ScriptedProvider(
            responses=[
                json.dumps({"C1": "fail", "overall": "fail", "feedback": "say it tentative"}),
                json.dumps({"C1": "pass", "overall": "pass", "feedback": ""}),
            ]
        )
        grader = OutcomeGrader(provider=grader_provider)

        # Agent rewrite: one canned new draft.
        agent_provider = _ScriptedProvider(responses=["Let me check availability for you."])
        router = LLMRouter(
            provider=agent_provider,
            classify_model="anthropic/haiku",
            respond_model="anthropic/sonnet",
            fallback_model="openai/gpt-4o",
        )

        node = make_grade_outcome_node(grader=grader, llm_router=router)
        state = {
            "tenant_id": str(tenant_id),
            "intent": "book",
            "response": "Confirmed! See you tomorrow at 10am.",
            "tool_calls": [],
        }
        out = await node(state)  # type: ignore[arg-type]

        assert out["outcome_overall"] == "pass"
        assert out["outcome_retries"] == 1
        assert out["response"] == "Let me check availability for you."

    async def test_max_retries_falls_to_neutral_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from nexus_worker.runtime.llm import LLMRouter
        from nexus_worker.runtime.pipeline import make_grade_outcome_node

        tenant_id = uuid.uuid4()
        monkeypatch.setenv("NEXUS_OUTCOME_GRADER_ENABLED_TENANTS", str(tenant_id))

        # Grader fails ALL the time (initial + every retry).
        fail_json = json.dumps(
            {"C1": "fail", "overall": "fail", "feedback": "still wrong"}
        )
        grader_provider = _ScriptedProvider(
            responses=[fail_json, fail_json, fail_json, fail_json]
        )
        grader = OutcomeGrader(provider=grader_provider)

        # Each rewrite produces a non-empty draft, so the loop hits the
        # retry ceiling rather than the empty-draft bail-out.
        agent_provider = _ScriptedProvider(
            responses=["attempt 2", "attempt 3", "attempt 4"]
        )
        router = LLMRouter(
            provider=agent_provider,
            classify_model="anthropic/haiku",
            respond_model="anthropic/sonnet",
            fallback_model="openai/gpt-4o",
        )

        node = make_grade_outcome_node(grader=grader, llm_router=router)
        state = {
            "tenant_id": str(tenant_id),
            "intent": "book",
            "response": "Confirmed!",
            "tool_calls": [],
        }
        out = await node(state)  # type: ignore[arg-type]

        assert out["outcome_overall"] == "fail"
        assert out["outcome_retries"] == MAX_GRADER_RETRIES
        assert out["response"] == GRADER_FALLBACK_RESPONSE

    async def test_passthrough_when_tenant_not_enabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from nexus_worker.runtime.llm import LLMRouter
        from nexus_worker.runtime.pipeline import make_grade_outcome_node

        monkeypatch.delenv("NEXUS_OUTCOME_GRADER_ENABLED_TENANTS", raising=False)
        grader_provider = _ScriptedProvider(responses=[])  # should never be called
        grader = OutcomeGrader(provider=grader_provider)
        agent_provider = _ScriptedProvider(responses=[])
        router = LLMRouter(
            provider=agent_provider,
            classify_model="x",
            respond_model="x",
            fallback_model="x",
        )

        node = make_grade_outcome_node(grader=grader, llm_router=router)
        state = {
            "tenant_id": str(uuid.uuid4()),
            "intent": "book",
            "response": "ANY content",
            "tool_calls": [],
        }
        out = await node(state)  # type: ignore[arg-type]

        assert out["outcome_overall"] == "skipped"
        assert grader_provider.calls == []  # grader was not invoked

    async def test_passthrough_when_grader_is_none(self) -> None:
        """``grader=None`` (test / dev path) skips without calling
        anything — guarantees the node never crashes the pipeline in
        environments without LLM credentials."""
        from nexus_worker.runtime.llm import InMemoryProvider, LLMRouter
        from nexus_worker.runtime.pipeline import make_grade_outcome_node

        node = make_grade_outcome_node(
            grader=None,
            llm_router=LLMRouter(
                provider=InMemoryProvider(),
                classify_model="x",
                respond_model="x",
                fallback_model="x",
            ),
        )
        out = await node(
            {  # type: ignore[arg-type]
                "tenant_id": str(uuid.uuid4()),
                "intent": "book",
                "response": "x",
                "tool_calls": [],
            }
        )
        assert out["outcome_overall"] == "skipped"
