"""``/console/clients/{ref}/playground/*`` + ``/console/playground/budget`` —
the partner's playground against a client's agent, with a monthly token
cap (PLAN-CONSOLE-V1 CP-16, lane B).

Built on the internal QA Playground (``api/qa.py`` + ``api/qa_streaming.py``,
ADR-020/021): same threads (``qa.threads``), same runs (``qa.runs``), same
in-process SSE runtime, same metering (``usage_records.source='qa'``, 0079,
never billed to the client). What changes is WHO and HOW:

- **Identity.** No admin token, no ``X-Operator-Id`` header. The operator
  is derived from the console principal: ``operator_id =
  "console:<user_id>"``. RLS on ``qa.*`` (by operator) then does what it
  always did — a member only sees its own threads — and the tenant is the
  one behind ``{ref}`` under the principal's partner (``client_scope`` /
  ``resolve_mapping``), never one named by the caller. A thread of another
  member, or of another client, is an opaque 404.
- **Always dry-run.** The console has no live toggle: every thread is
  created with ``dry_run=True`` and the flag is not exposed. Side effects
  are blocked and audited; the LLM calls are real and metered.
- **Cap.** ``partners.qa_monthly_token_cap`` (0082) is checked BEFORE a
  turn starts. Source of the month-to-date sum: ``qa.runs.input_tokens +
  output_tokens`` of the partner's members' threads on the partner's
  tenants since the first day of the UTC month. Chosen over
  ``usage_records`` because the API closes the ``qa.runs`` row itself when
  the stream ends (``_finalise_run_row``) — synchronous, no dependency on
  the metering consumer — and it is one query instead of one per tenant.
  ``usage_records`` stays what the usage page shows; both count the same
  ``usage_metadata``. At the cap: ``429`` + ``Retry-After`` (seconds until
  next month) + a ``qa.cap_reached`` console notification (best-effort,
  deduped per partner and month). Every run ends with a ``budget.updated``
  SSE event so the UI's bar moves without polling.
- **No transcript over REST (C8).** The partner's own test text travels
  ONLY over the SSE stream. There is no ``…/messages`` endpoint under
  ``/console``; the console keeps the transcript of the session in browser
  memory. The structural body check in ``tests/isolation/test_console_scope``
  therefore needs no allow-list entry for this lane.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api import qa as qa_api
from nexus_api.api import qa_streaming
from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.core.operator_context import (
    _current_operator,
    apply_operator_to_session,
    operator_context,
    qa_thread_context,
)
from nexus_api.core.rate_limit import allow
from nexus_api.core.respond_catalog import HUMAN_TURN_ERROR, hop_models_in_catalog
from nexus_api.core.tenant_context import (
    _current_tenant,
    apply_tenant_to_session,
    tenant_context,
)
from nexus_api.db.models import (
    ChannelType,
    Message,
    MessageDirection,
    Partner,
    PartnerMembership,
    PartnerTenant,
)
from nexus_api.db.models.console_notification import (
    ConsoleNotification,
    NotificationKind,
    NotificationSeverity,
)
from nexus_api.db.models.qa import (
    QA_RUN_STATUS_ERROR,
    QA_RUN_STATUS_RUNNING,
    QARun,
    QAThread,
)

from .deps import ClientRef, ClientScope, client_scope, resolve_mapping
from .schemas_playground import (
    PlaygroundBudgetOut,
    PlaygroundRunStartIn,
    PlaygroundRunStartOut,
    PlaygroundThreadCreateIn,
    PlaygroundThreadOut,
    PlaygroundThreadPatchIn,
)

log = structlog.get_logger(__name__)

router = APIRouter()

#: Prefix of every console-born ``qa.*`` operator id.
CONSOLE_OPERATOR_PREFIX = "console:"


def console_operator_id(principal: ConsolePrincipal) -> str:
    """The ``qa.*`` operator behind a console member — RLS key of its threads."""
    return f"{CONSOLE_OPERATOR_PREFIX}{principal.user_id}"


# ── budget ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MonthWindow:
    period: str
    start: datetime
    next_start: datetime


def month_window(now: datetime | None = None) -> MonthWindow:
    """The UTC calendar month containing ``now``."""
    now = now or datetime.now(UTC)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        next_start = start.replace(year=start.year + 1, month=1)
    else:
        next_start = start.replace(month=start.month + 1)
    return MonthWindow(period=start.strftime("%Y-%m"), start=start, next_start=next_start)


def retry_after_seconds(window: MonthWindow, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    return max(1, int((window.next_start - now).total_seconds()))


async def partner_qa_tokens_used(
    session: AsyncSession, partner_id: uuid.UUID, window: MonthWindow
) -> int:
    """Month-to-date playground tokens of a partner (all members, all clients).

    Runs its own transaction. ``qa.runs``/``qa.threads`` are RLS-scoped by
    operator, so the sum is taken member by member: the platform rows
    (memberships, mappings) are read first, then the role is dropped to
    ``nexus_app`` and ``app.operator_id`` is re-pointed per member inside
    the same transaction. Members removed from the partner stop counting
    — acceptable for a soft monthly cap.
    """
    async with session.begin():
        member_ids = list(
            (
                await session.execute(
                    select(PartnerMembership.user_id).where(
                        PartnerMembership.partner_id == partner_id
                    )
                )
            ).scalars()
        )
        tenant_ids = list(
            (
                await session.execute(
                    select(PartnerTenant.tenant_id).where(PartnerTenant.partner_id == partner_id)
                )
            ).scalars()
        )
        if not member_ids or not tenant_ids:
            return 0
        await session.execute(text("SET LOCAL ROLE nexus_app"))
        total = 0
        stmt = (
            select(
                func.coalesce(
                    func.sum(
                        func.coalesce(QARun.input_tokens, 0) + func.coalesce(QARun.output_tokens, 0)
                    ),
                    0,
                )
            )
            .select_from(QARun)
            .join(QAThread, QAThread.id == QARun.thread_id)
            .where(
                QAThread.tenant_id.in_(tenant_ids),
                QARun.started_at >= window.start,
                QARun.started_at < window.next_start,
            )
        )
        for user_id in member_ids:
            await apply_operator_to_session(session, f"{CONSOLE_OPERATOR_PREFIX}{user_id}")
            total += int(await session.scalar(stmt) or 0)
        return total


def budget_out(used: int, cap: int, window: MonthWindow) -> PlaygroundBudgetOut:
    remaining = max(0, cap - used)
    percent = 100.0 if cap <= 0 else min(100.0, round(used * 100.0 / cap, 2))
    return PlaygroundBudgetOut(
        used=used,
        cap=cap,
        remaining=remaining,
        percent=percent,
        exhausted=used >= cap,
        period=window.period,
        resets_at=window.next_start,
    )


async def notify_cap_reached(partner_id: uuid.UUID, window: MonthWindow) -> None:
    """Best-effort ``qa.cap_reached`` notification, once per partner and month."""
    from nexus_api.db.base import get_sessionmaker

    try:
        sm = get_sessionmaker()
        async with sm() as session, session.begin():
            session.add(
                ConsoleNotification(
                    partner_id=partner_id,
                    kind=NotificationKind.QA_CAP_REACHED.value,
                    severity=NotificationSeverity.WARNING.value,
                    payload={"period": window.period},
                    dedupe_key=f"partner:{partner_id}:qa_cap:{window.period}",
                )
            )
    except IntegrityError:
        pass  # already notified this month
    except Exception:  # pragma: no cover - never let a notice break a run
        log.exception("console.playground.cap_notify_failed", partner_id=str(partner_id))


@router.get("/playground/budget", response_model=PlaygroundBudgetOut)
async def get_budget(
    principal: ConsolePrincipal = Depends(require_console_principal("playground:run")),
    session: AsyncSession = Depends(get_db_session),
) -> PlaygroundBudgetOut:
    """Month-to-date playground spend of the partner, in tokens (C9)."""
    window = month_window()
    used = await partner_qa_tokens_used(session, principal.partner.id, window)
    return budget_out(used, principal.partner.qa_monthly_token_cap, window)


# ── threads (inside a client scope) ────────────────────────────────────


def _thread_out(t: QAThread) -> PlaygroundThreadOut:
    return PlaygroundThreadOut(
        id=t.id,
        title=t.title,
        archived_at=t.archived_at,
        last_run_at=t.last_run_at,
        turn_count=t.message_count,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


def _thread_not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown thread")


async def _own_thread(
    session: AsyncSession, thread_id: uuid.UUID, tenant_id: uuid.UUID
) -> QAThread:
    """The caller's thread on THIS client, or an opaque 404. Requires the
    operator GUC + role switch on the transaction (RLS by operator)."""
    thread = await session.get(QAThread, thread_id)
    if thread is None or thread.tenant_id != tenant_id:
        raise _thread_not_found()
    return thread


@router.get("/clients/{ref}/playground/threads", response_model=list[PlaygroundThreadOut])
async def list_threads(
    scope: ClientScope = Depends(client_scope("playground:run")),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[PlaygroundThreadOut]:
    """The calling member's threads on this client (RLS by operator +
    tenant filter)."""
    await apply_operator_to_session(scope.session, console_operator_id(scope.principal))
    stmt = (
        select(QAThread)
        .where(QAThread.tenant_id == scope.tenant.id)
        .order_by(QAThread.updated_at.desc())
        .limit(limit)
    )
    if not include_archived:
        stmt = stmt.where(QAThread.archived_at.is_(None))
    rows = (await scope.session.execute(stmt)).scalars().all()
    return [_thread_out(t) for t in rows]


@router.post(
    "/clients/{ref}/playground/threads",
    response_model=PlaygroundThreadOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_thread(
    body: PlaygroundThreadCreateIn,
    scope: ClientScope = Depends(client_scope("playground:run")),
) -> PlaygroundThreadOut:
    """A new dry-run thread of the caller against this client's agent."""
    operator_id = console_operator_id(scope.principal)
    await apply_operator_to_session(scope.session, operator_id)
    thread = QAThread(
        operator_id=operator_id,
        tenant_id=scope.tenant.id,
        title=body.title,
        dry_run=True,
    )
    scope.session.add(thread)
    await scope.session.flush()
    await qa_api._audit(
        scope.session,
        operator_id=operator_id,
        tenant_id=scope.tenant.id,
        thread_id=thread.id,
        action="thread.create",
        target_kind="qa.thread",
        target_id=str(thread.id),
        payload={"title": body.title, "dry_run": True, "surface": "console"},
    )
    await scope.session.refresh(thread)
    return _thread_out(thread)


