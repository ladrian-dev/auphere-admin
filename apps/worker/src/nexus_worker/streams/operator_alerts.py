"""Operator alerter — turns audit_log events into operator WhatsApp templates.

Five events trigger an alert in Phase 1:

- ``conversation.escalated`` — written by ``escalate.escalate_to_human``
  (block D). Template: ``alert_escalation_v1``.
- ``integration.agendapro.needs_reauth`` — written by the AgendaPro
  health-check service when re-login fails (block E + H cron).
  Template: ``alert_needs_reauth_v1``.
- ``cost.daily_threshold_exceeded`` — written by the cost rollup cron
  (block H) when ``messages.cost_usd`` for today crosses the tenant's
  ``cost_alert_threshold_usd_per_day``. Template: ``alert_cost_threshold_v1``.
- ``isolation.violation_detected`` — written by the isolation watcher
  (block H) when an ``isolation_events`` row lands for any of the 7 P1
  metrics. Template: ``alert_isolation_v1``.
- ``channel.whatsapp_5xx_burst`` — written by the outbound dispatcher's
  burst tracker (block H) when provider 5xx errors >= 5 within 2min.
  Template: ``alert_whatsapp_burst_v1``.

The :mod:`nexus_api.db.models.operator_notification` table is the
deduplication ledger — we INSERT a row keyed on ``audit_log_id`` BEFORE
sending the WhatsApp, so a crash mid-call still leaves the marker that
prevents the next tick from double-notifying.

Recipient resolution:
1. ``tenants.owner_phone`` if set.
2. ``settings.operator_fallback_phone`` (env) — Phase 1 default = Lee.
3. If neither: log + skip + status='failed' with error=no_recipient.

Tenant_id is derived from the audit_log row, NEVER from a caller arg.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

import sqlalchemy as sa
import structlog
from nexus_api.config import get_settings
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AuditLog,
    Customer,
    OperatorNotification,
    OperatorNotificationStatus,
    Tenant,
    TenantStatus,
)
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)

DEFAULT_TICK_SECONDS = 30.0

# Provider → ChannelAdapter, shared with the outbound dispatcher. The alerter
# resolves the adapter from the tenant's active WhatsApp channel provider so
# operator alerts go out through the same WABA the tenant is served on.
AdapterRegistry = Mapping[str, Any]


_ACTION_TO_TEMPLATE: dict[str, str] = {
    "conversation.escalated": "alert_escalation_v1",
    "integration.agendapro.needs_reauth": "alert_needs_reauth_v1",
    "cost.daily_threshold_exceeded": "alert_cost_threshold_v1",
    "isolation.violation_detected": "alert_isolation_v1",
    "channel.whatsapp_5xx_burst": "alert_whatsapp_burst_v1",
    # Block L — Connectors module. Both map to the existing needs_reauth
    # template (same operational signal: "go to the panel and reconnect"),
    # avoiding a new Meta template approval round-trip.
    "connector.needs_reauth": "alert_needs_reauth_v1",
    "connector.error": "alert_needs_reauth_v1",
}


async def run_operator_alerter(
    *,
    adapters: AdapterRegistry,
    stop: asyncio.Event,
    tick_seconds: float = DEFAULT_TICK_SECONDS,
) -> None:
    """Background task. One pass per ``tick_seconds``."""
    log.info("operator_alerter.start", tick_seconds=tick_seconds, providers=sorted(adapters.keys()))
    sm = get_sessionmaker()
    while not stop.is_set():
        try:
            await _process_pending(sm, adapters)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("operator_alerter.tick_failed", error=str(exc))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info("operator_alerter.stopped")


async def _process_pending(
    sm: sa.orm.sessionmaker,  # type: ignore[type-arg]
    adapters: AdapterRegistry,
) -> None:
    """One iteration: find unprocessed audit rows, alert, ledger them."""
    async with sm() as session:
        tenant_ids_result = await session.execute(
            sa.select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE)
        )
        tenant_ids = [r[0] for r in tenant_ids_result]

    for tid in tenant_ids:
        async with sm() as session, tenant_scoped_session(session, tid):
            await _process_tenant(session, tid, adapters)


async def _process_tenant(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    adapters: AdapterRegistry,
) -> None:
    """Find audit rows of interest that don't yet have a notification ledger."""
    actions = list(_ACTION_TO_TEMPLATE.keys())
    candidates = await session.execute(
        sa.select(AuditLog)
        .outerjoin(
            OperatorNotification,
            OperatorNotification.audit_log_id == AuditLog.id,
        )
        .where(
            AuditLog.action.in_(actions),
            OperatorNotification.id.is_(None),
        )
        .order_by(AuditLog.created_at.asc())
        .limit(20)
    )
    rows = list(candidates.scalars())
    if not rows:
        return
    log.info(
        "operator_alerter.batch",
        tenant_id=str(tenant_id),
        count=len(rows),
    )
    for audit_row in rows:
        await _alert_one(session, audit_row, adapters, tenant_id)


