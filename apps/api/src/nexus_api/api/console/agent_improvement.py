"""Rendimiento, conversaciones y mejoras de un agente — spec 047, T174 (requisito 51;
``contracts/console-api.md`` §4).

- ``GET …/agents/{agent_id}/performance?days=30`` [``agents:read``]: los últimos
  30 días, en total y por día (la gráfica de bloques): conversaciones, resueltas
  sin persona, pasadas a una persona, gasto y gasto medio por conversación
  (51.1);
- ``GET …/agents/{agent_id}/conversations?cursor=&limit=``
  [``conversations:read``]: la lista **solo con metadatos** (51.2);
- ``GET …/agents/{agent_id}/improvements`` [``agents:read``]: las sugerencias
  semanales abiertas, con su paráfrasis, a cuántos afectó, el diff y la prueba
  (51.3);
- ``POST …/improvements/{id}/accept`` [``agents:write``]: el cambio al borrador y
  la prueba a la suite; publicar pasa la puerta (51.4);
- ``POST …/improvements/{id}/discard`` [``agents:write``] ``{reason}``: con su
  motivo; no vuelve en 30 días (51.4).

Ninguna respuesta lleva cuerpos de mensaje, datos del cliente final ni costes
(C1, C8 y C9): el dinero va a precio, en ``{amount_micros, currency}``, y una
sugerencia no dice a qué conversaciones ni a qué contactos se refiere. Las
sugerencias se generan en el worker (``weekly_suggestions_cron``); aquí solo se
leen y se deciden.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any, Literal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from nexus_api.db.models import Agent, AuditLog, InboxCorrection
from nexus_api.db.models.agent_spec import Proposal
from nexus_api.services.agent_spec.patch import PatchError, apply_ops
from nexus_api.services.agent_spec.schema import dump
from nexus_api.services.agent_spec.validator import load_context, problems_out, validate_spec
from nexus_api.services.improvement import performance as perf
from nexus_api.services.improvement import suggestions as svc

from .agent_draft_routes import agent_in_path
from .agent_spec_drafts import current_spec, write_spec
from .deps import ClientScope

router = APIRouter(prefix="/clients/{ref}/agents/{agent_id}")


class Money(BaseModel):
    #: Cien milésimas de la moneda (``contracts/console-api.md``, Convenciones).
    amount_micros: int
    currency: Literal["USD"] = "USD"


def _money(micros: int | None) -> Money | None:
    return None if micros is None else Money(amount_micros=int(micros))


# ── rendimiento ────────────────────────────────────────────────────────────


class PerformanceDayOut(BaseModel):
    day: date
    conversations: int
    resolved_without_person: int
    handed_to_person: int
    spent: Money


class PerformanceOut(BaseModel):
    days: int
    since: datetime
    until: datetime
    conversations: int
    resolved_without_person: int
    handed_to_person: int
    resolved_pct: float | None = None
    spent: Money
    spend_per_conversation: Money | None = None
    series: list[PerformanceDayOut]


@router.get("/performance", response_model=PerformanceOut)
async def get_performance(
    days: int = Query(default=perf.DEFAULT_DAYS, ge=1, le=perf.MAX_DAYS),
    scope: ClientScope = Depends(agent_in_path("agents:read")),
) -> PerformanceOut:
    assert scope.agent_id is not None
    found = await perf.agent_performance(scope.session, scope.agent_id, days=days)
    return PerformanceOut(
        days=found.days,
        since=found.since,
        until=found.until,
        conversations=found.conversations,
        resolved_without_person=found.resolved_without_person,
        handed_to_person=found.handed_to_person,
        resolved_pct=found.resolved_pct,
        spent=Money(amount_micros=found.spent_micros),
        spend_per_conversation=_money(found.spend_per_conversation_micros),
        series=[
            PerformanceDayOut(
                day=d.day,
                conversations=d.conversations,
                resolved_without_person=d.resolved_without_person,
                handed_to_person=d.handed_to_person,
                spent=Money(amount_micros=d.spent_micros),
            )
            for d in found.series
        ],
    )


# ── conversaciones (solo metadatos) ────────────────────────────────────────


class AgentConversationOut(BaseModel):
    """Una conversación sin una palabra de ella (C1 y C8)."""

    id: uuid.UUID
    started_at: datetime
    last_activity_at: datetime
    channel_type: str | None = None
    duration_seconds: int | None = None
    messages_count: int
    outcome: Literal["handed_to_person", "resolved_without_person"]
    in_progress: bool
    #: Un código (``escalated``, ``taken_by_person``, ``no_balance``…); la consola
    #: pone las palabras.
    handoff_reason: str | None = None
    spent: Money | None = None


class AgentConversationPageOut(BaseModel):
    items: list[AgentConversationOut]
    next_cursor: str | None = None


@router.get("/conversations", response_model=AgentConversationPageOut)
async def list_agent_conversations(
    cursor: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=100),
    scope: ClientScope = Depends(agent_in_path("conversations:read")),
) -> AgentConversationPageOut:
    assert scope.agent_id is not None
    try:
        items, next_cursor = await perf.agent_conversations(
            scope.session, scope.agent_id, limit=limit, cursor=cursor
        )
    except perf.CursorInvalid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": "cursor_invalid"}
        ) from None
    return AgentConversationPageOut(
        items=[
            AgentConversationOut(
                id=c.id,
                started_at=c.started_at,
                last_activity_at=c.last_activity_at,
                channel_type=c.channel_type,
                duration_seconds=c.duration_seconds,
                messages_count=c.messages_count,
                outcome="handed_to_person" if c.handed_to_person else "resolved_without_person",
                in_progress=c.in_progress,
                handoff_reason=c.handoff_reason,
                spent=_money(c.spent_micros),
            )
            for c in items
        ],
        next_cursor=next_cursor,
    )


# ── mejoras: las sugerencias semanales ─────────────────────────────────────


class SuggestedTestOut(BaseModel):
    name: str
    persona: str
    first_message: str
    plan: str
    criteria: list[dict[str, Any]]
    critical: bool


class ImprovementOut(BaseModel):
    id: uuid.UUID
    #: Las sugerencias semanales y las correcciones de comportamiento que manda
    #: una persona del cliente desde la Bandeja (52.2, 52.3).
    kind: Literal["suggestion", "correction"]
    #: La semana de la sugerencia; ``None`` en una corrección.
    week: date | None = None
    #: La paráfrasis, sin datos personales.
    topic: str
    summary: str | None = None
    #: Solo en una corrección: la lección que escribió la persona del cliente y
    #: desde dónde la mandó. Nunca el mensaje ni la conversación (C1).
    lesson: str | None = None
    origin: str | None = None
    conversations_count: int = 0
    contacts_count: int = 0
    proposal_id: uuid.UUID | None = None
    #: El parche del AgentSpec (``{"ops": [...]}``).
    diff: dict[str, Any]
    test: SuggestedTestOut | None = None
    created_at: datetime


class ImprovementsOut(BaseModel):
    items: list[ImprovementOut]
    allowed: list[Literal["accept", "discard"]] = Field(default_factory=list)


@router.get("/improvements", response_model=ImprovementsOut)
async def list_improvements(
    scope: ClientScope = Depends(agent_in_path("agents:read")),
) -> ImprovementsOut:
    assert scope.agent_id is not None
    rows = await svc.open_suggestions(scope.session, scope.agent_id)
    proposals = await svc.proposals_of(scope.session, rows)
    items: list[ImprovementOut] = []
    for row in rows:
        ops, test = svc.change_of(proposals.get(row.proposal_id) if row.proposal_id else None)
        items.append(
            ImprovementOut(
                id=row.id,
                kind="suggestion",
                week=row.week,
                topic=row.topic,
                summary=row.summary,
                conversations_count=row.conversations_count,
                contacts_count=row.contacts_count,
                proposal_id=row.proposal_id,
                diff={"ops": ops},
                test=SuggestedTestOut(
                    name=str(test.get("name") or ""),
                    persona=str(test.get("persona") or ""),
                    first_message=str(test.get("first_message") or ""),
                    plan=str(test.get("plan") or ""),
                    criteria=list(test.get("criteria") or []),
                    critical=bool(test.get("critical", False)),
                )
                if test is not None
                else None,
                created_at=row.created_at,
            )
        )
    for correction, proposal in await _open_corrections(scope):
        ops, test = svc.change_of(proposal)
        items.append(
            ImprovementOut(
                id=correction.id,
                kind="correction",
                topic=correction.paraphrase or correction.lesson,
                summary=correction.lesson,
                lesson=correction.lesson,
                origin=correction.origin,
                conversations_count=1,
                contacts_count=1,
                proposal_id=correction.proposal_id,
                diff={"ops": ops},
                test=_test_out(test),
                created_at=correction.sent_at or correction.created_at,
            )
        )
    writes = "agents:write" in scope.principal.permissions
    return ImprovementsOut(items=items, allowed=["accept", "discard"] if writes else [])


def _test_out(test: dict[str, Any] | None) -> SuggestedTestOut | None:
    if test is None:
        return None
    return SuggestedTestOut(
        name=str(test.get("name") or ""),
        persona=str(test.get("persona") or ""),
        first_message=str(test.get("first_message") or ""),
        plan=str(test.get("plan") or ""),
        criteria=list(test.get("criteria") or []),
        critical=bool(test.get("critical", False)),
    )


async def _open_corrections(scope: ClientScope) -> list[tuple[InboxCorrection, Proposal | None]]:
    """Las correcciones de comportamiento de **este** agente que esperan decisión."""
    rows = (
        await scope.session.scalars(
            sa.select(InboxCorrection)
            .where(
                InboxCorrection.agent_id == scope.agent_id,
                InboxCorrection.kind == "behavior",
                InboxCorrection.status == "proposed",
            )
            .order_by(InboxCorrection.sent_at.desc(), InboxCorrection.id)
        )
    ).all()
    ids = [r.proposal_id for r in rows if r.proposal_id is not None]
    proposals = (
        {
            p.id: p
            for p in (
                await scope.session.scalars(sa.select(Proposal).where(Proposal.id.in_(ids)))
            ).all()
        }
        if ids
        else {}
    )
    return [(r, proposals.get(r.proposal_id) if r.proposal_id else None) for r in rows]


async def _correction_for_decision(
    scope: ClientScope, improvement_id: uuid.UUID
) -> tuple[InboxCorrection, Proposal] | None:
    """La corrección de **este** agente, bloqueada; ``None`` si el id no es de una
    corrección (entonces es una sugerencia, o no existe)."""
    row = await scope.session.scalar(
        sa.select(InboxCorrection)
        .where(
            InboxCorrection.id == improvement_id,
            InboxCorrection.agent_id == scope.agent_id,
            InboxCorrection.kind == "behavior",
        )
        .with_for_update()
    )
    if row is None:
        return None
    if row.status != "proposed" or row.proposal_id is None:
        raise _error(svc.SuggestionError("improvement_closed", status.HTTP_409_CONFLICT))
    proposal = await scope.session.scalar(
        sa.select(Proposal).where(Proposal.id == row.proposal_id).with_for_update()
    )
    if proposal is None or proposal.status in {"applied", "rejected"}:
        raise _error(svc.SuggestionError("improvement_closed", status.HTTP_409_CONFLICT))
    return row, proposal


async def _apply_change(
    scope: ClientScope, proposal: Proposal, *, author: Literal["suggestion", "correction"]
) -> tuple[int, uuid.UUID]:
    """El parche sobre el borrador de ahora, validado, y su prueba en la suite. Nada
    se publica: «Guardar» pasa la puerta como cualquier cambio. Devuelve la revisión
    del borrador y la prueba añadida."""
    from nexus_api.services.testing.suites import add_test, ensure_suite

    assert scope.agent_id is not None
    ops, test = svc.change_of(proposal)
    if not ops or test is None:
        raise _error(svc.SuggestionError("improvement_outdated", status.HTTP_409_CONFLICT))
    spec, _cfg = await current_spec(scope)
    if spec is None:
        raise _error(svc.SuggestionError("no_version", status.HTTP_409_CONFLICT))
    try:
        doc = apply_ops(dump(spec), ops)
    except PatchError as exc:
        raise _error(
            svc.SuggestionError(
                "improvement_outdated", status.HTTP_409_CONFLICT, pointer=exc.pointer
            )
        ) from None
    ctx = await load_context(
        scope.session,
        partner_id=scope.principal.partner.id,
        legacy_chars=svc.legacy_chars_of(spec),
    )
    checked, problems = validate_spec(doc, ctx, author=author)
    if checked is None or problems:
        raise _error(
            svc.SuggestionError(
                "invalid_proposal",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                problems=problems_out(problems),
            )
        )
    await write_spec(scope, checked, expected_revision=None)
    suite = await ensure_suite(scope.session, scope.agent_id)
    added = await add_test(scope.session, suite, test, kind="conversation", by=author)
    agent = await scope.session.get(Agent, scope.agent_id, populate_existing=True)
    return (int(agent.draft_revision) if agent is not None else 0), added.id


def _decide_correction(
    row: InboxCorrection, proposal: Proposal, *, accepted: bool, actor: str
) -> None:
    now = datetime.now(UTC)
    row.status = "accepted" if accepted else "rejected"
    proposal.status = "applied" if accepted else "rejected"
    proposal.decided_by = actor
    proposal.decided_at = now


class AcceptedOut(BaseModel):
    id: uuid.UUID
    status: Literal["accepted"]
    draft_revision: int
    test_id: uuid.UUID


class DiscardIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: Por qué no (51.4). Obligatorio.
    reason: str = Field(min_length=3, max_length=300)

    @field_validator("reason")
    @classmethod
    def _tidy(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 3:
            raise ValueError("reason_required")
        return value


class DiscardedOut(BaseModel):
    id: uuid.UUID
    status: Literal["discarded"]
    #: Hasta cuándo no vuelve (las sugerencias); ``None`` en una corrección.
    suppress_until: datetime | None = None


def _error(exc: svc.SuggestionError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail={"code": exc.code, **exc.extra})


@router.post(
    "/improvements/{improvement_id}/accept",
    response_model=AcceptedOut,
    responses={
        404: {"description": "unknown_improvement"},
        409: {"description": "improvement_closed · improvement_outdated · no_version"},
        422: {"description": "The patched spec does not pass the validator."},
    },
)
async def accept_improvement(
    improvement_id: uuid.UUID,
    scope: ClientScope = Depends(agent_in_path("agents:write")),
) -> AcceptedOut:
    """«Aceptar» (51.4, 52.3): el parche se aplica sobre el borrador de ahora y vuelve
    a pasar el validador; la prueba entra en la suite. Nada se publica: «Guardar»
    pasa la puerta como cualquier cambio."""
    assert scope.agent_id is not None
    correction = await _correction_for_decision(scope, improvement_id)
    if correction is not None:
        row_c, proposal_c = correction
        revision, test_id = await _apply_change(scope, proposal_c, author="correction")
        _decide_correction(row_c, proposal_c, accepted=True, actor=scope.principal.actor)
        scope.session.add(
            AuditLog(
                tenant_id=scope.tenant.id,
                actor=scope.principal.actor,
                action="correction.accepted",
                target=f"agent:{scope.agent_id}",
                after_json={
                    "correction_id": str(row_c.id),
                    "proposal_id": str(proposal_c.id),
                    "test_id": str(test_id),
                    "draft_revision": revision,
                },
            )
        )
        await scope.session.flush()
        return AcceptedOut(id=row_c.id, status="accepted", draft_revision=revision, test_id=test_id)
    try:
        row, proposal = await svc.for_decision(
            scope.session, improvement_id, agent_id=scope.agent_id
        )
    except svc.SuggestionError as exc:
        raise _error(exc) from None
    assert proposal is not None
    revision, test_id = await _apply_change(scope, proposal, author="suggestion")
    svc.mark_accepted(row, proposal, actor=scope.principal.actor, test_id=test_id)
    scope.session.add(
        AuditLog(
            tenant_id=scope.tenant.id,
            actor=scope.principal.actor,
            action="suggestion.accepted",
            target=f"agent:{scope.agent_id}",
            after_json={
                "suggestion_id": str(row.id),
                "proposal_id": str(proposal.id),
                "week": row.week.isoformat(),
                "topic_key": row.topic_key,
                "conversations_count": row.conversations_count,
                "contacts_count": row.contacts_count,
                "test_id": str(test_id),
                "draft_revision": revision,
            },
        )
    )
    await scope.session.flush()
    return AcceptedOut(id=row.id, status="accepted", draft_revision=revision, test_id=test_id)


@router.post(
    "/improvements/{improvement_id}/discard",
    response_model=DiscardedOut,
    responses={404: {"description": "unknown_improvement"}, 409: {"description": "closed"}},
)
async def discard_improvement(
    improvement_id: uuid.UUID,
    body: DiscardIn,
    scope: ClientScope = Depends(agent_in_path("agents:write")),
) -> DiscardedOut:
    """«Descartar» (51.4): pide el motivo; la misma sugerencia no vuelve en 30 días.
    Una corrección descartada queda «rechazada» con su motivo."""
    assert scope.agent_id is not None
    correction = await _correction_for_decision(scope, improvement_id)
    if correction is not None:
        row_c, proposal_c = correction
        _decide_correction(row_c, proposal_c, accepted=False, actor=scope.principal.actor)
        scope.session.add(
            AuditLog(
                tenant_id=scope.tenant.id,
                actor=scope.principal.actor,
                action="correction.rejected",
                target=f"agent:{scope.agent_id}",
                after_json={"correction_id": str(row_c.id), "discard_reason": body.reason},
            )
        )
        await scope.session.flush()
        return DiscardedOut(id=row_c.id, status="discarded", suppress_until=None)
    try:
        row, proposal = await svc.for_decision(
            scope.session, improvement_id, agent_id=scope.agent_id
        )
    except svc.SuggestionError as exc:
        raise _error(exc) from None
    svc.mark_discarded(row, proposal, actor=scope.principal.actor, reason=body.reason)
    assert row.suppress_until is not None
    scope.session.add(
        AuditLog(
            tenant_id=scope.tenant.id,
            actor=scope.principal.actor,
            action="suggestion.discarded",
            target=f"agent:{scope.agent_id}",
            after_json={
                "suggestion_id": str(row.id),
                "week": row.week.isoformat(),
                "topic_key": row.topic_key,
                "discard_reason": body.reason,
                "suppress_until": row.suppress_until.isoformat(),
            },
        )
    )
    await scope.session.flush()
    return DiscardedOut(id=row.id, status="discarded", suppress_until=row.suppress_until)


__all__ = ["router"]