@router.patch("/clients/{ref}/playground/threads/{thread_id}", response_model=PlaygroundThreadOut)
async def patch_thread(
    body: PlaygroundThreadPatchIn,
    thread_id: Annotated[uuid.UUID, Path(...)],
    scope: ClientScope = Depends(client_scope("playground:run")),
) -> PlaygroundThreadOut:
    """Rename or (un)archive one of the caller's threads."""
    if body.title is None and body.archived is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of title or archived must be set",
        )
    operator_id = console_operator_id(scope.principal)
    await apply_operator_to_session(scope.session, operator_id)
    thread = await _own_thread(scope.session, thread_id, scope.tenant.id)
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
        await qa_api._audit(
            scope.session,
            operator_id=operator_id,
            tenant_id=scope.tenant.id,
            thread_id=thread.id,
            action="thread.patch",
            target_kind="qa.thread",
            target_id=str(thread.id),
            payload=changes,
        )
    await scope.session.flush()
    await scope.session.refresh(thread)
    return _thread_out(thread)


def _scrub_ucm(data: dict[str, Any]) -> dict[str, Any]:
    """The UCM's ``metadata`` stamps internal ids (tenant, conversation);
    the console never sees a tenant id, not even over the stream."""
    ucm = data.get("ucm")
    if not isinstance(ucm, dict):
        return data
    meta = ucm.get("metadata")
    if not isinstance(meta, dict):
        return data
    clean_meta = {k: v for k, v in meta.items() if k not in {"tenant_id", "conversation_id"}}
    return {**data, "ucm": {**ucm, "metadata": clean_meta}}


