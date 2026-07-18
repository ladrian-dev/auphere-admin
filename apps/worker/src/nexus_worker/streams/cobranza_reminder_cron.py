"""Cobranza due-date sweep — automatic payment reminders.

Multi-tenant BY DESIGN: the sweep iterates every ACTIVE tenant that has a
connected ``amigable_cobro`` connector, so onboarding another business to
Amigable Cobro needs **no code change** — connect the connector, whitelist
its admins, approve the templates, and its debtors start getting reminders.

Per account (pending balance, not CANCELLED, with a phone and a due date):

    due in 3 days   → ``recordatorio_pago_proximo``
    due today       → ``recordatorio_pago_proximo``
    7 days overdue  → ``recordatorio_pago_vencido``

Guards, in order:
1. **Template approval** — the tenant's WABA must report the template as
   APPROVED (Meta rejects unapproved sends anyway). The sweep therefore
   stays idle until approval lands; no special "armed" flag needed.
2. **Opt-out** — a debtor who replied BAJA/STOP is skipped.
3. **Idempotency** — the queued message stores the account id + stage in
   ``template_payload``; a stage already sent for that account is never
   re-sent. No extra table required.

Reminders are queued as pending template messages; the existing outbound
dispatcher delivers them (retries, wamid, status callbacks included).
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, date, datetime
from typing import Any

import sqlalchemy as sa
import structlog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Channel,
    ChannelStatus,
    ChannelType,
    Message,
    MessageDirection,
    MessageStatus,
    Tenant,
    TenantStatus,
    WhatsAppOptOut,
)
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)

DEFAULT_TICK_SECONDS = 3600.0  # hourly tick; idempotency makes it send once
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


async def run_cobranza_reminder_cron(
    *, stop: asyncio.Event, tick_seconds: float = DEFAULT_TICK_SECONDS
) -> None:
    """Background task. Returns when ``stop`` is set."""
    log.info("cobranza_reminder_cron.start", tick_seconds=tick_seconds)
    sm = get_sessionmaker()
    while not stop.is_set():
        try:
            await _sweep_all_tenants(sm)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("cobranza_reminder_cron.tick_failed", error=str(exc))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info("cobranza_reminder_cron.stopped")


async def _sweep_all_tenants(sm: sa.orm.sessionmaker) -> None:  # type: ignore[type-arg]
    async with sm() as session:
        rows = await session.execute(
            sa.select(Tenant.id, Tenant.name).where(Tenant.status == TenantStatus.ACTIVE)
        )
        tenants = [(r[0], r[1]) for r in rows]
    for tenant_id, tenant_name in tenants:
        try:
            await _sweep_tenant(sm, tenant_id, tenant_name)
        except Exception as exc:
            log.warning(
                "cobranza_reminder_cron.tenant_failed",
                tenant_id=str(tenant_id),
                error=str(exc),
            )


async def _sweep_tenant(
    sm: sa.orm.sessionmaker,  # type: ignore[type-arg]
    tenant_id: uuid.UUID,
    tenant_name: str,
) -> None:
    """Scan one business's accounts and queue any due reminders."""
    # Lazy import: keeps the MCP surface off this module's import path.
    from nexus_mcp.servers.amigable_cobro.tools import (
        AmigableCobroNotConfigured,
        _load_amigable_client,
    )

    try:
        client = await _load_amigable_client(tenant_id)
    except AmigableCobroNotConfigured:
        return  # tenant doesn't use Amigable Cobro — nothing to do

    async with sm() as session, tenant_scoped_session(session, tenant_id):
        channel = await _active_whatsapp_channel(session)
        if channel is None:
            return
        approved = await _approved_templates(session)
    if not approved:
        return  # templates not approved yet — stay idle

    today = datetime.now(UTC).date()
    accounts = await _scan_accounts(client)
    queued = 0
    for raw in accounts:
        plan = _reminder_for(raw, today=today, approved=approved)
        if plan is None:
            continue
        stage, template_name, due = plan
        async with sm() as session, tenant_scoped_session(session, tenant_id):
            sent = await _queue_reminder(
                session,
                tenant_id=tenant_id,
                channel=channel,
                account=raw,
                stage=stage,
                template_name=template_name,
                due=due,
                business_name=tenant_name,
            )
            if sent:
                await session.commit()
                queued += 1
    if queued:
        log.info(
            "cobranza_reminder_cron.queued",
            tenant_id=str(tenant_id),
            reminders=queued,
        )


async def _active_whatsapp_channel(session: AsyncSession) -> Channel | None:
    return (
        await session.execute(
            sa.select(Channel)
            .where(
                Channel.type == ChannelType.WHATSAPP,
                Channel.provider == "meta",
                Channel.status == ChannelStatus.ACTIVE,
            )
            .limit(1)
        )
    ).scalar_one_or_none()


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
) -> bool:
    """Queue one reminder. Returns False when skipped (opt-out / already sent)."""
    from nexus_channels.whatsapp_meta.phone import to_e164

    from nexus_worker.persistence.messages import (
        upsert_conversation_for_customer,
        upsert_customer,
    )

    account_id = str(account.get("id") or "")
    e164 = to_e164(str(account.get("client_phone") or ""))
    if not e164:
        return False
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
        return False

    opted_out = await session.scalar(
        sa.select(WhatsAppOptOut.id).where(
            WhatsAppOptOut.channel_id == channel.id,
            WhatsAppOptOut.recipient_phone == wa_identifier,
            WhatsAppOptOut.opted_in_at.is_(None),
        )
    )
    if opted_out is not None:
        return False

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
    return True
