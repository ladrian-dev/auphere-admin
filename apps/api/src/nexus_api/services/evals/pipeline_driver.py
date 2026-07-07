"""Eval pipeline driver — runs a case through the REAL production graph.

Before Fase 1 of the agent-quality-roadmap the eval runner drove the
Bloque O sandbox (``run_test_turn``): a different code path from
production, capped at two LLM calls, and one that never actually
executed a tool. The promotion gate validated something prod never
runs.

This module replaces that path. It compiles the SAME graph the worker
runs (``build_pipeline``) and the QA Playground runs (``qa_pipeline``):
the real ReAct loop, real tool dispatch, real history loading. Two
deliberate differences from a production turn:

1. The MCP registry is built ``dry_run=True`` — exactly like the QA
   Playground — so a side-effecting tool (``booking.create_appointment``
   …) returns a synthetic envelope instead of hitting a real provider.
   Read tools run for real. No QA audit writer is wired: evals are not
   QA threads, so blocked side-effects are simply not persisted.
2. The ``AgentLoader`` is *pinned* (``AgentLoader.prime``) to the exact
   ``agent_config`` version under test. The promotion gate evaluates a
   STAGED candidate before it becomes ACTIVE; a plain loader would read
   ``get_active()`` and evaluate the wrong row.

The real graph loads conversation history from the DB by
``conversation_id`` — it ignores any ``history`` passed in state. So a
case's synthetic ``history`` is seeded as real ``messages`` rows on an
ephemeral conversation, the graph runs, and the conversation is deleted
afterwards (``messages`` cascade). Each case is fully isolated: its own
customer + conversation, on a dedicated per-tenant ``eval_runner`` web
channel that never sends anything externally.

Reference: agent-quality-roadmap E2 · ADR-023 · ADR-021.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog

from nexus_api.core.tenant_context import tenant_context, tenant_scoped_session
from nexus_api.db.base import get_sessionmaker

if TYPE_CHECKING:
    from nexus_worker.runtime.llm import LLMRouter

    from nexus_api.db.models import AgentConfig, Channel

log = structlog.get_logger(__name__)


# ── public result shape ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class PipelineTurnResult:
    """Outcome of one case driven through the real graph.

    ``tool_calls`` is adapted from the graph's tool envelopes into the
    flat shape the assertion engine + judge expect: each entry has
    ``name`` / ``arguments`` plus the REAL ``status`` and ``result`` the
    tool returned (the sandbox could only ever supply a placeholder).
    """

    assistant_message: str
    tool_calls: tuple[dict[str, Any], ...]
    intent: str | None
    model: str | None
    latency_ms: int


class EvalDriverError(Exception):
    """The driver could not run the case for a setup reason (no system
    prompt, graph build failure, …) — distinct from a per-case error."""


# ── LLM router injection (test hook) ─────────────────────────────────────────


_eval_router: LLMRouter | None = None


def set_eval_llm_router(router: LLMRouter | None) -> None:
    """Test hook — inject an ``InMemoryProvider``-backed router so the
    eval suite never touches LiteLLM. Production callers leave this
    unset and the driver builds a real LiteLLM router."""
    global _eval_router
    _eval_router = router


def _resolve_router() -> LLMRouter:
    if _eval_router is not None:
        return _eval_router
    # Same wiring the QA Playground uses (qa.py::_get_qa_pipeline).
    from nexus_worker.runtime.llm import LiteLLMProvider, LLMRouter

    return LLMRouter(
        provider=LiteLLMProvider(),
        classify_model="anthropic/claude-haiku-4-5-20251001",
        respond_model="anthropic/claude-sonnet-4-6",
        fallback_model="openai/gpt-4o",
    )


# ── dry-run registry (process-cached) ────────────────────────────────────────


_eval_registry: Any | None = None


def _build_eval_registry() -> Any:
    """A dry-run ``MCPRegistry`` that shares the default tool instances.

    We do NOT mutate ``build_default_registry()``'s process singleton
    into dry_run mode (``qa_pipeline`` does, but that registry is owned
    by the QA path). Instead we layer a fresh registry view over the
    same tool instances — the same copy trick ``pipeline._view_with_
    composio`` uses — so the eval path is dry_run regardless of whether
    QA has run in this process. ``dry_run_audit=None``: evals are not QA
    threads, so blocked side-effects are not persisted anywhere.
    """
    global _eval_registry
    if _eval_registry is not None:
        return _eval_registry

    from nexus_mcp import MCPRegistry, build_default_registry

    base = build_default_registry()
    view = MCPRegistry(dry_run=True, dry_run_audit=None)
    for name in base.names():
        view._tools[name] = base._tools[name]
    for name in base.internal_names():
        view._internal_tools[name] = base._internal_tools[name]
    _eval_registry = view
    return view


def reset_eval_registry() -> None:
    """Test helper — drop the cached registry between processes."""
    global _eval_registry
    _eval_registry = None


# ── driver ───────────────────────────────────────────────────────────────────

_EVAL_CHANNEL_PROVIDER = "eval_runner"


@dataclass
class EvalPipelineDriver:
    """Runs cases of one eval run through the real compiled graph.

    Built once per ``EvalRun`` (the pinned ``agent_config`` is fixed for
    the whole run); ``run_case`` is then called per case. The compiled
    graph is stateless — each case brings its own ephemeral conversation
    and a unique ``thread_id``."""

    tenant_id: uuid.UUID
    pipeline: Any
    channel_id: uuid.UUID
    case_timeout_s: float = 120.0

    async def run_case(
        self,
        *,
        history: list[dict[str, str]],
        user_message: str,
    ) -> PipelineTurnResult:
        """Seed an ephemeral conversation for this case, drive the graph,
        then delete the conversation (messages cascade).

        The case's ``history`` is written as real ``messages`` rows with
        explicit, monotonically increasing ``created_at`` values so the
        graph's ``_load_recent_history`` (which orders by ``created_at``)
        replays them deterministically.
        """
        started = time.perf_counter()
        sm = get_sessionmaker()

        conversation_id: uuid.UUID | None = None
        customer_id: uuid.UUID | None = None
        try:
            # ── seed: customer + conversation + history + inbound ────────
            async with sm() as session, tenant_scoped_session(session, self.tenant_id):
                (
                    conversation_id,
                    customer_id,
                    customer_identifier,
                    inbound_id,
                ) = await self._seed_case(session, history=history, user_message=user_message)

            # ── invoke the real graph (outside any tx — it opens its own) ─
            state: dict[str, Any] = {
                "tenant_id": str(self.tenant_id),
                "channel_id": str(self.channel_id),
                "channel_type": "web",
                "user_id": customer_identifier,
                "conversation_id": str(conversation_id),
                "customer_id": str(customer_id),
                "inbound_message_id": str(inbound_id),
                "user_message": user_message,
            }
            config = {"configurable": {"thread_id": str(conversation_id)}}
            with tenant_context(self.tenant_id):
                final = await asyncio.wait_for(
                    self.pipeline.ainvoke(state, config=config),
                    timeout=self.case_timeout_s,
                )

            latency_ms = int((time.perf_counter() - started) * 1000)
            return _adapt_final_state(final or {}, latency_ms=latency_ms)
        finally:
            # ── cleanup: drop the ephemeral conversation + customer ──────
            if conversation_id is not None or customer_id is not None:
                await self._cleanup(sm, conversation_id, customer_id)

    async def _seed_case(
        self,
        session: Any,
        *,
        history: list[dict[str, str]],
        user_message: str,
    ) -> tuple[uuid.UUID, uuid.UUID, str, uuid.UUID]:
        from nexus_api.db.models import (
            Conversation,
            ConversationStatus,
            Customer,
            Message,
            MessageDirection,
            MessageStatus,
        )

        identifier = f"eval::{uuid.uuid4().hex}"
        customer = Customer(
            tenant_id=self.tenant_id,
            identifier=identifier,
            name="Eval case",
            preferences={"eval": True},
        )
        session.add(customer)
        await session.flush()

        conversation = Conversation(
            tenant_id=self.tenant_id,
            channel_id=self.channel_id,
            customer_id=customer.id,
            status=ConversationStatus.OPEN,
        )
        session.add(conversation)
        await session.flush()

        # Explicit increasing timestamps: every row in this tx would
        # otherwise share the transaction's ``now()``, and the graph
        # orders history by ``created_at`` — same timestamp == scrambled
        # history. Space the seeded turns one second apart; the inbound
        # (current turn) lands last.
        base = datetime.now(UTC) - timedelta(seconds=len(history) + 1)
        for i, turn in enumerate(history):
            role = turn.get("role")
            direction = MessageDirection.INBOUND if role == "user" else MessageDirection.OUTBOUND
            session.add(
                Message(
                    tenant_id=self.tenant_id,
                    conversation_id=conversation.id,
                    direction=direction,
                    status=MessageStatus.SENT,
                    content=turn.get("content") or "",
                    tool_calls=[],
                    created_at=base + timedelta(seconds=i),
                )
            )
        inbound = Message(
            tenant_id=self.tenant_id,
            conversation_id=conversation.id,
            direction=MessageDirection.INBOUND,
            status=MessageStatus.SENT,
            content=user_message,
            tool_calls=[],
            created_at=base + timedelta(seconds=len(history)),
        )
        session.add(inbound)
        await session.flush()
        return conversation.id, customer.id, identifier, inbound.id

    async def _cleanup(
        self,
        sm: Any,
        conversation_id: uuid.UUID | None,
        customer_id: uuid.UUID | None,
    ) -> None:
        """Best-effort delete of the ephemeral case data. Deleting the
        conversation cascades its ``messages`` (FK ``ON DELETE CASCADE``),
        including the outbound row the graph's ``checkpoint`` node wrote.
        A failure here must not fail the case — it is logged and left for
        a later sweep."""
        import sqlalchemy as sa

        from nexus_api.db.models import Conversation, Customer

        try:
            async with sm() as session, tenant_scoped_session(session, self.tenant_id):
                if conversation_id is not None:
                    await session.execute(
                        sa.delete(Conversation).where(Conversation.id == conversation_id)
                    )
                if customer_id is not None:
                    await session.execute(sa.delete(Customer).where(Customer.id == customer_id))
        except Exception as exc:
            log.warning(
                "evals.driver.cleanup_failed",
                tenant_id=str(self.tenant_id),
                conversation_id=str(conversation_id) if conversation_id else None,
                error=str(exc),
            )


def _adapt_final_state(final: dict[str, Any], *, latency_ms: int) -> PipelineTurnResult:
    """Map the graph's final state onto :class:`PipelineTurnResult`.

    The graph stores tool calls as envelopes (``{tool, args, status,
    result, …}``). The assertion engine matches on ``name`` and the
    judge reads ``status`` / ``result``, so we flatten each envelope to
    that shape."""
    envelopes = final.get("tool_calls") or []
    tool_calls = tuple(
        {
            "name": e.get("tool"),
            "arguments": e.get("args") or {},
            "status": e.get("status"),
            "result": e.get("result") or {},
        }
        for e in envelopes
    )
    return PipelineTurnResult(
        assistant_message=str(final.get("response") or ""),
        tool_calls=tool_calls,
        intent=final.get("intent"),
        model=final.get("response_model"),
        latency_ms=latency_ms,
    )


# ── channel get-or-create ────────────────────────────────────────────────────


async def _ensure_eval_channel(session: Any, tenant_id: uuid.UUID) -> Channel:
    """Get-or-create the tenant's dedicated ``eval_runner`` web channel.

    Evals get their own channel — parallel to the QA Playground's
    ``qa_playground`` web channel — so eval conversations never land on
    the tenant's real WhatsApp channel history. It never sends anything:
    eval conversations are deleted after each case.
    """
    import sqlalchemy as sa

    from nexus_api.db.models import Channel, ChannelStatus, ChannelType

    stmt = (
        sa.select(Channel)
        .where(Channel.tenant_id == tenant_id)
        .where(Channel.type == ChannelType.WEB)
        .where(Channel.provider == _EVAL_CHANNEL_PROVIDER)
        .limit(1)
    )
    channel: Channel | None = (await session.execute(stmt)).scalar_one_or_none()
    if channel is not None:
        return channel

    channel = Channel(
        tenant_id=tenant_id,
        type=ChannelType.WEB,
        provider=_EVAL_CHANNEL_PROVIDER,
        provider_identifier=f"{_EVAL_CHANNEL_PROVIDER}:{tenant_id}",
        config={"eval_runner": True},
        status=ChannelStatus.ACTIVE,
    )
    session.add(channel)
    await session.flush()
    return channel


# ── public builder ───────────────────────────────────────────────────────────


async def build_eval_driver(
    *,
    tenant_id: uuid.UUID,
    agent_config: AgentConfig,
    llm_router: LLMRouter | None = None,
    case_timeout_s: float = 120.0,
) -> EvalPipelineDriver:
    """Compile the real graph pinned to ``agent_config`` and return a
    driver ready to run cases.

    The loader is primed with an ``AgentBundle`` built from the exact
    config row, so ``classify`` / the handlers see this version's system
    prompt and whitelist — even when it is a STAGED candidate that is
    not the tenant's active config.
    """
    from nexus_worker.runtime.agent_loader import AgentBundle, AgentLoader
    from nexus_worker.runtime.pipeline import build_pipeline

    if not (agent_config.system_prompt_rendered or "").strip():
        raise EvalDriverError(
            "agent_config has an empty system_prompt_rendered — "
            "apply a seed template or stage a real prompt first"
        )

    bundle = AgentBundle(
        tenant_id=tenant_id,
        version=agent_config.version,
        version_id=agent_config.id,
        system_prompt=agent_config.system_prompt_rendered,
        tools=frozenset(agent_config.tools or ()),
        policies=dict(agent_config.policies or {}),
    )
    loader = AgentLoader()
    loader.prime(bundle)

    from langgraph.checkpoint.memory import MemorySaver

    pipeline = build_pipeline(
        agent_loader=loader,
        llm_router=llm_router or _resolve_router(),
        checkpointer=MemorySaver(),
        mcp_registry=_build_eval_registry(),
        # Deterministic eval runs: skip the UCM shadow-diff node. The
        # assertions read ``state["response"]`` (plain text); the
        # formatter would only add shadow-diff log noise.
        use_ucm_formatter=False,
    )

    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        channel = await _ensure_eval_channel(session, tenant_id)
        channel_id = channel.id

    log.info(
        "evals.driver.built",
        tenant_id=str(tenant_id),
        agent_config_version=agent_config.version,
        whitelist_size=len(bundle.tools),
    )
    return EvalPipelineDriver(
        tenant_id=tenant_id,
        pipeline=pipeline,
        channel_id=channel_id,
        case_timeout_s=case_timeout_s,
    )
