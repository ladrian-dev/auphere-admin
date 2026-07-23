"""Agent-sales poll — attributes paid WhatsApp WooCommerce orders.

The WhatsApp agent doesn't create the order: it sends a checkout link tagged
``wa=1``; WooCommerce creates the paid order later and stamps it with the
``_auphere_source=whatsapp`` meta (the store's own snippet). So the source of
truth is WooCommerce, and this cron is the bridge: it polls each tenant's
store for recently-changed orders, keeps the ones carrying the WhatsApp mark,
and upserts them into ``agent_sales`` with the commission owed.

Multi-tenant BY DESIGN: iterates every ACTIVE tenant with a connected
``woocommerce`` connector, so a new store needs no code change.

Safety properties:
- **Records only** — never bills. It just writes ``agent_sales`` rows; the
  monthly commission run (separate) reads them later.
- **Idempotent** — upsert on the ``(tenant_id, wc_order_id)`` unique key, so
  re-polling an order updates the same row (e.g. a refund flips its status
  and zeroes the commission) instead of duplicating it.
- **Amount faithful** — ``gross_amount`` is stored in the store's own
  currency (CLP…), NOT pre-converted. FX→USD is a later, auditable step.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import sqlalchemy as sa
import structlog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import AgentSale, Tenant, TenantStatus
from sqlalchemy.dialects.postgresql import insert as pg_insert

log = structlog.get_logger(__name__)

DEFAULT_TICK_SECONDS = 21600.0  # 6h; the upsert makes re-runs harmless
LOOKBACK_DAYS = 45  # re-scan a window so status changes (refunds) are caught
MAX_PAGES = 20
PER_PAGE = 100

# The WooCommerce order meta the store's checkout snippet stamps on a sale
# that came from the WhatsApp agent's ``wa=1`` link.
WA_META_KEY = "_auphere_source"
WA_META_VALUE = "whatsapp"
# WooCommerce statuses that mean the money was actually collected.
PAID_STATUSES = frozenset({"processing", "completed"})
# Facelad's cut. Configurable per tenant later via policies.commission.rate.
DEFAULT_COMMISSION_RATE = Decimal("0.025")


async def run_agent_sales_poll_cron(
    *, stop: asyncio.Event, tick_seconds: float = DEFAULT_TICK_SECONDS
) -> None:
    """Background task. Returns when ``stop`` is set."""
    log.info("agent_sales_poll_cron.start", tick_seconds=tick_seconds)
    sm = get_sessionmaker()
    while not stop.is_set():
        try:
            await _poll_all_tenants(sm)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("agent_sales_poll_cron.tick_failed", error=str(exc))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info("agent_sales_poll_cron.stopped")


async def _poll_all_tenants(sm: sa.orm.sessionmaker) -> None:  # type: ignore[type-arg]
    async with sm() as session:
        rows = await session.execute(
            sa.select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE)
        )
        tenant_ids = [r[0] for r in rows]
    for tenant_id in tenant_ids:
        try:
            await _poll_tenant(sm, tenant_id)
        except Exception as exc:
            log.warning(
                "agent_sales_poll_cron.tenant_failed",
                tenant_id=str(tenant_id),
                error=str(exc),
            )


async def _poll_tenant(
    sm: sa.orm.sessionmaker,  # type: ignore[type-arg]
    tenant_id: uuid.UUID,
) -> None:
    # Lazy import: keeps the MCP surface off this module's import path.
    from nexus_mcp.servers.woocommerce.tools import (
        WooCommerceNotConfigured,
        _load_woocommerce_client,
    )

    try:
        client = await _load_woocommerce_client(tenant_id)
    except WooCommerceNotConfigured:
        return  # tenant has no WooCommerce store — nothing to do

    after = (datetime.now(UTC) - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%dT%H:%M:%S")
    rate = DEFAULT_COMMISSION_RATE
    recorded = 0
    page = 1
    while page <= MAX_PAGES:
        orders, meta = await client.list_paginated(
            "/orders",
            page=page,
            per_page=PER_PAGE,
            extra_params={"modified_after": after, "orderby": "modified", "order": "desc"},
        )
        for order in orders:
            if not _is_whatsapp_order(order):
                continue
            row = _sale_row(order, tenant_id=tenant_id, rate=rate)
            if row is None:
                continue
            async with sm() as session, tenant_scoped_session(session, tenant_id):
                await _upsert_sale(session, row)
                await session.commit()
            recorded += 1
        if not meta.has_more:
            break
        page += 1
    if recorded:
        log.info(
            "agent_sales_poll_cron.recorded",
            tenant_id=str(tenant_id),
            orders=recorded,
        )


def _is_whatsapp_order(order: dict[str, Any]) -> bool:
    for m in order.get("meta_data") or []:
        if (
            isinstance(m, dict)
            and m.get("key") == WA_META_KEY
            and str(m.get("value")) == WA_META_VALUE
        ):
            return True
    return False


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _sale_row(
    order: dict[str, Any], *, tenant_id: uuid.UUID, rate: Decimal
) -> dict[str, Any] | None:
    wc_order_id = order.get("id")
    if not wc_order_id:
        return None
    status = str(order.get("status") or "").lower()
    currency = str(order.get("currency") or "").upper()[:3] or "CLP"
    try:
        gross = Decimal(str(order.get("total") or "0"))
    except (ValueError, ArithmeticError):
        gross = Decimal("0")
    # Commission only accrues on collected money; a refund/cancel re-poll
    # flips status here and zeroes the commission on the same row.
    is_paid = status in PAID_STATUSES
    commission = (
        (gross * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if is_paid
        else Decimal("0.00")
    )
    # Cash-on-delivery and local-pickup orders are collected off-gateway, so
    # WooCommerce never writes ``date_paid`` even once the money is in. The
    # monthly receipt buckets commissions by this date, so leaving it NULL
    # would silently drop those sales from billing forever. Fall back to when
    # the order was completed, else when it was created.
    paid_at = _parse_dt(order.get("date_paid_gmt") or order.get("date_paid"))
    if paid_at is None and is_paid:
        paid_at = _parse_dt(
            order.get("date_completed_gmt") or order.get("date_completed")
        ) or _parse_dt(order.get("date_created_gmt") or order.get("date_created"))

    billing = order.get("billing") or {}
    return {
        "tenant_id": tenant_id,
        "wc_order_id": int(wc_order_id),
        "currency": currency,
        "gross_amount": gross.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        "commission_rate": rate,
        "commission_amount": commission,
        "wc_status": status[:20],
        "date_paid": paid_at,
        "source_meta": {
            "number": order.get("number"),
            "billing_phone": billing.get("phone") if isinstance(billing, dict) else None,
        },
    }


async def _upsert_sale(session: Any, row: dict[str, Any]) -> None:
    stmt = pg_insert(AgentSale).values(**row)
    stmt = stmt.on_conflict_do_update(
        index_elements=["tenant_id", "wc_order_id"],
        set_={
            "currency": stmt.excluded.currency,
            "gross_amount": stmt.excluded.gross_amount,
            "commission_rate": stmt.excluded.commission_rate,
            "commission_amount": stmt.excluded.commission_amount,
            "wc_status": stmt.excluded.wc_status,
            "date_paid": stmt.excluded.date_paid,
            "source_meta": stmt.excluded.source_meta,
            "updated_at": sa.func.now(),
        },
    )
    await session.execute(stmt)
