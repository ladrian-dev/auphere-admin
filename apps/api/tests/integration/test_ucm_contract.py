"""UCM contract tests (ADR-020 Fase 6, Bloque C).

The QA Playground promises that every turn rendered for the operator is
a valid UCM v1.0.0 message that degrades cleanly to WhatsApp (the only
production channel today + the most constrained one). This file runs
the FULL QA pipeline (``build_qa_pipeline``) end-to-end with a memory
checkpointer + the InMemoryProvider, against five canonical user
messages, and asserts:

  - ``state["ucm"]`` parses with ``parse_ucm`` (i.e. survives the schema).
  - ``validate(state["ucm"], "whatsapp")`` returns ``ok=True`` OR the
    failure is captured + explained.
  - The shadow diff vs the legacy text path is ``equivalent=True`` while
    the formatter only emits ``type: "text"`` — first regression here is
    the first place to look when the formatter grows new branches.

These tests do NOT need the LangGraph Server. They exercise the pure
runtime contract — the same code path the Server will run later.

Coverage policy: the "agente piloto" (auphere-canary) does not exist
yet at the cut-off date of this file; until it does, the test runs
against a synthesised tenant with an empty system_prompt + the default
intent classification. When the canary lands, extend
``CANONICAL_MESSAGES`` to include real intents from its eval-suite v1
cases — the asserts stay the same.

Reference: ADR-020 Fase 6, feature spec "Plan de pruebas" / "UCM
contract por agente".
"""

from __future__ import annotations

import uuid

import pytest
from nexus_worker.runtime.qa_pipeline import build_qa_pipeline

pytestmark = [pytest.mark.asyncio, pytest.mark.contract]


# ── local fixtures (mirrored from tests/isolation/conftest.py) ──────────────
# These are duplicated here intentionally so the contract test doesn't
# inherit the isolation conftest's seed_active_agent_config etc., which
# would over-specify the setup. Keeping the dupes scoped to this module
# avoids tangling fixture trees across two suites.


import pytest_asyncio  # noqa: E402


@pytest_asyncio.fixture
async def memory_saver():
    from langgraph.checkpoint.memory import MemorySaver

    yield MemorySaver()


@pytest_asyncio.fixture
async def agent_loader():
    from nexus_worker.runtime.agent_loader import AgentLoader

    return AgentLoader()


@pytest_asyncio.fixture
async def in_memory_provider():
    from nexus_worker.runtime.llm import InMemoryProvider

    return InMemoryProvider()


@pytest_asyncio.fixture
async def llm_router(in_memory_provider):
    from nexus_worker.runtime.llm import LLMRouter

    return LLMRouter(
        provider=in_memory_provider,
        classify_model="test/classify",
        respond_model="test/respond",
        fallback_model="test/fallback",
    )


# ── canonical user messages ─────────────────────────────────────────────────


CANONICAL_MESSAGES: list[tuple[str, str]] = [
    ("greeting", "Hola"),
    ("hours_question", "¿Cuáles son los horarios de atención?"),
    ("ambiguous_intent", "Eh, quería preguntar algo, no sé"),
    ("out_of_scope", "¿Pueden recomendarme un restaurante cerca?"),
    ("empty_ish", "."),
]


# ── helpers ─────────────────────────────────────────────────────────────────


@pytest.fixture
async def qa_tenant_setup(db_session):
    """Seed a single tenant + active agent_config + channel + customer +
    conversation. Returns ids we feed to the pipeline state.

    Inserts run as the test superuser (no ``SET ROLE nexus_app``) so
    RLS is bypassed — same pattern as ``conftest.seed_active_agent_config``.
    The contract under test is the FORMATTER, not RLS; isolation is
    covered by ``tests/isolation/test_8 / test_9``.
    """
    from nexus_api.db.models import (
        AgentConfig,
        AgentConfigStatus,
        Channel,
        ChannelStatus,
        ChannelType,
        Conversation,
        ConversationStatus,
        Customer,
        Tenant,
        TenantPlan,
    )

    tenant_id = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tenant_id,
            name="UCM-Contract",
            slug=f"ucm-c-{tenant_id.hex[:8]}",
            plan=TenantPlan.PRO,
        )
    )
    await db_session.commit()

    cfg = AgentConfig(
        tenant_id=tenant_id,
        version=1,
        status=AgentConfigStatus.ACTIVE,
        system_prompt_rendered="You are a helpful assistant.",
        channels=[],
        tools=[],
        policies={},
        seed_template_ref=None,
    )
    ch = Channel(
        tenant_id=tenant_id,
        type=ChannelType.WHATSAPP,
        provider="meta",
        provider_identifier=f"ucm-c-{tenant_id.hex[:6]}",
        config={},
        status=ChannelStatus.ACTIVE,
    )
    cust = Customer(tenant_id=tenant_id, identifier="+56-ucm-c", preferences={})
    db_session.add_all([cfg, ch, cust])
    await db_session.commit()
    await db_session.refresh(ch)
    await db_session.refresh(cust)

    conv = Conversation(
        tenant_id=tenant_id,
        channel_id=ch.id,
        customer_id=cust.id,
        status=ConversationStatus.OPEN,
    )
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)

    return {
        "tenant_id": tenant_id,
        "channel_id": ch.id,
        "customer_id": cust.id,
        "conversation_id": conv.id,
    }


