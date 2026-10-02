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
import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

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
    WhatsAppTemplateStatus,
)
from nexus_api.metering.wallet import allocations_for, credit_burn, read_wallet
from nexus_api.services.console_home import (
    REVIEW_WINDOW,
    SnapshotResult,
    TenantSnapshot,
    tenant_snapshots,
)
from nexus_api.services.console_home_blocks import (
    ClientRow,
    attention_items,
    credit_block,
    days_until,
    portfolio_rows,
    review_block,
    spend_block,
    trend_block,
)
from nexus_api.services.console_reporting import (
    month_bounds,
    percent_of,
    project_month,
)
from nexus_api.services.usage_alerts import (
    channel_units_by_day,
    channel_units_month,
    evaluate_partner_usage_alerts,
)

from .schemas_home_usage import (
    AttentionItemOut,
    HomeAttentionOut,
    HomeClientsOut,
    HomeConversationsOut,
    HomeCreditOut,
    HomeIncidentsOut,
    HomeOut,
    HomePendingOut,
    HomeSpendOut,
    HomeToReviewOut,
    HomeTrendOut,
    HomeUsageOut,
    IncidentClientOut,
    PendingItemOut,
    PortfolioRowOut,
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
            by_day = await channel_units_by_day(session, tenant_ids, since, until)
            month_days = [since.date() + timedelta(days=i) for i in range((now - since).days + 1)]
            cap = principal.partner.usage_cap_messages_month
            usage = HomeUsageOut(
                units=units,
                daily=[by_day.get(d, 0.0) for d in month_days],
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
    snap: SnapshotResult | None = None
    quota: dict[uuid.UUID, bool] = {}
    if "clients:read" in perms or "conversations:read" in perms:
        # Spec 026: every client, not only the active ones — the portfolio
        # and «alta sin terminar» need them; the month figures below still
        # count active clients only.
        snap = await tenant_snapshots(tenant_ids, month_start=since, now=now)
        if snap.failed:
            errors.append("agents_with_incidents")
        conversations = HomeConversationsOut(
            count=sum(
                s.conversations_month for tid, s in snap.snapshots.items() if tid in active_ids
            ),
            since=since,
            until=until,
        )
        if "clients:read" in perms:
            # Spec 016 (R2.7): «sin cupo» is an incident. One ledger read for
            # the page, the same reading as the channel gate.
            from nexus_api.metering.wallet import quota_state

            quota = await quota_state(principal.partner.id, active_ids)
            refs: list[IncidentClientOut] = []
            for tid in active_ids:
                s = snap.snapshots.get(tid)
                issues = list(s.issues) if s is not None else []
                if quota.get(tid, True):
                    issues.append("out_of_quota")
                if not issues:
                    continue
                ref, name, _ = by_tenant[tid]
                refs.append(
                    IncidentClientOut(
                        external_client_ref=ref,
                        client_name=name,
                        issues=issues,
                        failed_messages_24h=s.failed_messages_24h if s is not None else 0,
                        href=f"/clients/{ref}",
                    )
                )
            incidents = HomeIncidentsOut(count=len(refs), refs=refs)

    # ── spec 026 blocks ────────────────────────────────────────────────
    client_rows = [ClientRow(tid, ref, name, st) for tid, (ref, name, st) in by_tenant.items()]
    today = now.date()
    attention: HomeAttentionOut | None = None
    to_review: HomeToReviewOut | None = None
    trend: HomeTrendOut | None = None
    credit: HomeCreditOut | None = None
    spend: HomeSpendOut | None = None
    portfolio: list[PortfolioRowOut] | None = None
    allocations: dict[uuid.UUID, tuple[int, int]] = {}
    if "clients:read" in perms or "usage:read" in perms:
        allocations = await allocations_for(principal.partner.id, tenant_ids)
    if snap is not None:
        try:
            snapshots = snap.snapshots
            rejected = await _templates_rejected(session, snapshots, now)
            if "clients:read" in perms:
                problems = attention_items(client_rows, snapshots, quota, rejected)
                with_problems = {
                    p.external_client_ref for p in problems if p.kind != "provisioning"
                }
                attention = HomeAttentionOut(
                    items=[AttentionItemOut.model_validate(asdict(p)) for p in problems],
                    clients_ok=sum(
                        1 for tid in active_ids if by_tenant[tid][0] not in with_problems
                    ),
                )
                portfolio = [
                    PortfolioRowOut.model_validate(asdict(r))
                    for r in portfolio_rows(client_rows, snapshots, allocations, problems, today)
                ]
            to_review = HomeToReviewOut.model_validate(asdict(review_block(client_rows, snapshots)))
            trend = HomeTrendOut.model_validate(asdict(trend_block(client_rows, snapshots, today)))
        except Exception as exc:
            log.warning("console_home.blocks_failed", error=str(exc))
            errors.append("attention")
    if "usage:read" in perms:
        burn: dict[uuid.UUID | None, int] = {}
        try:
            wallet = await read_wallet(principal.partner.id)
            burn = await credit_burn(principal.partner.id, tenant_ids, now - REVIEW_WINDOW)
            credit = HomeCreditOut.model_validate(
                asdict(
                    credit_block(
                        client_rows,
                        wallet.available if wallet is not None else None,
                        burn,
                        allocations,
                        days_until(until, now),
                    )
                )
            )
        except Exception as exc:
            log.warning("console_home.credit_failed", error=str(exc))
            errors.append("credit")
        try:
            # The same days of last month, so the change compares like with like.
            prev_start = (since - timedelta(days=1)).replace(day=1)
            month_burn = await credit_burn(principal.partner.id, tenant_ids, since)
            prev_burn = await credit_burn(
                principal.partner.id, tenant_ids, prev_start, prev_start + (now - since)
            )
            spend = HomeSpendOut.model_validate(
                asdict(
                    spend_block(
                        client_rows,
                        month_burn,
                        sum(prev_burn.values()),
                        daily_7d=sum(burn.values()) / REVIEW_WINDOW.days,
                        days_left=days_until(until, now),
                    )
                )
            )
        except Exception as exc:
            log.warning("console_home.spend_failed", error=str(exc))
            errors.append("spend")

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
        attention=attention,
        to_review=to_review,
        conversations_trend=trend,
        credit=credit,
        spend=spend,
        portfolio=portfolio,
        errors=errors,
        generated_in_ms=int((time.perf_counter() - started) * 1000),
    )


async def _templates_rejected(
    session: AsyncSession, snapshots: dict[uuid.UUID, TenantSnapshot], now: datetime
) -> dict[uuid.UUID, int]:
    """Spec 026 (D3): rejected templates of the last 7 days per client.

    The template mirror is keyed by WABA, not by tenant: the snapshots say
    which WABAs each client uses and ONE platform query reads the mirror.
    """
    by_waba: dict[str, list[uuid.UUID]] = {}
    for tid, s in snapshots.items():
        for waba in s.waba_ids:
            by_waba.setdefault(waba, []).append(tid)
    if not by_waba:
        return {}
    async with session.begin():
        rows = await session.execute(
            sa.select(WhatsAppTemplateStatus.waba_id, sa.func.count())
            .where(
                WhatsAppTemplateStatus.waba_id.in_(list(by_waba)),
                sa.func.lower(WhatsAppTemplateStatus.status) == "rejected",
                WhatsAppTemplateStatus.updated_at >= now - REVIEW_WINDOW,
            )
            .group_by(WhatsAppTemplateStatus.waba_id)
        )
    out: dict[uuid.UUID, int] = {}
    for waba, count in rows.all():
        for tid in by_waba.get(waba, []):
            out[tid] = out.get(tid, 0) + int(count)
    return out
