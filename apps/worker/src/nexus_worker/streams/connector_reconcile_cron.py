"""Composio connector status auto-reconciliation cron.

Closes the known gap where an ``oauth_composio`` install stays ``pending``
forever because Composio's server-to-server webhook never landed (not
configured, transient miss, signature mismatch) — and the inverse, where
a token expired upstream but our row still says ``connected``.

Every tick this cron walks ACTIVE tenants, finds their ``oauth_composio``
installs in a reconcilable state and drives
:func:`nexus_api.services.connectors.service.reconcile_connector_status`
— the SAME idempotent path the operator's "Sincronizar" button uses, so
an ACTIVE upstream also fans out to tools sync + auto-enable.

Tick: 10 minutes by default. Composio's ``get_account`` is cheap and the
reconcile is a no-op when statuses already match, so the steady-state
cost is one GET per non-terminal install per tick.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid

import sqlalchemy as sa
import structlog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Connector,
    Tenant,
    TenantConnector,
    TenantConnectorStatus,
    TenantStatus,
)
from nexus_api.services.connectors.runtime import get_composio_client
from nexus_api.services.connectors.service import reconcile_connector_status

log = structlog.get_logger(__name__)

DEFAULT_TICK_SECONDS = 600.0
ACTOR = "system:connector_reconcile_cron"

# States worth polling. ``connected`` is included so an upstream EXPIRED
# flips us to needs_reauth without waiting for a failed tool call.
_RECONCILABLE = (
    TenantConnectorStatus.PENDING.value,
    TenantConnectorStatus.CONNECTED.value,
    TenantConnectorStatus.PARTIAL.value,
    TenantConnectorStatus.NEEDS_REAUTH.value,
)


async def run_connector_reconcile_cron(
    *,
    stop: asyncio.Event,
    tick_seconds: float = DEFAULT_TICK_SECONDS,
) -> None:
    """Background task. Returns when ``stop`` is set."""
    log.info("connector_reconcile.start", tick_seconds=tick_seconds)
    sm = get_sessionmaker()
    while not stop.is_set():
        try:
            tenant_ids = await _list_active_tenants(sm)
            for tid in tenant_ids:
                if stop.is_set():
                    break
                await _reconcile_tenant(sm, tid)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("connector_reconcile.tick_failed", error=str(exc))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info("connector_reconcile.stopped")


async def _list_active_tenants(sm: sa.orm.sessionmaker) -> list[uuid.UUID]:  # type: ignore[type-arg]
    async with sm() as session:
        rows = await session.execute(
            sa.select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE)
        )
        return [row[0] for row in rows]


async def _reconcile_tenant(
    sm: sa.orm.sessionmaker,  # type: ignore[type-arg]
    tenant_id: uuid.UUID,
) -> None:
    composio = get_composio_client()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        rows = await session.execute(
            sa.select(TenantConnector, Connector)
            .join(Connector, Connector.id == TenantConnector.connector_id)
            .where(
                Connector.auth_kind == "oauth_composio",
                TenantConnector.status.in_(_RECONCILABLE),
            )
        )
        for tenant_connector, connector in rows.all():
            try:
                result = await reconcile_connector_status(
                    session,
                    tenant_connector=tenant_connector,
                    connector=connector,
                    composio=composio,
                    actor=ACTOR,
                )
            except Exception as exc:
                log.warning(
                    "connector_reconcile.failed",
                    tenant_id=str(tenant_id),
                    connector=connector.slug,
                    error=str(exc)[:200],
                )
                continue
            if result is not None:
                log.info(
                    "connector_reconcile.applied",
                    tenant_id=str(tenant_id),
                    connector=connector.slug,
                    status=tenant_connector.status,
                )
        await session.commit()
