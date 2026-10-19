"""Spec 031 — the operator panel's home: the instance at a glance.

``GET /admin/overview`` adds up what already exists. Platform tables are read
directly; the partner-scoped ones with FORCE RLS are read **per partner,
under that partner's GUC** (``apply_partner_to_session``) — the overview
never lifts RLS to read across partners. Tickets use the admin policy
(``app.is_admin``) like the ticket inbox.

Honest states (constitution §V): a section that cannot be read is named in
``unreadable`` and comes back empty or ``None``; the rest of the page still
answers (state ``parcial``).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.billing.pricing import credits_to_cents
from nexus_api.core.partner_context import apply_admin_to_session, apply_partner_to_session
from nexus_api.core.security import require_admin_token
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Partner, PartnerAllocation, Tenant
from nexus_api.db.models.signup import SignupRequest
from nexus_api.db.models.support_ticket import SupportTicket
from nexus_api.metering.wallet import read_wallet

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/overview", dependencies=[Depends(require_admin_token)])
instance_router = APIRouter(prefix="/instance", dependencies=[Depends(require_admin_token)])

#: How many rows of each attention list the home shows; the count is exact.
ATTENTION_LIMIT = 5


class PartnerCounts(BaseModel):
    total: int
    active: int


class ClientCounts(BaseModel):
    total: int
    active: int
    paused: int


class OpenTicketOut(BaseModel):
    id: uuid.UUID
    ticket_ref: str
    partner_id: uuid.UUID
    partner_name: str
    topic: str
    opened_at: datetime


class PendingSignupOut(BaseModel):
    id: uuid.UUID
    email: str
    created_at: datetime


class ClientWithoutCapOut(BaseModel):
    tenant_id: uuid.UUID
    name: str
    partner_id: uuid.UUID
    partner_name: str


class PartnerCardOut(BaseModel):
    """Spec 041: a partner's card news — newly saved, or charges stopped."""

    partner_id: uuid.UUID
    name: str
    card_brand: str | None
    card_last4: str | None
    card_saved_at: datetime | None
    mode: str
    paused_reason: str | None


#: How recent a saved card is still news on the Panel.
CARD_NEWS_DAYS = 14


class OverviewOut(BaseModel):
    partners: PartnerCounts
    clients: ClientCounts
    #: Sum of every partner's available balance in US$ cents (rounded down
    #: per partner, as each console shows it). None if no balance was read.
    balance_cents: int | None
    tickets_open: int
    open_tickets: list[OpenTicketOut]
    signups_pending: int
    pending_signups: list[PendingSignupOut]
    clients_without_cap: list[ClientWithoutCapOut]
    #: Spec 041: cards saved in the last ``CARD_NEWS_DAYS`` days.
    cards_added: list[PartnerCardOut] = []
    #: Spec 041: partners whose automatic charges stopped (card declined).
    charges_paused: list[PartnerCardOut] = []
    #: Sections that could not be read: ``balance``, ``caps``, ``tickets``.
    unreadable: list[str]


