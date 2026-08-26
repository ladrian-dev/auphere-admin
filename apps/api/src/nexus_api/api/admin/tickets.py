"""Admin F4 — inbox de tickets de soporte de partners.

Listado unscoped vía ``app.is_admin`` (policy extra, no BYPASSRLS).
Persist y lectura de partner corren bajo FORCE RLS ``app.partner_id``.
``partner_id`` de query es filtro, nunca el GUC ni el cuerpo.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin.partners import _admin_actor
from nexus_api.api.deps import get_db_session
from nexus_api.core.partner_context import apply_admin_to_session
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import AuditLog, Partner
from nexus_api.db.models.support_ticket import (
    EVENT_STATUS,
    TICKET_STATUSES,
    SupportTicket,
    SupportTicketEvent,
)
from nexus_api.schemas.admin_tickets import (
    AdminTicketDetailOut,
    AdminTicketEventOut,
    AdminTicketLinksOut,
    AdminTicketOut,
    AdminTicketStatusIn,
)

router = APIRouter(prefix="/tickets", dependencies=[Depends(require_admin_token)])

_LIST_QUERY_KEYS = frozenset({"status", "partner_id"})


def _unknown_ticket() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown ticket")


def _links(partner_id: uuid.UUID) -> AdminTicketLinksOut:
    base = f"/partners/{partner_id}"
    return AdminTicketLinksOut(
        consumo=f"{base}/wallet",
        modelos=f"{base}/models",
        conocimiento=f"{base}/knowledge",
        auditoria=f"{base}/audit",
    )


def _out(ticket: SupportTicket, partner: Partner) -> AdminTicketOut:
    return AdminTicketOut(
        id=ticket.id,
        ticket_ref=ticket.ticket_ref,
        partner_id=ticket.partner_id,
        partner_name=partner.name,
        partner_slug=partner.slug,
        category=ticket.category,
        topic=ticket.topic,
        sla=ticket.sla,
        status=ticket.status,
        client_ref=ticket.client_ref,
        need=ticket.need,
        checked=[str(x) for x in (ticket.checked or [])],
        alternative=ticket.alternative,
        bridge=ticket.bridge,
        opened_by=ticket.opened_by,
        opened_at=ticket.opened_at,
        created_at=ticket.opened_at,
        updated_at=ticket.updated_at,
    )


def _detail(
    ticket: SupportTicket, partner: Partner, events: list[SupportTicketEvent]
) -> AdminTicketDetailOut:
    base = _out(ticket, partner)
    return AdminTicketDetailOut(
        **base.model_dump(),
        events=[
            AdminTicketEventOut(
                id=ev.id,
                kind=ev.kind,
                from_status=ev.from_status,
                to_status=ev.to_status,
                actor=ev.actor,
                created_at=ev.created_at,
            )
            for ev in events
        ],
        links=_links(ticket.partner_id),
    )


@router.get("", response_model=list[AdminTicketOut])
async def list_tickets(
    request: Request,
    status_filter: str | None = Query(
        default=None, alias="status", pattern="^(open|pending|closed)$"
    ),
    partner_id: uuid.UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> list[AdminTicketOut]:
    """Inbox global. ``app.is_admin``; ``partner_id`` es filtro, no GUC."""
    extra = set(request.query_params) - _LIST_QUERY_KEYS
    if extra:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="extra fields not permitted",
        )
    stmt = (
        sa.select(SupportTicket, Partner)
        .join(Partner, Partner.id == SupportTicket.partner_id)
        .order_by(SupportTicket.opened_at.desc())
        .limit(200)
    )
    if status_filter is not None:
        stmt = stmt.where(SupportTicket.status == status_filter)
    if partner_id is not None:
        stmt = stmt.where(SupportTicket.partner_id == partner_id)
    async with session.begin():
        await apply_admin_to_session(session)
        rows = (await session.execute(stmt)).all()
        items = [_out(ticket, partner) for ticket, partner in rows]
    return items


@router.get(
    "/{ticket_id}",
    response_model=AdminTicketDetailOut,
    responses={404: {"description": "Ticket not found."}},
)
async def get_ticket(
    ticket_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> AdminTicketDetailOut:
    async with session.begin():
        await apply_admin_to_session(session)
        ticket = await session.get(SupportTicket, ticket_id)
        if ticket is None:
            raise _unknown_ticket()
        partner = await session.get(Partner, ticket.partner_id)
        if partner is None:
            raise _unknown_ticket()
        events = (
            await session.scalars(
                sa.select(SupportTicketEvent)
                .where(SupportTicketEvent.ticket_id == ticket.id)
                .order_by(SupportTicketEvent.created_at.asc())
            )
        ).all()
        out = _detail(ticket, partner, list(events))
    return out


@router.patch(
    "/{ticket_id}",
    response_model=AdminTicketDetailOut,
    responses={
        404: {"description": "Ticket not found."},
        422: {"description": "status fuera de open|pending|closed, o campos extra."},
    },
)
async def patch_ticket(
    ticket_id: uuid.UUID,
    body: AdminTicketStatusIn,
    session: AsyncSession = Depends(get_db_session),
    token: str = Depends(require_admin_token),
) -> AdminTicketDetailOut:
    if body.status not in TICKET_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="status must be open, pending or closed",
        )
    actor = _admin_actor(token)
    async with session.begin():
        await apply_admin_to_session(session)
        ticket = await session.get(SupportTicket, ticket_id)
        if ticket is None:
            raise _unknown_ticket()
        partner = await session.get(Partner, ticket.partner_id)
        if partner is None:
            raise _unknown_ticket()
        before = ticket.status
        if before != body.status:
            session.add(
                AuditLog(
                    tenant_id=None,
                    actor=actor,
                    action="ticket.status",
                    target=f"ticket:{ticket.ticket_ref}",
                    before_json={"status": before},
                    after_json={"status": body.status, "ticket_ref": ticket.ticket_ref},
                )
            )
            await session.flush()
        ticket = await session.get(SupportTicket, ticket_id)
        if ticket is None:
            raise _unknown_ticket()
        if before != body.status:
            ticket.status = body.status
            ticket.updated_at = datetime.now(UTC)
            session.add(
                SupportTicketEvent(
                    ticket_id=ticket.id,
                    partner_id=ticket.partner_id,
                    kind=EVENT_STATUS,
                    from_status=before,
                    to_status=body.status,
                    actor=actor,
                )
            )
            await session.flush()
        events = (
            await session.scalars(
                sa.select(SupportTicketEvent)
                .where(SupportTicketEvent.ticket_id == ticket.id)
                .order_by(SupportTicketEvent.created_at.asc())
            )
        ).all()
        out = _detail(ticket, partner, list(events))
    return out