# ── runs (outside the client-scope transaction) ────────────────────────
#
# Starting a run must COMMIT the inbound message before the graph's
# checkpoint node persists the outbound (FK), and the SSE endpoint must
# not hold a transaction open across the stream. So these three routes
# resolve ``{ref}`` with ``resolve_mapping`` (same opaque 404 as
# ``client_scope``) and open their own short transactions.


@dataclass(frozen=True)
class PlaygroundRef:
    principal: ConsolePrincipal
    mapping: PartnerTenant

    @property
    def operator_id(self) -> str:
        return console_operator_id(self.principal)

    @property
    def tenant_id(self) -> uuid.UUID:
        return self.mapping.tenant_id


def playground_ref() -> Callable[..., Awaitable[PlaygroundRef]]:
    principal_dep = require_console_principal("playground:run")

    async def _dependency(
        ref: str = ClientRef,
        principal: ConsolePrincipal = Depends(principal_dep),
        session: AsyncSession = Depends(get_db_session),
    ) -> PlaygroundRef:
        mapping = await resolve_mapping(session, principal, ref)
        return PlaygroundRef(principal=principal, mapping=mapping)

    return _dependency


@router.post(
    "/clients/{ref}/playground/threads/{thread_id}/runs",
    response_model=PlaygroundRunStartOut,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        429: {"description": "Monthly playground token cap reached (Retry-After set)."},
        409: {"description": "Thread is archived."},
    },
)
async def start_run(
    body: PlaygroundRunStartIn,
    response: Response,
    thread_id: Annotated[uuid.UUID, Path(...)],
    pg: PlaygroundRef = Depends(playground_ref()),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> PlaygroundRunStartOut:
    """One turn: cap check → persist inbound + ``qa.runs`` → spawn the
    streaming driver → 202 with ``run_id`` (open the stream next)."""
    # Per-member burst limit: the monthly token cap is checked against
    # FINISHED runs, so a burst of parallel POSTs could overshoot it.
    if not await allow(
        redis,
        key=f"console:playground_run:{pg.principal.user_id}",
        per_minute=20,
        surface="console",
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many playground turns — slow down for a minute.",
        )
    partner: Partner = pg.principal.partner
    window = month_window()
    used_before = await partner_qa_tokens_used(session, partner.id, window)
    cap = partner.qa_monthly_token_cap
    if not hop_models_in_catalog(qa_api.QA_CLASSIFY_MODEL, qa_api.QA_RESPOND_MODEL):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=HUMAN_TURN_ERROR,
        )

    if used_before >= cap:
        await notify_cap_reached(partner.id, window)
        retry = retry_after_seconds(window)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Playground token cap reached for {window.period}: {used_before:,} of {cap:,} "
                f"tokens used. The cap resets on {window.next_start:%Y-%m-%d} (UTC); "
                "contact Auphere to raise it."
            ),
            headers={"Retry-After": str(retry)},
        )

    operator_id = pg.operator_id
    tenant_id = pg.tenant_id
    operator_token = _current_operator.set(operator_id)
    tenant_token = _current_tenant.set(tenant_id)
    try:
        async with session.begin():
            await apply_operator_to_session(session, operator_id)
            await apply_tenant_to_session(session, tenant_id)
            thread = await _own_thread(session, thread_id, tenant_id)
            if thread.archived_at is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail="Thread is archived"
                )
            conversation, customer, channel = await qa_api._ensure_qa_conversation(
                session, thread=thread, operator_id=operator_id
            )
            inbound = Message(
                tenant_id=tenant_id,
                conversation_id=conversation.id,
                direction=MessageDirection.INBOUND,
                content=body.prompt,
                tool_calls=[],
            )
            session.add(inbound)
            await session.flush()
            await session.refresh(inbound)
            qa_run = QARun(
                thread_id=thread.id, operator_id=operator_id, status=QA_RUN_STATUS_RUNNING
            )
            session.add(qa_run)
            thread.last_run_at = func.now()
            thread.message_count = (thread.message_count or 0) + 1
            await session.flush()
            await session.refresh(qa_run)

            run_id = qa_run.id
            conv_id = conversation.id
            inbound_id = inbound.id
            cust_id = customer.id
            chan_id = channel.id
            cust_identifier = customer.identifier
    finally:
        _current_tenant.reset(tenant_token)
        _current_operator.reset(operator_token)

    # Console threads are always dry-run (no toggle): the safe pipeline.
    pipeline = qa_api._get_qa_pipeline(live=False)
    graph_state = {
        "tenant_id": str(tenant_id),
        "channel_id": str(chan_id),
        "channel_type": ChannelType.WEB.value,
        "user_id": cust_identifier,
        "conversation_id": str(conv_id),
        "customer_id": str(cust_id),
        "inbound_message_id": str(inbound_id),
        "user_message": body.prompt,
    }
    graph_config = {"configurable": {"thread_id": str(thread_id)}}
    partner_id = partner.id

    async def _driver(handle: qa_streaming.RunHandle) -> None:
        from nexus_worker.metering.collector import SOURCE_QA, usage_turn

        # Contextvars + usage scope live INSIDE the task (fresh context per
        # asyncio Task) — same reasoning as ``api/qa.py::start_thread_run``.
        with (
            operator_context(operator_id),
            tenant_context(tenant_id),
            qa_thread_context(thread_id),
        ):
            async with usage_turn(
                tenant_id=tenant_id,
                turn_id=str(inbound_id),
                conversation_id=conv_id,
                source=SOURCE_QA,
            ):
                translator_state = qa_streaming._TranslatorState()
                async for event in pipeline.astream_events(
                    graph_state, config=graph_config, version="v2"
                ):
                    for name, data in qa_streaming.translate_event(event, translator_state):
                        if name == "ucm.final":
                            data = _scrub_ucm(data)
                        if name == "cost.updated":
                            handle.total_input_tokens += int(data.get("input_tokens") or 0)
                            handle.total_output_tokens += int(data.get("output_tokens") or 0)
                        qa_streaming._push_event(
                            handle,
                            qa_streaming.SSEEvent(
                                seq=qa_streaming._next_seq(handle), event=name, data=data
                            ),
                        )
        # The partner's bar moves without polling: prior spend + this turn.
        snapshot = budget_out(
            used_before + handle.total_input_tokens + handle.total_output_tokens, cap, window
        )
        qa_streaming._push_event(
            handle,
            qa_streaming.SSEEvent(
                seq=qa_streaming._next_seq(handle),
                event="budget.updated",
                data={
                    "used": snapshot.used,
                    "cap": snapshot.cap,
                    "remaining": snapshot.remaining,
                    "percent": snapshot.percent,
                    "exhausted": snapshot.exhausted,
                    "period": snapshot.period,
                    "resets_at": snapshot.resets_at.isoformat(),
                },
            ),
        )

    async def _on_complete(handle: qa_streaming.RunHandle) -> None:
        await qa_api._finalise_run_row(
            operator_id=operator_id,
            tenant_id=tenant_id,
            run_id=handle.run_id,
            final_status=handle.final_status or QA_RUN_STATUS_ERROR,
            final_error=handle.final_error,
            input_tokens=handle.total_input_tokens,
            output_tokens=handle.total_output_tokens,
        )
        if used_before + handle.total_input_tokens + handle.total_output_tokens >= cap:
            await notify_cap_reached(partner_id, window)

    await qa_streaming.start_run(
        run_id=run_id,
        thread_id=thread_id,
        operator_id=operator_id,
        driver=_driver,
        on_complete=_on_complete,
    )
    response.headers["Cache-Control"] = "no-store"
    return PlaygroundRunStartOut(run_id=run_id, thread_id=thread_id, status=QA_RUN_STATUS_RUNNING)