@router.get("", response_model=OverviewOut)
async def get_overview(session: AsyncSession = Depends(get_db_session)) -> OverviewOut:
    unreadable: list[str] = []

    partners = list((await session.execute(sa.select(Partner).order_by(Partner.name))).scalars())
    names = {p.id: p.name for p in partners}
    tenant_rows = (
        await session.execute(sa.select(Tenant.status, sa.func.count()).group_by(Tenant.status))
    ).all()
    by_status = {str(getattr(s, "value", s)): int(n) for s, n in tenant_rows}

    # Money: one read per partner under its own GUC.
    balance: int | None = 0
    readable = 0
    for p in partners:
        snap = await read_wallet(p.id)
        if snap is None:
            continue
        readable += 1
        balance = (balance or 0) + credits_to_cents(snap.available)
    if partners and readable == 0:
        balance = None

    # Clients whose cap is spent: partner_allocations is FORCE by partner.
    without_cap: list[ClientWithoutCapOut] = []
    try:
        sm = get_sessionmaker()
        for p in partners:
            async with sm() as s, s.begin():
                await apply_partner_to_session(s, p.id)
                rows = (
                    await s.execute(
                        sa.select(PartnerAllocation.tenant_id, Tenant.name)
                        .join(Tenant, Tenant.id == PartnerAllocation.tenant_id)
                        .where(PartnerAllocation.partner_id == p.id)
                        .where(PartnerAllocation.remaining <= 0)
                        .order_by(Tenant.name)
                    )
                ).all()
            without_cap.extend(
                ClientWithoutCapOut(tenant_id=t, name=n, partner_id=p.id, partner_name=p.name)
                for t, n in rows
            )
    except Exception as exc:  # pragma: no cover - surfaced as a partial state
        log.warning("admin.overview.caps_unreadable", error=str(exc))
        unreadable.append("caps")
        without_cap = []

    tickets_open = 0
    open_tickets: list[OpenTicketOut] = []
    try:
        sm = get_sessionmaker()
        async with sm() as s, s.begin():
            await apply_admin_to_session(s)
            tickets_open = int(
                await s.scalar(
                    sa.select(sa.func.count())
                    .select_from(SupportTicket)
                    .where(SupportTicket.status == "open")
                )
                or 0
            )
            tickets = (
                await s.execute(
                    sa.select(SupportTicket)
                    .where(SupportTicket.status == "open")
                    .order_by(SupportTicket.opened_at)
                    .limit(ATTENTION_LIMIT)
                )
            ).scalars()
            open_tickets = [
                OpenTicketOut(
                    id=t.id,
                    ticket_ref=t.ticket_ref,
                    partner_id=t.partner_id,
                    partner_name=names.get(t.partner_id, ""),
                    topic=t.topic,
                    opened_at=t.opened_at,
                )
                for t in tickets
            ]
    except Exception as exc:  # pragma: no cover - surfaced as a partial state
        log.warning("admin.overview.tickets_unreadable", error=str(exc))
        unreadable.append("tickets")

    signups_pending = int(
        await session.scalar(
            sa.select(sa.func.count())
            .select_from(SignupRequest)
            .where(SignupRequest.status == "pending")
        )
        or 0
    )
    pending = (
        await session.execute(
            sa.select(SignupRequest)
            .where(SignupRequest.status == "pending")
            .order_by(SignupRequest.created_at.desc())
            .limit(ATTENTION_LIMIT)
        )
    ).scalars()

    if balance is None:
        unreadable.append("balance")

    # Spec 041: card news, read partner by partner under its own GUC.
    from nexus_api.services.partner_billing import billing_summary

    cards_added: list[PartnerCardOut] = []
    charges_paused: list[PartnerCardOut] = []
    since_cards = datetime.now(UTC) - timedelta(days=CARD_NEWS_DAYS)
    try:
        for p in partners:
            b = await billing_summary(p.id)
            item = PartnerCardOut(
                partner_id=p.id,
                name=p.name,
                card_brand=b.card_brand,
                card_last4=b.card_last4,
                card_saved_at=b.card_saved_at,
                mode=b.mode,
                paused_reason=b.paused_reason or ("line_frozen" if b.credit_frozen else None),
            )
            if b.paused_reason or b.credit_frozen:
                charges_paused.append(item)
            if b.card_saved_at is not None and b.card_saved_at >= since_cards:
                cards_added.append(item)
    except Exception as exc:  # pragma: no cover - partial state
        log.warning("admin.overview.cards_unreadable", error=str(exc))
        unreadable.append("cards")
    cards_added.sort(key=lambda c: c.card_saved_at or since_cards, reverse=True)

    return OverviewOut(
        partners=PartnerCounts(
            total=len(partners), active=sum(1 for p in partners if p.status == "active")
        ),
        clients=ClientCounts(
            total=sum(by_status.values()),
            active=by_status.get("active", 0),
            paused=by_status.get("paused", 0),
        ),
        balance_cents=balance,
        tickets_open=tickets_open,
        open_tickets=open_tickets,
        signups_pending=signups_pending,
        pending_signups=[
            PendingSignupOut(id=r.id, email=r.email, created_at=r.created_at) for r in pending
        ],
        clients_without_cap=without_cap,
        cards_added=cards_added[:ATTENTION_LIMIT],
        charges_paused=charges_paused,
        unreadable=sorted(unreadable),
    )


class InstanceOut(BaseModel):
    """Spec 031 (R6): what the Estado page says about this deployment."""

    environment: str
    #: Alembic head the database is on. None if it could not be read.
    schema_revision: str | None
    #: Commit the API image was built from (``NEXUS_GIT_SHA``); "unknown" locally.
    commit: str
    checks: dict[str, str]


@instance_router.get("", response_model=InstanceOut)
async def get_instance(session: AsyncSession = Depends(get_db_session)) -> InstanceOut:
    import os

    from nexus_api.config import get_settings
    from nexus_api.health import _check_redis

    checks: dict[str, str] = {}
    revision: str | None = None
    try:
        revision = await session.scalar(sa.text("SELECT version_num FROM alembic_version"))
        checks["postgres"] = "ok"
    except Exception as exc:
        checks["postgres"] = f"error: {type(exc).__name__}"
    try:
        await _check_redis()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {type(exc).__name__}"
    return InstanceOut(
        environment=get_settings().environment,
        schema_revision=revision,
        commit=os.environ.get("NEXUS_GIT_SHA", "unknown"),
        checks=checks,
    )