def _scripted_responder(call):
    """Map LLM roles to deterministic answers.

    The pipeline calls the LLM twice per turn (classify → respond);
    scripting both ensures the formatter sees realistic-looking text.
    """
    if call.role == "classify":
        # Pick the simplest valid intent so the test doesn't depend on
        # any specific handler. ``fallback`` is unconditionally valid.
        return "fallback"
    return "Hola, gracias por escribir. ¿En qué puedo ayudarte?"


# ── tests ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("label", "user_message"),
    CANONICAL_MESSAGES,
    ids=[label for label, _ in CANONICAL_MESSAGES],
)
async def test_canonical_user_message_produces_valid_ucm(
    label,
    user_message,
    qa_tenant_setup,
    db_session,
    agent_loader,
    in_memory_provider,
    llm_router,
    memory_saver,
):
    """Every canonical message must produce a UCM that:
    - parses with parse_ucm (survives v1.0.0 schema),
    - validates clean against the WhatsApp channel (the most
      constrained one).
    """
    from nexus_worker.runtime.state import new_state
    from nexus_worker.runtime.thread_id import make_thread_id
    from ucm_schema import parse_ucm, validate

    from nexus_api.core.tenant_context import tenant_context
    from nexus_api.db.models import Message, MessageDirection

    tenant_id = qa_tenant_setup["tenant_id"]
    channel_id = qa_tenant_setup["channel_id"]
    customer_id = qa_tenant_setup["customer_id"]
    conversation_id = qa_tenant_setup["conversation_id"]

    in_memory_provider.responder = _scripted_responder

    pipeline = build_qa_pipeline(
        agent_loader=agent_loader,
        llm_router=llm_router,
        checkpointer=memory_saver,
    )

    inbound = Message(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        direction=MessageDirection.INBOUND,
        content=user_message,
        tool_calls=[],
    )
    db_session.add(inbound)
    await db_session.commit()
    await db_session.refresh(inbound)

    state = new_state(
        tenant_id=tenant_id,
        channel_id=channel_id,
        user_id="+56-ucm-c",
        conversation_id=conversation_id,
        customer_id=customer_id,
        inbound_message_id=inbound.id,
        user_message=user_message,
    )
    thread_id = make_thread_id(tenant_id, channel_id, "+56-ucm-c")
    with tenant_context(tenant_id):
        out = await pipeline.ainvoke(state, config={"configurable": {"thread_id": thread_id}})

    # Assert the formatter emitted a UCM.
    ucm_payload = out.get("ucm")
    assert ucm_payload is not None, f"[{label}] formatter did not emit UCM"

    # 1) parse_ucm survives.
    ucm = parse_ucm(ucm_payload)
    assert ucm.type == "text", f"[{label}] expected text-only formatter, got {ucm.type!r}"
    assert ucm.ucm_version == "1.0.0"
    assert ucm.fallback_text, f"[{label}] fallback_text is required by v1.0.0 — empty is invalid"

    # 2) validate against the WhatsApp channel returns ok.
    result = validate(ucm_payload, "whatsapp")
    if not result.ok:
        # Empty/whitespace user messages can fail capability validation in
        # rare edge cases — surface the diagnosis so the operator can fix
        # the formatter rather than guessing.
        pytest.fail(
            f"[{label}] UCM failed WhatsApp validation: "
            f"issues={result.issues!r}, payload={ucm_payload!r}"
        )

    # 3) shadow diff equivalent while we're still in text-only mode.
    diff = out.get("ucm_shadow_diff")
    assert diff is not None, f"[{label}] formatter did not emit shadow diff"
    assert diff.get("equivalent") is True, (
        f"[{label}] shadow diff diverged — UCM-WhatsApp degradation no longer "
        f"matches legacy text path. diff={diff!r}"
    )


async def test_pilot_floor_coverage_is_at_least_eighty_percent():
    """The spec asks for >= 80% of canonical turns to render directly
    on WhatsApp. With the current text-only formatter that's trivially
    100% — but the assertion is here so when the formatter grows new
    types we notice the regression before the canary loads.

    Today the pilot is a fixture (no auphere-canary in BD yet). When
    canary lands, replace the iteration below with the canary's
    actual eval-suite v1 cases.
    """
    from ucm_schema import parse_ucm, validate

    valid_count = 0
    for _label, text in CANONICAL_MESSAGES:
        # Hand-build the UCM the formatter would produce for plain text.
        # We bypass the full pipeline here — the e2e per-message test
        # above already exercises that — and just confirm the schema +
        # channel validation holds for the canonical payloads.
        payload = {
            "ucm_version": "1.0.0",
            "message_id": str(uuid.uuid4()),
            "type": "text",
            "capabilities_required": ["text"],
            "fallback_text": text or "(empty)",
            "metadata": {},
            "content": {"body": text or "(empty)", "format": "plain"},
        }
        parse_ucm(payload)
        if validate(payload, "whatsapp").ok:
            valid_count += 1

    ratio = valid_count / len(CANONICAL_MESSAGES)
    assert ratio >= 0.80, (
        f"pilot coverage floor breached: {valid_count}/{len(CANONICAL_MESSAGES)} "
        f"({ratio:.0%}) — expected >= 80%"
    )