_ERROR_LINE = re.compile(r'^(data: .*"event"?)', re.M)


async def _scrub_stream(source: AsyncIterator[str]) -> AsyncIterator[str]:
    """The backoffice stream carries ``run.completed.error = str(exc)``
    (DB/provider/host details for operators). A partner only gets a
    human phrase — the stack stays in our logs, not on their screen."""
    async for frame in source:
        if "event: run.completed" in frame and '"error"' in frame:
            head, _, data_line = frame.partition("data: ")
            body, _, tail = data_line.partition("\n")
            try:
                payload = json.loads(body)
            except ValueError:  # pragma: no cover - defensive
                yield frame
                continue
            if payload.get("error"):
                payload["error"] = HUMAN_TURN_ERROR
            yield f"{head}data: {json.dumps(payload, separators=(',', ':'))}\n{tail}"
        else:
            yield frame


@router.get("/clients/{ref}/playground/threads/{thread_id}/stream")
async def stream_run(
    thread_id: Annotated[uuid.UUID, Path(...)],
    pg: PlaygroundRef = Depends(playground_ref()),
    session: AsyncSession = Depends(get_db_session),
    run_id: uuid.UUID = Query(...),
    since_seq: int = Query(default=0, ge=0),
) -> StreamingResponse:
    """SSE of one run — the ONLY channel that carries the test transcript.

    Ownership: the ``qa.runs`` row must be visible under the caller's
    operator (RLS), belong to ``thread_id``, and the thread must be on
    this client. Verified in a short transaction that commits before the
    stream starts. Events: ``run.started``, ``text.delta``,
    ``reasoning.delta``, ``cost.updated``, ``tool.call.started``,
    ``tool.call.completed``, ``audit.blocked``, ``ucm.final``,
    ``budget.updated``, ``run.completed``, ``resume.gap``, ``ping``.
    """
    operator_token = _current_operator.set(pg.operator_id)
    try:
        async with session.begin():
            await apply_operator_to_session(session, pg.operator_id)
            await session.execute(text("SET LOCAL ROLE nexus_app"))
            run = await session.get(QARun, run_id)
            if run is None or run.thread_id != thread_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown run")
            await _own_thread(session, thread_id, pg.tenant_id)
    finally:
        _current_operator.reset(operator_token)

    headers = {
        "Cache-Control": "no-store",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return StreamingResponse(
        _scrub_stream(qa_streaming.subscribe(run_id, since_seq=since_seq)),
        media_type="text/event-stream",
        headers=headers,
    )


@router.delete("/clients/{ref}/playground/runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_run(
    run_id: Annotated[uuid.UUID, Path(...)],
    pg: PlaygroundRef = Depends(playground_ref()),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    """Stop relaying an in-flight run (the ``qa.runs`` row closes as
    ``cancelled``; tokens already spent still count)."""
    operator_token = _current_operator.set(pg.operator_id)
    try:
        async with session.begin():
            await apply_operator_to_session(session, pg.operator_id)
            await session.execute(text("SET LOCAL ROLE nexus_app"))
            run = await session.get(QARun, run_id)
            if run is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown run")
            await _own_thread(session, run.thread_id, pg.tenant_id)
    finally:
        _current_operator.reset(operator_token)
    await qa_streaming.cancel(run_id)


__all__ = [
    "CONSOLE_OPERATOR_PREFIX",
    "MonthWindow",
    "budget_out",
    "console_operator_id",
    "month_window",
    "partner_qa_tokens_used",
    "retry_after_seconds",
    "router",
]
