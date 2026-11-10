"""Spec 050 (D6) — a WhatsApp opt-out is respected everywhere, the same way.

One registry (``whatsapp_opt_outs``) and three questions about it, asked by
the webhook, the outbound dispatcher, broadcasts, direct messages, the
reminder crons and the operator panel:

- :func:`record` — a person opted out: through Meta (``user_preferences``
  ``stop``, ``source=meta``), by writing a stop word (``source=keyword``) or
  because an operator did it (``source=operator``). New opt-outs are of
  **marketing** (``scope=marketing``); every row from before spec 050 stays
  ``all``, because a consent already given is never relaxed.
- :func:`lift` — the opt-out ends. Meta's ``resume`` lifts Meta's; an
  operator may lift a stop word's or an operator's, with a reason, and never
  Meta's (only the person can: ``lifted_by_person_only``).
- :func:`blocks` — whether a send must not leave. Marketing (templates and
  broadcasts) is blocked by any active opt-out: the person decides. Anything
  else — the agent's replies, appointment and payment reminders, utility
  templates — is blocked only by an opt-out **the business** recorded
  (``source=operator``): the store decides who stops getting reminders, not
  the customer (owner's decision, QA 2026-10-30, INC-18). A pre-050 ``all``
  row from a stop word no longer blocks them.

The person is the customer row when there is one (``customer_id``), else the
phone Meta gave. A person known only by BSUID and not yet a customer cannot
be recorded: the webhook logs it, and the next message makes them one.
Callers hold the tenant-scoped session; nothing here crosses a tenant.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import AuditLog, Customer, WhatsAppOptOut

log = structlog.get_logger(__name__)

Scope = Literal["marketing", "all"]
Source = Literal["meta", "keyword", "operator"]


class OptOutLiftRefused(Exception):
    """``code`` is what the API answers (``lifted_by_person_only``…)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _digits(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = "".join(ch for ch in phone if ch.isdigit())
    return digits or None


def _person(customer_id: uuid.UUID | None, phone: str | None) -> list[sa.ColumnElement[bool]]:
    conditions: list[sa.ColumnElement[bool]] = []
    if customer_id is not None:
        conditions.append(WhatsAppOptOut.customer_id == customer_id)
    digits = _digits(phone)
    if digits:
        conditions.append(WhatsAppOptOut.recipient_phone.in_((digits, f"+{digits}")))
    return conditions


async def find_customer(
    session: AsyncSession, *, phone: str | None = None, bsuid: str | None = None
) -> Customer | None:
    """The customer Meta's identity points at, under the current tenant."""
    if bsuid:
        found = await session.scalar(sa.select(Customer).where(Customer.bsuid == bsuid).limit(1))
        if found is not None:
            return found
    digits = _digits(phone)
    if digits:
        by_phone: Customer | None = await session.scalar(
            sa.select(Customer)
            .where(sa.or_(Customer.phone == digits, Customer.identifier == digits))
            .limit(1)
        )
        return by_phone
    return None


async def record(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    channel_id: uuid.UUID,
    customer_id: uuid.UUID | None,
    phone: str | None,
    scope: Scope,
    source: Source,
    reason: str,
    actor: str,
    keyword: str | None = None,
    source_wamid: str | None = None,
) -> WhatsAppOptOut | None:
    """Record an opt-out. Idempotent: an active one for the same person is
    kept (and widened to ``all`` if that is asked); a lifted one for the same
    phone is reactivated, because the phone is unique per channel. Returns the
    row when something changed."""
    conditions = _person(customer_id, phone)
    if not conditions:
        log.info("opt_out.unknown_person", channel_id=str(channel_id), source=source)
        return None
    rows = (
        await session.scalars(
            sa.select(WhatsAppOptOut)
            .where(WhatsAppOptOut.channel_id == channel_id, sa.or_(*conditions))
            .order_by(WhatsAppOptOut.opted_in_at.is_(None).desc())
        )
    ).all()
    now = datetime.now(tz=UTC)
    active = next((r for r in rows if r.opted_in_at is None), None)
    if active is not None:
        changed = False
        if scope == "all" and active.scope != "all":
            active.scope = "all"
            changed = True
        if customer_id is not None and active.customer_id is None:
            active.customer_id = customer_id
            changed = True
        return active if changed else None
    row = next((r for r in rows if r.recipient_phone and r.recipient_phone == _digits(phone)), None)
    if row is None:
        row = WhatsAppOptOut(tenant_id=tenant_id, channel_id=channel_id)
        session.add(row)
    row.customer_id = customer_id or row.customer_id
    row.recipient_phone = _digits(phone) or row.recipient_phone
    row.scope = scope
    row.source = source
    row.reason = reason
    row.trigger_keyword = keyword
    row.source_wamid = source_wamid
    row.opted_out_at = now
    row.opted_in_at = None
    row.lifted_by = None
    await session.flush()
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor=actor,
            action="customer.opt_out.recorded",
            target=f"opt_out:{row.id}",
            after_json={
                "channel_id": str(channel_id),
                "customer_id": str(customer_id) if customer_id else None,
                "phone": row.recipient_phone,
                "scope": scope,
                "source": source,
            },
        )
    )
    log.info("opt_out.recorded", channel_id=str(channel_id), scope=scope, source=source)
    return row