async def _alert_one(
    session: AsyncSession,
    audit_row: AuditLog,
    adapters: AdapterRegistry,
    tenant_id: uuid.UUID,
) -> None:
    template = _ACTION_TO_TEMPLATE[audit_row.action]
    # Insert ledger row FIRST. UNIQUE(audit_log_id) makes this idempotent
    # across worker replicas (only one will succeed; the loser's exception
    # is logged and the audit row is treated as already-processed next tick).
    notif = OperatorNotification(
        tenant_id=tenant_id,
        audit_log_id=audit_row.id,
        template_name=template,
        status=OperatorNotificationStatus.PENDING,
    )
    session.add(notif)
    try:
        await session.flush()
    except sa.exc.IntegrityError:
        await session.rollback()
        log.info(
            "operator_alerter.duplicate_skipped",
            tenant_id=str(tenant_id),
            audit_log_id=str(audit_row.id),
        )
        return

    recipient_phone, owner_business_phone, provider = await _resolve_recipient_and_business_phone(
        session, tenant_id
    )
    if recipient_phone is None:
        notif.status = OperatorNotificationStatus.FAILED
        notif.last_error = "no_recipient_configured"
        log.warning(
            "operator_alerter.no_recipient",
            tenant_id=str(tenant_id),
            audit_log_id=str(audit_row.id),
        )
        return
    if owner_business_phone is None or provider is None:
        notif.status = OperatorNotificationStatus.FAILED
        notif.last_error = "no_whatsapp_channel_for_tenant"
        log.warning(
            "operator_alerter.no_channel",
            tenant_id=str(tenant_id),
            audit_log_id=str(audit_row.id),
        )
        return

    adapter = adapters.get(provider)
    if adapter is None:
        notif.status = OperatorNotificationStatus.FAILED
        notif.last_error = f"no adapter for provider: {provider}"
        log.warning(
            "operator_alerter.unsupported_provider",
            tenant_id=str(tenant_id),
            audit_log_id=str(audit_row.id),
            provider=provider,
        )
        return

    body_params = await _render_params(session, audit_row, template)
    try:
        await _send_alert_template(
            adapter=adapter,
            provider=provider,
            from_phone=owner_business_phone,
            recipient=recipient_phone,
            template=template,
            body_params=body_params,
            tenant_id=tenant_id,
        )
    except Exception as exc:
        notif.status = OperatorNotificationStatus.FAILED
        notif.attempts += 1
        notif.last_error = f"{type(exc).__name__}: {exc}"[:500]
        log.warning(
            "operator_alerter.send_failed",
            tenant_id=str(tenant_id),
            audit_log_id=str(audit_row.id),
            template=template,
            error=notif.last_error,
        )
        return
    notif.status = OperatorNotificationStatus.SENT
    notif.sent_at = datetime.now(UTC)
    log.info(
        "operator_alerter.sent",
        tenant_id=str(tenant_id),
        audit_log_id=str(audit_row.id),
        template=template,
    )


async def _resolve_recipient_and_business_phone(
    session: AsyncSession,
    tenant_id: uuid.UUID,
) -> tuple[str | None, str | None, str | None]:
    """Return (recipient_e164, owner_whatsapp_business_phone, provider).

    Recipient = tenant.owner_phone || settings.operator_fallback_phone.
    Business phone + provider = first active WhatsApp channel of this tenant.
    The provider drives which adapter sends the alert.
    """
    settings = get_settings()
    tenant_row = await session.execute(sa.select(Tenant.owner_phone).where(Tenant.id == tenant_id))
    owner_phone = tenant_row.scalar_one_or_none()
    recipient = owner_phone or settings.operator_fallback_phone or None

    from nexus_api.db.models import Channel, ChannelStatus

    channel_row = await session.execute(
        sa.select(Channel.provider_identifier, Channel.provider)
        .where(
            Channel.type == "whatsapp",
            Channel.status == ChannelStatus.ACTIVE,
        )
        .order_by(Channel.created_at.asc())
        .limit(1)
    )
    row = channel_row.first()
    if row is None:
        return recipient, None, None
    business_phone, provider = row
    return recipient, business_phone, provider


async def _send_alert_template(
    *,
    adapter: Any,
    provider: str,
    from_phone: str,
    recipient: str,
    template: str,
    body_params: list[str],
    tenant_id: uuid.UUID,
) -> None:
    """Send an operator alert template via the resolved adapter.

    Meta's ``send_template`` takes a single ``params`` dict; its
    ``_build_template_components`` reads ``body`` as a positional list.
    The ``channel_id`` is a placeholder because the adapter only logs it.
    """
    await adapter.send_template(
        from_phone=from_phone,
        recipient=recipient,
        template_name=template,
        language="es_CL",
        tenant_id=tenant_id,
        channel_id=uuid.uuid4(),  # placeholder — adapter only logs
        params={"body": body_params},
    )


async def _render_params(
    session: AsyncSession,
    audit_row: AuditLog,
    template: str,
) -> list[str]:
    """Return template body params in declared order. Pulls customer name
    from the KG when needed."""
    after = cast(dict[str, Any] | None, audit_row.after_json) or {}
    if template == "alert_escalation_v1":
        customer_label = "cliente"
        customer_id = after.get("customer_id")
        if customer_id:
            try:
                cust_row = await session.execute(
                    sa.select(Customer.name, Customer.identifier).where(
                        Customer.id == uuid.UUID(str(customer_id))
                    )
                )
                cust = cust_row.first()
                if cust:
                    customer_label = cust[0] or cust[1] or "cliente"
            except (ValueError, TypeError):
                pass
        reason = str(after.get("reason") or "sin motivo informado")
        return [customer_label, reason]
    if template == "alert_needs_reauth_v1":
        return []
    if template == "alert_cost_threshold_v1":
        total = after.get("cost_usd_total") or "0"
        threshold = after.get("threshold_usd") or "0"
        amount_label = f"USD {total} / umbral USD {threshold}"
        return [amount_label]
    if template == "alert_isolation_v1":
        metric = str(after.get("metric") or "isolation.unknown")
        count = str(after.get("count") or after.get("count_24h") or "1")
        return [metric, count]
    if template == "alert_whatsapp_burst_v1":
        count = str(after.get("threshold") or "5")
        return [count]
    return []
