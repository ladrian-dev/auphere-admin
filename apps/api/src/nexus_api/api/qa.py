"""QA Playground HTTP surface (ADR-020, Phase 3).

Endpoints
---------

``POST   /qa/threads``               — create a thread (tenant_id in body)
``GET    /qa/threads``                — list operator's threads (filter by tenant)
``GET    /qa/threads/{id}``           — detail (thread + counts)
``PATCH  /qa/threads/{id}``           — rename / archive
``GET    /qa/threads/{id}/audit``     — side-effect audit log for this thread

Every request is gated by ``require_qa_operator`` (Bearer admin_token +
``X-Operator-Id`` header). The ``qa_session`` dependency opens a single
transaction per request and applies ``app.operator_id`` (and ``app.tenant_id``
when the body carries it) so RLS holds.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.metrics import QA_THREAD_CREATED, counters
from nexus_api.core.operator_context import (
    _current_operator,
    apply_operator_to_session,
)
from nexus_api.core.qa_security import require_qa_operator
from nexus_api.core.tenant_context import (
    _current_tenant,
    apply_tenant_to_session,
    tenant_context,
)
from nexus_api.db.models import (
    Channel,
    ChannelStatus,
    Conversation,
    Customer,
    Message,
    MessageDirection,
)
from nexus_api.db.models.qa import (
    QA_RUN_STATUS_ERROR,
    QA_RUN_STATUS_RUNNING,
    QAAuditLog,
    QARun,
    QASideEffectAudit,
    QAThread,
)
from nexus_api.db.models.tenant import Tenant

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/qa", tags=["qa"])


# ── dependency: tx + operator-scoped session ─────────────────────────────────


async def qa_session(
    operator_id: Annotated[str, Depends(require_qa_operator)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AsyncIterator[tuple[AsyncSession, str]]:
    """Open a transaction + apply ``app.operator_id`` for the request.

    Mirrors ``scoped_session_from_path`` but for the QA dimension:
      - opens the transaction (commits on clean exit, rolls back on error)
      - sets ``app.operator_id`` (RLS gate on qa.*)
      - drops the superuser role to ``nexus_app`` so RLS is actually
        enforced — the connecting user is a superuser that bypasses
        every policy by default. ``apply_tenant_to_session`` does this
        too; we duplicate the SET ROLE here so qa-only endpoints (which
        don't always set a tenant) still get role-switched.
    Returns ``(session, operator_id)`` so handlers can stamp inserts
    without re-parsing the header.
    """
    from sqlalchemy import text

    operator_token = _current_operator.set(operator_id)
    try:
        async with session.begin():
            await apply_operator_to_session(session, operator_id)
            await session.execute(text("SET LOCAL ROLE nexus_app"))
            yield session, operator_id
    finally:
        _current_operator.reset(operator_token)


# ── pydantic schemas ─────────────────────────────────────────────────────────


class ThreadCreate(BaseModel):
    tenant_id: uuid.UUID
    title: str = Field(default="Untitled", max_length=200)


class ThreadPatch(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    archived: bool | None = None


class ThreadOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    operator_id: str
    external_id: str | None
    title: str
    archived_at: datetime | None
    last_run_at: datetime | None
    message_count: int
    created_at: datetime
    updated_at: datetime


class SideEffectOut(BaseModel):
    id: uuid.UUID
    tool_name: str
    tool_args: dict[str, Any]
    synthetic_result: dict[str, Any]
    blocked_reason: str
    run_id: str | None
    created_at: datetime


# ── helpers ──────────────────────────────────────────────────────────────────


async def _audit(
    session: AsyncSession,
    *,
    operator_id: str,
    tenant_id: uuid.UUID | None,
    thread_id: uuid.UUID | None,
    action: str,
    target_kind: str | None = None,
    target_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """Append one row to ``qa.audit_log`` from inside an open transaction."""
    session.add(
        QAAuditLog(
            operator_id=operator_id,
            tenant_id=tenant_id,
            thread_id=thread_id,
            action=action,
            target_kind=target_kind,
            target_id=target_id,
            payload=payload or {},
        )
    )


def _thread_out(t: QAThread) -> ThreadOut:
    return ThreadOut(
        id=t.id,
        tenant_id=t.tenant_id,
        operator_id=t.operator_id,
        external_id=t.external_id,
        title=t.title,
        archived_at=t.archived_at,
        last_run_at=t.last_run_at,
        message_count=t.message_count,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


async def _load_thread(session: AsyncSession, thread_id: uuid.UUID) -> QAThread:
    thread = await session.get(QAThread, thread_id)
    if thread is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"thread {thread_id} not found",
        )
    return thread


# ── endpoints ────────────────────────────────────────────────────────────────


@router.post(
    "/threads",
    response_model=ThreadOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_thread(
    body: ThreadCreate,
    scope: Annotated[tuple[AsyncSession, str], Depends(qa_session)],
) -> ThreadOut:
    """Create a QA thread bound to ``body.tenant_id``.

    The tenant must exist (we read it without RLS since ``tenants`` is a
    global table). We then apply ``app.tenant_id`` for the rest of the
    transaction so the audit row stamps the tenant correctly.
    """
    session, operator_id = scope
    tenant = await session.get(Tenant, body.tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"tenant {body.tenant_id} not found",
        )

    # Set the tenant scope on top of the existing operator scope.
    tenant_token = _current_tenant.set(body.tenant_id)
    try:
        await apply_tenant_to_session(session, body.tenant_id)
        thread = QAThread(
            operator_id=operator_id,
            tenant_id=body.tenant_id,
            title=body.title,
        )
        session.add(thread)
        await session.flush()
        await _audit(
            session,
            operator_id=operator_id,
            tenant_id=body.tenant_id,
            thread_id=thread.id,
            action="thread.create",
            target_kind="qa.thread",
            target_id=str(thread.id),
            payload={"title": body.title},
        )
        await session.refresh(thread)
        # Metrics: bump the global + per-tenant + per-operator counter so
        # alerts/dashboards can spot a sudden surge (e.g. one operator
        # spam-creating threads in a script).
        counters.incr(QA_THREAD_CREATED)
        counters.incr(f"{QA_THREAD_CREATED}:tenant={body.tenant_id}")
        counters.incr(f"{QA_THREAD_CREATED}:operator={operator_id}")
        return _thread_out(thread)
    finally:
        _current_tenant.reset(tenant_token)


@router.get("/threads", response_model=list[ThreadOut])
async def list_threads(
    scope: Annotated[tuple[AsyncSession, str], Depends(qa_session)],
    tenant_id: uuid.UUID | None = Query(default=None),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ThreadOut]:
    """List the operator's threads.

    RLS guarantees we only see the operator's own rows even if the
    WHERE clause is omitted — that's the whole point of the isolation
    layer.
    """
    session, _ = scope
    stmt = select(QAThread).order_by(QAThread.updated_at.desc()).limit(limit)
    if tenant_id is not None:
        stmt = stmt.where(QAThread.tenant_id == tenant_id)
    if not include_archived:
        stmt = stmt.where(QAThread.archived_at.is_(None))
    rows = (await session.execute(stmt)).scalars().all()
    return [_thread_out(t) for t in rows]


@router.get("/threads/{thread_id}", response_model=ThreadOut)
async def get_thread(
    thread_id: Annotated[uuid.UUID, Path(...)],
    scope: Annotated[tuple[AsyncSession, str], Depends(qa_session)],
) -> ThreadOut:
    session, _ = scope
    thread = await _load_thread(session, thread_id)
    return _thread_out(thread)


@router.patch("/threads/{thread_id}", response_model=ThreadOut)
async def patch_thread(
    body: ThreadPatch,
    thread_id: Annotated[uuid.UUID, Path(...)],
    scope: Annotated[tuple[AsyncSession, str], Depends(qa_session)],
) -> ThreadOut:
    """Rename or archive a thread.

    Archive is soft (``archived_at = now()``) so audit + side-effect
    rows remain queryable. Un-archive: ``archived: false``.
    """
    if body.title is None and body.archived is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of title or archived must be set",
        )
    session, operator_id = scope
    thread = await _load_thread(session, thread_id)
    changes: dict[str, Any] = {}
    if body.title is not None:
        thread.title = body.title
        changes["title"] = body.title
    if body.archived is not None:
        if body.archived and thread.archived_at is None:
            thread.archived_at = func.now()
            changes["archived"] = True
        elif not body.archived and thread.archived_at is not None:
            thread.archived_at = None
            changes["archived"] = False
    if changes:
        await _audit(
            session,
            operator_id=operator_id,
            tenant_id=thread.tenant_id,
            thread_id=thread.id,
            action="thread.patch",
            target_kind="qa.thread",
            target_id=str(thread.id),
            payload=changes,
        )
    await session.flush()
    await session.refresh(thread)
    return _thread_out(thread)


@router.get(
    "/threads/{thread_id}/audit",
    response_model=list[SideEffectOut],
)
async def get_thread_audit(
    thread_id: Annotated[uuid.UUID, Path(...)],
    scope: Annotated[tuple[AsyncSession, str], Depends(qa_session)],
    limit: int = Query(default=100, ge=1, le=500),
) -> list[SideEffectOut]:
    """Side-effect audit rows for a single thread.

    RLS-scoped by operator_id; the thread_id filter further constrains
    to this conversation. If the operator doesn't own the thread the
    ``_load_thread`` check returns 404 before the audit query runs.
    """
    session, _ = scope
    await _load_thread(session, thread_id)
    stmt = (
        select(QASideEffectAudit)
        .where(QASideEffectAudit.thread_id == thread_id)
        .order_by(QASideEffectAudit.created_at.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        SideEffectOut(
            id=r.id,
            tool_name=r.tool_name,
            tool_args=r.tool_args,
            synthetic_result=r.synthetic_result,
            blocked_reason=r.blocked_reason,
            run_id=r.run_id,
            created_at=r.created_at,
        )
        for r in rows
    ]


# ── send endpoint (Fase 5 closure) ───────────────────────────────────────────
#
# Architecture decision (ADR-020 follow-up, 2026-05-20): the QA Playground
# invokes the agent graph IN-PROCESS instead of going through a separate
# qa-langgraph-server over HTTP. The graph is the same code either way
# (``build_qa_pipeline`` from ``nexus_worker.runtime.qa_pipeline``); pinning
# it inside the qa-api removes a network hop, a deploy target, an enterprise-
# license gate for custom auth, and an in-memory checkpoint state that drifts
# across server restarts. The standalone ``apps/qa-langgraph-server/`` package
# stays in the repo as a dev-only utility for LangGraph Studio inspection, but
# is no longer on the production path.
#
# When (and if) a future channel-web for end clients lands and requires real
# token streaming, that surface gets designed against its own constraints
# (channel adapter pattern, public auth, SSE/WebSocket) — not by retrofitting
# this internal Playground.


class SendIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class SendOut(BaseModel):
    response: str
    ucm: dict[str, Any] | None
    intent: str | None
    tool_calls: list[dict[str, Any]]
    conversation_id: uuid.UUID
    inbound_message_id: uuid.UUID
    run_id: str | None


async def _ensure_qa_conversation(
    session: AsyncSession,
    *,
    thread: QAThread,
    operator_id: str,
) -> tuple[Conversation, Customer, Channel]:
    """Lazily wire a thread to a (customer, conversation, channel) trio.

    First send: pick the tenant's first ACTIVE channel, mint a dedicated
    QA customer keyed to ``operator_id + thread.id`` so the same operator
    re-using the same thread always lands on the same customer (history
    tools can rely on that), then create one conversation.

    Subsequent sends: load the existing conversation + customer + channel.

    The function expects the caller's tx to already have ``app.tenant_id``
    set so RLS on the tenant-scoped tables (customers, conversations,
    channels) accepts the writes.
    """
    if thread.conversation_id is not None:
        conv = await session.get(Conversation, thread.conversation_id)
        if conv is not None:
            cust = await session.get(Customer, conv.customer_id)
            ch = await session.get(Channel, conv.channel_id)
            if cust is None or ch is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="qa thread points to a conversation whose "
                    "customer or channel disappeared",
                )
            return conv, cust, ch
        # FK was SET NULL by a CASCADE; fall through to recreate.

    # Pick the first ACTIVE channel of this tenant. WhatsApp preferred —
    # if a tenant has only Instagram in the future, we still get one.
    ch_stmt = (
        select(Channel)
        .where(Channel.tenant_id == thread.tenant_id)
        .where(Channel.status == ChannelStatus.ACTIVE)
        .order_by(Channel.created_at.asc())
        .limit(1)
    )
    channel = (await session.execute(ch_stmt)).scalar_one_or_none()
    if channel is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"tenant {thread.tenant_id} has no active channel; configure "
                "one before sending QA messages"
            ),
        )

    # Deterministic QA customer identifier — same operator+thread pair
    # always reuses the same customer row so the agent's history tools
    # see a coherent conversation.
    qa_identifier = f"qa::{operator_id[:12]}::{thread.id.hex[:12]}"
    cust_stmt = (
        select(Customer)
        .where(Customer.tenant_id == thread.tenant_id)
        .where(Customer.identifier == qa_identifier)
        .limit(1)
    )
    customer = (await session.execute(cust_stmt)).scalar_one_or_none()
    if customer is None:
        customer = Customer(
            tenant_id=thread.tenant_id,
            identifier=qa_identifier,
            name=f"QA · {operator_id[:8]}",
            preferences={"qa": True, "operator_id": operator_id},
        )
        session.add(customer)
        await session.flush()

    conv = Conversation(
        tenant_id=thread.tenant_id,
        channel_id=channel.id,
        customer_id=customer.id,
    )
    session.add(conv)
    await session.flush()
    thread.conversation_id = conv.id
    return conv, customer, channel


# ── in-process graph (lazy, process-cached) ──────────────────────────────────


_qa_pipeline_cache: Any | None = None


def _get_qa_pipeline() -> Any:
    """Build the QA pipeline once per process and reuse it.

    The compiled graph is stateless — every ``ainvoke`` / ``astream_events``
    brings its own state. The only mutable surface is the checkpointer,
    which keys by ``thread_id`` so concurrent runs on different QA
    threads don't collide.

    Since ADR-021 Fase 1 the checkpointer is the process-wide
    ``AsyncPostgresSaver`` initialised by ``main.lifespan`` (see
    ``core.qa_checkpointer``). That makes resumability + HITL durable
    across server restarts. Tests bypass this path by patching the
    cache directly with a ``MemorySaver``-backed pipeline.

    Imports live inside this function so the qa-api module load doesn't
    pay the heavy LiteLLM / langgraph cost at startup.
    """
    global _qa_pipeline_cache
    if _qa_pipeline_cache is not None:
        return _qa_pipeline_cache

    from nexus_worker.runtime.agent_loader import AgentLoader
    from nexus_worker.runtime.llm import LiteLLMProvider, LLMRouter
    from nexus_worker.runtime.qa_pipeline import build_qa_pipeline

    from nexus_api.core.qa_checkpointer import get_qa_checkpointer

    provider = LiteLLMProvider()
    llm_router = LLMRouter(
        provider=provider,
        classify_model="anthropic/claude-haiku-4-5-20251001",
        respond_model="anthropic/claude-sonnet-4-6",
        fallback_model="openai/gpt-4o",
    )
    _qa_pipeline_cache = build_qa_pipeline(
        agent_loader=AgentLoader(),
        llm_router=llm_router,
        checkpointer=get_qa_checkpointer(),
    )
    log.info("qa.pipeline.compiled", checkpointer="async_postgres")
    return _qa_pipeline_cache


async def _run_in_process(
    *,
    operator_id: str,
    qa_thread_id: uuid.UUID,
    inbound_id: uuid.UUID,
    conversation_id: uuid.UUID,
    customer_id: uuid.UUID,
    channel_id: uuid.UUID,
    tenant_id: uuid.UUID,
    user_id: str,
    user_message: str,
) -> dict[str, Any]:
    """Invoke the QA pipeline in-process and return the final graph state.

    The agent runtime depends on three contextvars (operator_id,
    tenant_id, qa_thread_id) for the dry_run audit writer to stamp the
    right scope on each blocked side-effect. We set them around the
    ``ainvoke`` call so they propagate into the worker's graph nodes.

    LangGraph's ``thread_id`` (the configurable) is the same as
    ``qa_thread_id`` so the in-memory checkpointer keys conversations
    consistently across turns within a single process lifetime.
    """
    from nexus_api.core.operator_context import qa_thread_context

    pipeline = _get_qa_pipeline()
    state = {
        "tenant_id": str(tenant_id),
        "channel_id": str(channel_id),
        "user_id": user_id,
        "conversation_id": str(conversation_id),
        "customer_id": str(customer_id),
        "inbound_message_id": str(inbound_id),
        "user_message": user_message,
    }
    config = {"configurable": {"thread_id": str(qa_thread_id)}}

    op_token = _current_operator.set(operator_id)
    try:
        with tenant_context(tenant_id), qa_thread_context(qa_thread_id):
            final_state = await pipeline.ainvoke(state, config=config)
    finally:
        _current_operator.reset(op_token)

    return dict(final_state) if final_state else {}


@router.post(
    "/threads/{thread_id}/send",
    response_model=SendOut,
)
async def send_message(
    thread_id: Annotated[uuid.UUID, Path(...)],
    body: SendIn,
    operator_id: Annotated[str, Depends(require_qa_operator)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SendOut:
    """Operator → agent turn from the Playground composer.

    End-to-end:
      1. Auto-seed a (customer, conversation, channel) trio for this
         thread on the first call; reuse on subsequent calls.
      2. Persist the inbound ``Message``.
      3. Ensure the LangGraph Server has a thread for this QA thread;
         stamp ``qa.threads.external_id`` on first send.
      4. Fire the run against the LangGraph Server with ``dry_run=True``
         (the qa_pipeline forces that), drain the SSE stream, capture
         the final ``values`` event.
      5. Return the agent's response + UCM + intent + tool_calls. The
         outbound ``messages`` row is persisted by the graph's
         ``checkpoint`` node — the operator sees the UCM here, the DB
         row lands in parallel.

    Why this endpoint does NOT use the ``qa_session`` dependency:
    the inbound row needs to be COMMITTED before the graph's
    ``checkpoint`` node persists the outbound (the FK references it).
    We use one short tx for the seed + inbound, then invoke the graph
    OUTSIDE any tx so the graph can open its own session for the
    outbound.

    The endpoint is synchronous from the operator's POV: one POST in,
    one JSON back. Visible streaming is out of scope for the internal
    Playground (it's an internal QA surface, not a customer-facing
    channel). If a future channel-web for end clients lands, it will
    be designed as a separate channel adapter with its own streaming
    surface.
    """
    # ── Phase 1: scoped tx that ensures conversation + persists inbound ──
    operator_token = _current_operator.set(operator_id)
    tenant_token = None
    try:
        async with session.begin():
            from sqlalchemy import text as _sql_text

            await apply_operator_to_session(session, operator_id)
            await session.execute(_sql_text("SET LOCAL ROLE nexus_app"))
            thread = await _load_thread(session, thread_id)
            if thread.archived_at is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"thread {thread_id} is archived",
                )

            tenant_token = _current_tenant.set(thread.tenant_id)
            await apply_tenant_to_session(session, thread.tenant_id)

            conversation, customer, channel = await _ensure_qa_conversation(
                session, thread=thread, operator_id=operator_id
            )
            inbound = Message(
                tenant_id=thread.tenant_id,
                conversation_id=conversation.id,
                direction=MessageDirection.INBOUND,
                content=body.message,
                tool_calls=[],
            )
            session.add(inbound)
            await session.flush()
            await session.refresh(inbound)

            # Snapshot the values we need after the tx closes — SQLAlchemy
            # detaches the rows once the tx commits, so we read the
            # primitives now.
            conv_id = conversation.id
            inbound_id = inbound.id
            tenant_id_local = thread.tenant_id
            cust_id = customer.id
            chan_id = channel.id
            cust_identifier = customer.identifier
    finally:
        if tenant_token is not None:
            _current_tenant.reset(tenant_token)
        _current_operator.reset(operator_token)

    # ── Phase 2: in-process graph invocation ──────────────────────────────
    # No DB transaction held here. The graph's ``checkpoint`` node opens
    # its own session per node to persist the outbound message. The
    # dry_run audit writer (registered when the pipeline was built) also
    # opens its own session per blocked tool call.
    try:
        final_state = await _run_in_process(
            operator_id=operator_id,
            qa_thread_id=thread_id,
            inbound_id=inbound_id,
            conversation_id=conv_id,
            customer_id=cust_id,
            channel_id=chan_id,
            tenant_id=tenant_id_local,
            user_id=cust_identifier,
            user_message=body.message,
        )
    except Exception as exc:
        log.exception(
            "qa.send.graph_invoke_failed",
            qa_thread_id=str(thread_id),
            operator_id=operator_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"qa graph invocation failed: {exc!s}",
        ) from exc

    return SendOut(
        response=final_state.get("response", "") or "",
        ucm=final_state.get("ucm"),
        intent=final_state.get("intent"),
        tool_calls=final_state.get("tool_calls", []) or [],
        conversation_id=conv_id,
        inbound_message_id=inbound_id,
        run_id=None,  # in-process runs don't carry the LG server run id
    )


# ── streaming endpoints (ADR-021, Fase 1) ────────────────────────────────────
#
# These endpoints expose the SSE runtime defined in
# ``nexus_api.api.qa_streaming``. The contract:
#
#   1. ``POST /qa/threads/{id}/runs`` — persist inbound + qa.runs row,
#      spawn the streaming driver, return ``{run_id, ...}`` fast.
#   2. ``GET  /qa/threads/{id}/stream?run_id=&since_seq=`` — SSE.
#   3. ``DELETE /qa/runs/{run_id}`` — cancel an in-flight run.
#   4. ``GET  /qa/threads/{id}/messages?limit=`` — hydrate history.
#
# The existing synchronous ``POST /qa/threads/{id}/send`` is kept intact
# for backwards compatibility (the legacy thread-pane.tsx uses it). The
# Fase 2 frontend rewrite on top of assistant-ui will switch to the
# ``/runs`` + ``/stream`` flow above.


class RunStartIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class RunStartOut(BaseModel):
    run_id: uuid.UUID
    thread_id: uuid.UUID
    conversation_id: uuid.UUID
    inbound_message_id: uuid.UUID
    status: str


class HistoryMessageOut(BaseModel):
    id: uuid.UUID
    direction: str
    content: str | None
    ucm: dict[str, Any] | None
    tool_calls: list[dict[str, Any]]
    created_at: datetime


async def _finalise_run_row(
    operator_id: str,
    tenant_id: uuid.UUID,
    run_id: uuid.UUID,
    final_status: str,
    final_error: str | None,
    input_tokens: int,
    output_tokens: int,
) -> None:
    """Update the ``qa.runs`` row when the streaming run finishes.

    Runs OUTSIDE any request transaction (the request already returned
    to the client). Opens its own session, applies the operator + tenant
    scopes so RLS lets the UPDATE through.
    """
    from sqlalchemy import text as _sql_text

    from nexus_api.db.base import get_sessionmaker

    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_operator_to_session(session, operator_id)
        await apply_tenant_to_session(session, tenant_id)
        await session.execute(_sql_text("SET LOCAL ROLE nexus_app"))
        run = await session.get(QARun, run_id)
        if run is None:
            log.warning(
                "qa.run.finalise_missing",
                run_id=str(run_id),
                operator_id=operator_id,
            )
            return
        run.status = final_status
        run.ended_at = datetime.now(tz=run.started_at.tzinfo)
        run.error = final_error
        run.input_tokens = input_tokens or None
        run.output_tokens = output_tokens or None


@router.post(
    "/threads/{thread_id}/runs",
    response_model=RunStartOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_thread_run(
    thread_id: Annotated[uuid.UUID, Path(...)],
    body: RunStartIn,
    operator_id: Annotated[str, Depends(require_qa_operator)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> RunStartOut:
    """Start a streaming agent turn on a QA thread.

    Sequence:
      1. Inside a tx: auto-seed conversation (first turn), persist
         inbound ``messages`` row, insert ``qa.runs`` row with
         ``status='running'``.
      2. Commit.
      3. Spawn the background task via ``qa_streaming.start_run`` —
         the task drives ``pipeline.astream_events`` and feeds the
         per-run buffer + live queues.
      4. Return ``{run_id}`` so the client can open the SSE stream
         immediately.
    """
    from nexus_api.api import qa_streaming
    from nexus_api.core.operator_context import qa_thread_context
    from nexus_api.core.tenant_context import tenant_context

    operator_token = _current_operator.set(operator_id)
    tenant_token = None
    try:
        async with session.begin():
            from sqlalchemy import text as _sql_text

            await apply_operator_to_session(session, operator_id)
            await session.execute(_sql_text("SET LOCAL ROLE nexus_app"))
            thread = await _load_thread(session, thread_id)
            if thread.archived_at is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"thread {thread_id} is archived",
                )

            tenant_token = _current_tenant.set(thread.tenant_id)
            await apply_tenant_to_session(session, thread.tenant_id)

            conversation, customer, channel = await _ensure_qa_conversation(
                session, thread=thread, operator_id=operator_id
            )
            inbound = Message(
                tenant_id=thread.tenant_id,
                conversation_id=conversation.id,
                direction=MessageDirection.INBOUND,
                content=body.message,
                tool_calls=[],
            )
            session.add(inbound)
            await session.flush()
            await session.refresh(inbound)

            qa_run = QARun(
                thread_id=thread.id,
                operator_id=operator_id,
                status=QA_RUN_STATUS_RUNNING,
            )
            session.add(qa_run)
            await session.flush()
            await session.refresh(qa_run)

            run_id = qa_run.id
            conv_id = conversation.id
            inbound_id = inbound.id
            tenant_id_local = thread.tenant_id
            cust_id = customer.id
            chan_id = channel.id
            cust_identifier = customer.identifier
    finally:
        if tenant_token is not None:
            _current_tenant.reset(tenant_token)
        _current_operator.reset(operator_token)

    # Build the driver — it captures the cached pipeline + the
    # graph state. Contextvars must be set INSIDE the driver task
    # (asyncio creates a fresh context for each Task), so the driver
    # wraps the astream_events loop in the three context managers.
    pipeline = _get_qa_pipeline()
    graph_state = {
        "tenant_id": str(tenant_id_local),
        "channel_id": str(chan_id),
        "user_id": cust_identifier,
        "conversation_id": str(conv_id),
        "customer_id": str(cust_id),
        "inbound_message_id": str(inbound_id),
        "user_message": body.message,
    }
    graph_config = {"configurable": {"thread_id": str(thread_id)}}

    async def _driver(handle: qa_streaming.RunHandle) -> None:
        from nexus_api.core.operator_context import operator_context

        with (
            operator_context(operator_id),
            tenant_context(tenant_id_local),
            qa_thread_context(thread_id),
        ):
            translator_state = qa_streaming._TranslatorState()
            async for event in pipeline.astream_events(
                graph_state, config=graph_config, version="v2"
            ):
                pending = qa_streaming.translate_event(event, translator_state)
                for name, data in pending:
                    if name == "cost.updated":
                        handle.total_input_tokens += int(data.get("input_tokens") or 0)
                        handle.total_output_tokens += int(data.get("output_tokens") or 0)
                    qa_streaming._push_event(
                        handle,
                        qa_streaming.SSEEvent(
                            seq=qa_streaming._next_seq(handle),
                            event=name,
                            data=data,
                        ),
                    )

    async def _on_complete(handle: qa_streaming.RunHandle) -> None:
        await _finalise_run_row(
            operator_id=operator_id,
            tenant_id=tenant_id_local,
            run_id=handle.run_id,
            final_status=handle.final_status or QA_RUN_STATUS_ERROR,
            final_error=handle.final_error,
            input_tokens=handle.total_input_tokens,
            output_tokens=handle.total_output_tokens,
        )

    await qa_streaming.start_run(
        run_id=run_id,
        thread_id=thread_id,
        operator_id=operator_id,
        driver=_driver,
        on_complete=_on_complete,
    )

    return RunStartOut(
        run_id=run_id,
        thread_id=thread_id,
        conversation_id=conv_id,
        inbound_message_id=inbound_id,
        status=QA_RUN_STATUS_RUNNING,
    )


@router.get("/threads/{thread_id}/stream")
async def stream_thread_run(
    thread_id: Annotated[uuid.UUID, Path(...)],
    operator_id: Annotated[str, Depends(require_qa_operator)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    run_id: uuid.UUID = Query(...),
    since_seq: int = Query(default=0, ge=0),
) -> StreamingResponse:
    """SSE endpoint that streams the events of an in-flight ``qa.runs`` row.

    Ownership is verified via RLS: the SELECT against ``qa.runs`` only
    returns the row if ``operator_id`` matches the session's GUC. A
    foreign operator gets 404, identical to the pattern other QA
    endpoints follow.

    After the ownership check, the SSE stream is fed from the in-memory
    buffer + live queue maintained by ``qa_streaming``. The HTTP
    transaction does NOT stay open across the stream — the verification
    tx commits before the StreamingResponse starts emitting.
    """
    from fastapi.responses import StreamingResponse

    from nexus_api.api import qa_streaming

    # Verify ownership (RLS).
    operator_token = _current_operator.set(operator_id)
    try:
        async with session.begin():
            from sqlalchemy import text as _sql_text

            await apply_operator_to_session(session, operator_id)
            await session.execute(_sql_text("SET LOCAL ROLE nexus_app"))
            run = await session.get(QARun, run_id)
            if run is None or run.thread_id != thread_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"run {run_id} not found",
                )
    finally:
        _current_operator.reset(operator_token)

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",  # disable proxy buffering (Nginx)
        "Connection": "keep-alive",
    }
    return StreamingResponse(
        qa_streaming.subscribe(run_id, since_seq=since_seq),
        media_type="text/event-stream",
        headers=headers,
    )


@router.delete("/runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_run(
    run_id: Annotated[uuid.UUID, Path(...)],
    operator_id: Annotated[str, Depends(require_qa_operator)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> None:
    """Request cancellation of an in-flight QA run.

    Ownership verified via RLS. The actual cancel signal goes through
    the in-memory ``qa_streaming.cancel`` (which calls ``Task.cancel``).
    The ``on_complete`` hook closes the ``qa.runs`` row with
    ``status='cancelled'``.
    """
    from nexus_api.api import qa_streaming

    operator_token = _current_operator.set(operator_id)
    try:
        async with session.begin():
            from sqlalchemy import text as _sql_text

            await apply_operator_to_session(session, operator_id)
            await session.execute(_sql_text("SET LOCAL ROLE nexus_app"))
            run = await session.get(QARun, run_id)
            if run is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"run {run_id} not found",
                )
    finally:
        _current_operator.reset(operator_token)

    await qa_streaming.cancel(run_id)


@router.get(
    "/threads/{thread_id}/messages",
    response_model=list[HistoryMessageOut],
)
async def get_thread_messages(
    thread_id: Annotated[uuid.UUID, Path(...)],
    scope: Annotated[tuple[AsyncSession, str], Depends(qa_session)],
    limit: int = Query(default=50, ge=1, le=200),
) -> list[HistoryMessageOut]:
    """Hydrate the operator-visible history of a QA thread.

    Reads the ``messages`` table joined via ``qa.threads.conversation_id``.
    Inbound rows surface their ``content`` (plain text from the
    composer). Outbound rows surface ``ucm`` when the agent produced
    one (the ``ucm_formatter`` node now persists the UCM into the
    ``meta`` JSON column via the existing checkpoint node).
    """
    session, _ = scope
    thread = await _load_thread(session, thread_id)
    if thread.conversation_id is None:
        return []
    # Tenant scope required to read messages (RLS by tenant_id).
    tenant_token = _current_tenant.set(thread.tenant_id)
    try:
        await apply_tenant_to_session(session, thread.tenant_id)
        stmt = (
            select(Message)
            .where(Message.conversation_id == thread.conversation_id)
            .order_by(Message.created_at.asc())
            .limit(limit)
        )
        rows = (await session.execute(stmt)).scalars().all()
        out: list[HistoryMessageOut] = []
        for m in rows:
            # UCM is not yet persisted by the checkpoint node — outbound
            # rows carry the plain text in ``content``. When UCM
            # persistence lands (separate change), this field surfaces
            # the canonical message. For now: None on outbound, the
            # client just renders ``content`` as plain text on reload.
            out.append(
                HistoryMessageOut(
                    id=m.id,
                    direction=(
                        m.direction.value if hasattr(m.direction, "value") else str(m.direction)
                    ),
                    content=m.content,
                    ucm=None,
                    tool_calls=list(m.tool_calls or []),
                    created_at=m.created_at,
                )
            )
        return out
    finally:
        _current_tenant.reset(tenant_token)