async def lift(
    session: AsyncSession,
    row: WhatsAppOptOut,
    *,
    actor: str,
    by: Literal["meta", "operator"],
    reason: str | None = None,
) -> bool:
    """End one opt-out. Whether it was still active."""
    if row.opted_in_at is not None:
        return False
    if by == "operator":
        if row.source == "meta":
            # Meta's opt-out is the person's choice in WhatsApp: only their
            # «resume» in WhatsApp lifts it.
            raise OptOutLiftRefused("lifted_by_person_only")
        if not (reason or "").strip():
            raise OptOutLiftRefused("reason_required")
    row.opted_in_at = datetime.now(tz=UTC)
    row.lifted_by = actor[:255]
    session.add(
        AuditLog(
            tenant_id=row.tenant_id,
            actor=actor,
            action="customer.opt_out.lifted",
            target=f"opt_out:{row.id}",
            before_json={"scope": row.scope, "source": row.source},
            after_json={"by": by, "reason": (reason or "").strip() or None},
        )
    )
    await session.flush()
    log.info("opt_out.lifted", opt_out_id=str(row.id), by=by)
    return True


async def lift_from_meta(
    session: AsyncSession,
    *,
    channel_id: uuid.UUID,
    customer_id: uuid.UUID | None,
    phone: str | None,
) -> int:
    """Meta's ``resume``: the person wants marketing again. Lifts their
    marketing opt-outs (Meta's and their stop word's); an ``all`` one from
    before spec 050 stays, as it was not given through Meta."""
    conditions = _person(customer_id, phone)
    if not conditions:
        return 0
    rows = (
        await session.scalars(
            sa.select(WhatsAppOptOut).where(
                WhatsAppOptOut.channel_id == channel_id,
                WhatsAppOptOut.opted_in_at.is_(None),
                WhatsAppOptOut.scope == "marketing",
                sa.or_(*conditions),
            )
        )
    ).all()
    lifted = 0
    for row in rows:
        lifted += await lift(session, row, actor="meta", by="meta")
    return lifted


async def blocks(
    session: AsyncSession,
    *,
    channel_id: uuid.UUID | None,
    customer_id: uuid.UUID | None = None,
    phone: str | None = None,
    marketing: bool,
) -> bool:
    """Whether a send to this person must not leave. ``marketing`` is true
    for a marketing template or a broadcast; a reply, a reminder, a utility
    or an authentication template is not marketing, and only an opt-out the
    business recorded (``source=operator``) blocks it. ``channel_id=None``
    looks across every number of the business."""
    conditions = _person(customer_id, phone)
    if not conditions:
        return False
    query = sa.select(WhatsAppOptOut.id).where(
        WhatsAppOptOut.opted_in_at.is_(None), sa.or_(*conditions)
    )
    if channel_id is not None:
        query = query.where(WhatsAppOptOut.channel_id == channel_id)
    if not marketing:
        query = query.where(WhatsAppOptOut.source == "operator")
    return await session.scalar(query.limit(1)) is not None
