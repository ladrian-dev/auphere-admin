"""``GET /console/home`` — the console's front page in ONE response (CP-08).

Before this endpoint the home page made three calls (``/me``, a 200-row
client list, ``/usage``) to show four figures. Now: five figures, one
call, each block guarded by the principal's permissions and isolated on
failure (a block that fails comes back ``null`` and its name is listed in
``errors``; the rest still render). Aggregations live in
``services/console_home.py``; the target — < 1 s p95 for a Facelad-sized
partner — is measured with ``scripts/dev_seed_console_volume.py``.

Also the cheap, synchronous evaluation of the usage alerts (CP-24): if
the partner has a cap, crossing 80 %/100 % is noticed the moment someone
opens the console, not only when the worker cron ticks.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.db.models import (
    ConsoleNotification,
    ConsoleNotificationRead,
    InvitationStatus,
    PartnerInvitation,
    PartnerTenant,
    Tenant,
    TenantStatus,
)
from nexus_api.services.console_home import tenant_snapshots
from nexus_api.services.console_reporting import (
    month_bounds,
    percent_of,
    project_month,
)
from nexus_api.services.usage_alerts import (
    channel_units_month,
    evaluate_partner_usage_alerts,
)

from .schemas_home_usage import (
    HomeClientsOut,
    HomeConversationsOut,
    HomeIncidentsOut,
    HomeOut,
    HomePendingOut,
    HomeUsageOut,
    IncidentClientOut,
    PendingItemOut,
)

log = structlog.get_logger(__name__)

router = APIRouter()


@router.get("/home", response_model=HomeOut)
async def home(
    principal: ConsolePrincipal = Depends(require_console_principal("partner:read")),
    session: AsyncSession = Depends(get_db_session),
) -> HomeOut:
    started = time.perf_counter()
    now = datetime.now(UTC)
    since, until, elapsed_days, days_in_month = month_bounds(now)
    perms = principal.permissions
    errors: list[str] = []

    # ── clients (platform tables, one query) ───────────────────────────
    async with session.begin():
        rows = (
            await session.execute(
                sa.select(
                    PartnerTenant.tenant_id,
                    PartnerTenant.external_client_ref,
                    PartnerTenant.client_name,
                    Tenant.status,
                )
                .join(Tenant, Tenant.id == PartnerTenant.tenant_id)
                .where(PartnerTenant.partner_id == principal.partner.id)
                .order_by(PartnerTenant.external_client_ref)
            )
        ).all()
    tenant_ids = [r[0] for r in rows]
    by_tenant = {r[0]: (r[1], r[2], r[3]) for r in rows}
    active_ids = [tid for tid, (_, _, st) in by_tenant.items() if st is TenantStatus.ACTIVE]

    clients: HomeClientsOut | None = None
    if "clients:read" in perms:
        clients = HomeClientsOut(
            active=len(active_ids),
            total=len(rows),
            provisioning=sum(
                1 for _, _, st in by_tenant.values() if st is TenantStatus.PROVISIONING
            ),
            paused=sum(1 for _, _, st in by_tenant.values() if st is TenantStatus.PAUSED),
        )

    # ── usage of the month (one reporting query) + alerts ──────────────
    usage: HomeUsageOut | None = None
    if "usage:read" in perms:
        try:
            units = await channel_units_month(session, tenant_ids, since, until)
            cap = principal.partner.usage_cap_messages_month
            usage = HomeUsageOut(
                units=units,
                cap=cap,
                percent=percent_of(units, cap),
                projected_month_units=project_month(units, elapsed_days, days_in_month),
                basis_days=elapsed_days,
            )
            if cap is not None and principal.partner.usage_alerts_enabled:
                try:
                    await evaluate_partner_usage_alerts(
                        session, principal.partner, used=units, now=now
                    )
                except Exception as exc:
                    log.warning("console_home.alerts_eval_failed", error=str(exc))
        except Exception as exc:
            log.warning("console_home.usage_failed", error=str(exc))
            errors.append("usage_units")

    # ── per-tenant snapshots: conversations + incidents ────────────────
    conversations: HomeConversationsOut | None = None
    incidents: HomeIncidentsOut | None = None
    if "clients:read" in perms or "conversations:read" in perms:
        snap = await tenant_snapshots(active_ids, month_start=since, now=now)
        if snap.failed:
            errors.append("agents_with_incidents")
        conversations = HomeConversationsOut(
            count=sum(s.conversations_month for s in snap.snapshots.values()),
            since=since,
            until=until,
        )
        if "clients:read" in perms:
            refs: list[IncidentClientOut] = []
            for tid in active_ids:
                s = snap.snapshots.get(tid)
                if s is None or not s.issues:
                    continue
                ref, name, _ = by_tenant[tid]
                refs.append(
                    IncidentClientOut(
                        external_client_ref=ref,
                        client_name=name,
                        issues=s.issues,
                        failed_messages_24h=s.failed_messages_24h,
                        href=f"/clients/{ref}",
                    )
                )
            incidents = HomeIncidentsOut(count=len(refs), refs=refs)

    # ── pending actions (platform tables) ──────────────────────────────
    pending: HomePendingOut | None = None
    try:
        items: list[PendingItemOut] = []
        if "clients:read" in perms:
            for _tid, (ref, name, st) in by_tenant.items():
                if st is TenantStatus.PROVISIONING:
                    items.append(
                        PendingItemOut(
                            kind="client_provisioning",
                            external_client_ref=ref,
                            client_name=name,
                            href=f"/clients/{ref}",
                        )
                    )
        async with session.begin():
            if "team:read" in perms:
                inv = await session.scalar(
                    sa.select(sa.func.count())
                    .select_from(PartnerInvitation)
                    .where(
                        PartnerInvitation.partner_id == principal.partner.id,
                        PartnerInvitation.status == InvitationStatus.PENDING.value,
                        PartnerInvitation.expires_at > now,
                    )
                )
                if inv:
                    items.append(
                        PendingItemOut(kind="invitations_pending", count=int(inv), href="/team")
                    )
            if "usage:read" in perms:
                read_by_me = (
                    sa.select(ConsoleNotificationRead.notification_id)
                    .where(ConsoleNotificationRead.user_id == principal.user_id)
                    .scalar_subquery()
                )
                unread = await session.scalar(
                    sa.select(sa.func.count())
                    .select_from(ConsoleNotification)
                    .where(
                        ConsoleNotification.partner_id == principal.partner.id,
                        ConsoleNotification.kind.like("usage.%"),
                        ConsoleNotification.read_at.is_(None),
                        sa.or_(
                            ConsoleNotification.recipient_user_id.is_(None),
                            ConsoleNotification.recipient_user_id == principal.user_id,
                        ),
                        ConsoleNotification.id.not_in(read_by_me),
                    )
                )
                if unread:
                    items.append(
                        PendingItemOut(
                            kind="usage_alerts_unread", count=int(unread), href="/usage/alerts"
                        )
                    )
        pending = HomePendingOut(count=sum(i.count for i in items), items=items)
    except Exception as exc:
        log.warning("console_home.pending_failed", error=str(exc))
        errors.append("pending_actions")

    return HomeOut(
        clients=clients,
        conversations_period=conversations,
        usage_units=usage,
        agents_with_incidents=incidents,
        pending_actions=pending,
        errors=errors,
        generated_in_ms=int((time.perf_counter() - started) * 1000),
    )
