"""Cobranza due-date reminders — sent ON DEMAND, never autonomously.

Previously a background cron swept every tenant hourly and queued these
reminders on its own. That is gone: reminders now go out ONLY when a
business admin explicitly asks the agent for them (and confirms), via the
``billing.send_reminders`` MCP tool, which calls
``send_due_reminders_for_tenant`` for that one tenant. No timer, no
autonomous sends.

Per account (pending balance, not CANCELLED, with a phone and a due date):

    due in 3 days   → ``recordatorio_pago_proximo``
    due today       → ``recordatorio_pago_proximo``
    7 days overdue  → ``recordatorio_pago_vencido``

Guards, in order:
1. **Template approval** — the tenant's WABA must report the template as
   APPROVED (Meta rejects unapproved sends anyway).
2. **Opt-out** — a debtor who replied BAJA/STOP is skipped, on ANY of the
   business's numbers (see ``_queue_reminder``).
3. **Idempotency** — the queued message stores the account id + stage in
   ``template_payload``; a stage already sent for that account is never
   re-sent, so an admin can safely trigger the same run twice in a day.

Reminders are queued as pending template messages; the existing outbound
dispatcher delivers them (retries, wamid, status callbacks included).

Which number they leave from: the channel tagged ``role=notifications``. A
business with a single active WhatsApp line keeps the old behaviour (that line
is used, tagged or not). A business with two and no tag gets a refusal rather
than a guess — see :mod:`nexus_api.services.channel_routing`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

import sqlalchemy as sa
import structlog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Channel,
    Message,
    MessageDirection,
    MessageStatus,
    WhatsAppOptOut,
)
from nexus_api.services.channel_routing import (
    CHANNEL_ROLE_NOTIFICATIONS,
    ChannelResolutionError,
    describe_channel,
    resolve_whatsapp_channel,
)
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)

MAX_PAGES = 20

TEMPLATE_PROXIMO = "recordatorio_pago_proximo"
TEMPLATE_VENCIDO = "recordatorio_pago_vencido"
LANGUAGE = "es"

# (days until due, stage label, template). Negative = already overdue.
_STAGES: tuple[tuple[int, str, str], ...] = (
    (3, "T-3", TEMPLATE_PROXIMO),
    (0, "T0", TEMPLATE_PROXIMO),
    (-7, "T+7", TEMPLATE_VENCIDO),
)


async def send_due_reminders_for_tenant(
    tenant_id: uuid.UUID,
    tenant_name: str,
    *,
    today: date | None = None,
) -> dict[str, Any]:
    """Queue every due-date reminder for ONE business, right now.

    Called on demand from the ``billing.send_reminders`` tool after an admin
    asks for it. Returns a summary the agent can report back:

        {"status": "ok"|"no_connector"|"no_channel"|
                    "templates_not_approved"|"no_due_accounts",
         "queued": int,
         "recipients": [{"cliente", "stage", "monto", "fecha"}, ...]}

    Idempotency (account+stage already sent) means a repeat call the same day
    queues nothing new.
    """
    # Lazy import: keeps the MCP surface off this module's import path.
    from nexus_mcp.servers.amigable_cobro.tools import (
        AmigableCobroNotConfigured,
        _load_amigable_client,
    )

    sm = get_sessionmaker()
    try:
        client = await _load_amigable_client(tenant_id)
    except AmigableCobroNotConfigured:
        return {"status": "no_connector", "queued": 0, "recipients": []}

    async with sm() as session, tenant_scoped_session(session, tenant_id):
        try:
            channel = await resolve_whatsapp_channel(
                session,
                role=CHANNEL_ROLE_NOTIFICATIONS,
                provider="meta",
                purpose="cobranza_reminder",
            )
        except ChannelResolutionError as exc:
            # Reported back to the admin who asked for the run, verbatim.
            # "No channel" and "you have two numbers and neither is the
            # notifications line" need different fixes, so they must not
            # collapse into the same status.
            log.warning(
                "cobranza_reminder.channel_unresolved",
                tenant_id=str(tenant_id),
                reason=exc.reason,
                detail=str(exc),
            )
            return {
                "status": "no_channel" if exc.reason == "whatsapp_not_connected" else exc.reason,
                "queued": 0,
                "recipients": [],
                "detail": str(exc),
            }
        log.info(
            "cobranza_reminder.channel_resolved",
            tenant_id=str(tenant_id),
            **describe_channel(channel),
        )
        approved = await _approved_templates(session)
    if not approved:
        return {"status": "templates_not_approved", "queued": 0, "recipients": []}

    today = today or datetime.now(UTC).date()
    accounts = await _scan_accounts(client)
    recipients: list[dict[str, Any]] = []
    for raw in accounts:
        plan = _reminder_for(raw, today=today, approved=approved)
        if plan is None:
            continue
        stage, template_name, due = plan
        async with sm() as session, tenant_scoped_session(session, tenant_id):
            queued = await _queue_reminder(
                session,
                tenant_id=tenant_id,
                channel=channel,
                account=raw,
                stage=stage,
                template_name=template_name,
                due=due,
                business_name=tenant_name,
            )
            if queued is not None:
                await session.commit()
                recipients.append(queued)
    if recipients:
        log.info(
            "cobranza_reminder.queued",
            tenant_id=str(tenant_id),
            reminders=len(recipients),
        )
    return {
        "status": "ok" if recipients else "no_due_accounts",
        "queued": len(recipients),
        "recipients": recipients,
    }


async def _approved_templates(session: AsyncSession) -> set[str]:
    """Names of our reminder templates that Meta reports as APPROVED."""
    from nexus_api.services.whatsapp_templates import fetch_templates

    try:
        templates, _waba = await fetch_templates(session)
    except Exception as exc:  # connector/credentials hiccup — skip this tick
        log.warning("cobranza_reminder_cron.templates_unavailable", error=str(exc))
        return set()
    wanted = {TEMPLATE_PROXIMO, TEMPLATE_VENCIDO}
    return {
        t.name
        for t in templates
        if t.name in wanted
        and (t.status or "").upper() == "APPROVED"
        and (t.language or "").lower().startswith(LANGUAGE)
    }


async def _scan_accounts(client: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    page = 1
    while page <= MAX_PAGES:
        raw, meta = await client.list_cuentas(page=page)
        out.extend(r for r in raw if isinstance(r, dict))
        if page >= int(meta.get("last_page") or page):
            break
        page += 1
    return out


def _parse_due(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _reminder_for(
    account: dict[str, Any], *, today: date, approved: set[str]
) -> tuple[str, str, date] | None:
    """Return (stage, template_name, due_date) when this account is due for a
    reminder today, else None."""
    if str(account.get("status") or "").upper() == "CANCELLED":
        return None
    total = float(account.get("total_amount") or 0)
    paid = float(account.get("paid_amount") or 0)
    if round(total - paid, 2) <= 0:
        return None  # nothing owed
    if not str(account.get("client_phone") or "").strip():
        return None  # no phone on file — can't reach them
    due = _parse_due(account.get("due_date"))
    if due is None:
        return None
    delta = (due - today).days
    for want, stage, template_name in _STAGES:
        if delta == want and template_name in approved:
            return stage, template_name, due
    return None


def _fmt_amount(value: float) -> str:
    """Spanish formatting: 1668.5 -> ``$1.668,50`` (dot thousands, comma cents)."""
    whole, _, cents = f"{value:.2f}".partition(".")
    grouped = f"{int(whole):,}".replace(",", ".")
    return f"${grouped},{cents}"


async def _queue_reminder(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    channel: Channel,
    account: dict[str, Any],
    stage: str,
    template_name: str,
    due: date,
    business_name: str,
) -> dict[str, Any] | None:
    """Queue one reminder. Returns a summary dict, or None when skipped
    (no phone / opt-out / already sent)."""
    from nexus_channels.whatsapp_meta.phone import to_e164

    from nexus_worker.persistence.messages import (
        upsert_conversation_for_customer,
        upsert_customer,
    )

    account_id = str(account.get("id") or "")
    e164 = to_e164(str(account.get("client_phone") or ""))
    if not e164:
        return None
    # Meta's ``from`` format — must match what the inbound webhook stores or
    # customers/opt-outs fork per format.
    wa_identifier = e164.removeprefix("+")

    already = await session.scalar(
        sa.select(Message.id)
        .where(
            Message.tenant_id == tenant_id,
            Message.template_payload["cobranza_account"].astext == account_id,
            Message.template_payload["cobranza_stage"].astext == stage,
        )
        .limit(1)
    )
    if already is not None:
        return None

    # Opt-out is checked across EVERY channel of the tenant, not just the one
    # we are about to send from. The table is keyed per channel because that
    # is where the STOP arrived, but a debtor who said BAJA means "stop
    # chasing me", not "stop chasing me from this number". Once a business
    # runs two lines, the per-channel check would let a reminder through on
    # the second one — a compliance failure in a collections vertical, and
    # one nobody would notice until a debtor complained.
    #
    # RLS scopes the query to the tenant, so this is exactly "any active
    # opt-out this business holds for this phone".
    opted_out = await session.scalar(
        sa.select(WhatsAppOptOut.id).where(
            WhatsAppOptOut.recipient_phone == wa_identifier,
            WhatsAppOptOut.opted_in_at.is_(None),
        )
    )
    if opted_out is not None:
        log.info(
            "cobranza_reminder.skipped_opt_out",
            tenant_id=str(tenant_id),
            channel_id=str(channel.id),
            account=account_id,
            stage=stage,
        )
        return None

    total = float(account.get("total_amount") or 0)
    paid = float(account.get("paid_amount") or 0)
    variables = {
        "cliente": str(account.get("client_name") or "").strip() or "cliente",
        "negocio": business_name,
        "monto": _fmt_amount(round(total - paid, 2)),
        "fecha": due.strftime("%d/%m/%Y"),
    }

    customer = await upsert_customer(session, identifier=wa_identifier)
    conversation = await upsert_conversation_for_customer(
        session, channel_id=channel.id, customer_id=customer.id
    )
    session.add(
        Message(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            direction=MessageDirection.OUTBOUND,
            status=MessageStatus.PENDING,
            content=f"[template:{template_name}]",
            tool_calls=[],
            actor_kind="system",
            template_payload={
                "name": template_name,
                "language": LANGUAGE,
                "params": {"body": variables},
                # Idempotency markers (ignored by the dispatcher).
                "cobranza_account": account_id,
                "cobranza_stage": stage,
            },
        )
    )
    return {
        "cliente": variables["cliente"],
        "stage": stage,
        "monto": variables["monto"],
        "fecha": variables["fecha"],
    }
