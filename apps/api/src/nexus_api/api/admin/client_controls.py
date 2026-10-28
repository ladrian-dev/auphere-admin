"""Palancas de operador por cliente y las conciliaciones — spec 047, T172
(requisitos 54.6 y 54.9; ``contracts/admin-api.md`` §5).

- ``GET|PUT /admin/clients/{tenant_id}/sovereign`` ``{enabled, reason}``: la
  restricción soberana (solo proveedores europeos y pesos abiertos). El partner la
  ve como insignia y no la cambia; el router la lee (``model_lifecycle``,
  ``agent_quality``). Queda en la auditoría con la persona de Auphere y su motivo.
- ``GET /admin/reconciliations``: las diferencias del libro de las bolsas (el mismo
  cuadre que el cron diario, calculado al momento) y las de la conciliación de
  mensajes con Meta (``meta_reconciliation_runs`` con diferencia).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin.operator import operator_actor, require_operator
from nexus_api.api.deps import get_db_session
from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.core.security import require_admin_token
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AuditLog,
    Channel,
    ClientWallet,
    OperatorAccount,
    Partner,
    PartnerWallet,
    Tenant,
)
from nexus_api.db.models.business import BusinessProfile

router = APIRouter(dependencies=[Depends(require_admin_token)])


class SovereignIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    reason: str = Field(min_length=3, max_length=300)


async def _profile_flag(tenant_id: uuid.UUID) -> bool | None:
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        flag: bool | None = await session.scalar(
            sa.select(BusinessProfile.sovereign).where(BusinessProfile.tenant_id == tenant_id)
        )
    return flag


@router.get("/clients/{tenant_id}/sovereign")
async def get_sovereign(
    tenant_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
) -> dict[str, Any]:
    async with session.begin():
        if await session.get(Tenant, tenant_id) is None:
            raise HTTPException(status_code=404, detail={"code": "unknown_client"})
    flag = await _profile_flag(tenant_id)
    return {"tenant_id": str(tenant_id), "enabled": bool(flag), "has_profile": flag is not None}


@router.put("/clients/{tenant_id}/sovereign")
async def set_sovereign(
    tenant_id: uuid.UUID,
    body: SovereignIn,
    session: AsyncSession = Depends(get_db_session),
    operator: OperatorAccount = Depends(require_operator),
) -> dict[str, Any]:
    async with session.begin():
        if await session.get(Tenant, tenant_id) is None:
            raise HTTPException(status_code=404, detail={"code": "unknown_client"})
    actor = operator_actor(operator)
    async with get_sessionmaker()() as scoped, tenant_scoped_session(scoped, tenant_id):
        profile = await scoped.get(BusinessProfile, tenant_id)
        if profile is None:
            raise HTTPException(status_code=409, detail={"code": "no_business_profile"})
        before = profile.sovereign
        profile.sovereign = body.enabled
        scoped.add(
            AuditLog(
                tenant_id=tenant_id,
                actor=actor,
                action="client.sovereign_set",
                target=f"tenant:{tenant_id}",
                before_json={"sovereign": before},
                after_json={"sovereign": body.enabled, "reason": body.reason, "origin": "admin"},
            )
        )
    return {"tenant_id": str(tenant_id), "enabled": body.enabled}


@router.get("/reconciliations")
async def reconciliations(
    days: int = Query(default=7, ge=1, le=90), session: AsyncSession = Depends(get_db_session)
) -> dict[str, Any]:
    from nexus_api.db.models import MetaReconciliationRun
    from nexus_api.services.wallet.bags import as_client, bags_active
    from nexus_api.services.wallet.ledger import reconcile

    async with session.begin():
        partners = (
            await session.execute(
                sa.select(Partner.id, Partner.name).where(
                    Partner.console_v2_enabled_at.is_not(None)
                )
            )
        ).all()
        tenants = (
            await session.execute(sa.text("SELECT id, name FROM tenants ORDER BY name"))
        ).all()
    ledger: list[dict[str, Any]] = []
    names = {str(tid): name for tid, name in tenants}
    sm = get_sessionmaker()
    for partner_id, name in partners:
        async with sm() as scoped, scoped.begin():
            await apply_partner_to_session(scoped, partner_id)
            if not await bags_active(scoped, partner_id):
                continue
            result = await reconcile(scoped, partner_id)
            currency = await scoped.scalar(
                sa.select(PartnerWallet.currency).where(PartnerWallet.partner_id == partner_id)
            )
            bag_currency: dict[str, str] = {}
            for diff in result.differences:
                tenant = diff.get("tenant_id")
                if tenant:
                    # La bolsa es del cliente: su moneda, con su contexto puesto.
                    await as_client(scoped, uuid.UUID(str(tenant)))
                    found = await scoped.scalar(
                        sa.select(ClientWallet.currency).where(
                            ClientWallet.tenant_id == uuid.UUID(str(tenant))
                        )
                    )
                    bag_currency[str(tenant)] = str(found or "USD")
        for diff in result.differences:
            tenant = diff.get("tenant_id")
            ledger.append(
                {
                    "partner_id": str(partner_id),
                    "partner_name": name,
                    # Una bolsa va en su moneda; la cuenta, en la suya.
                    "currency": bag_currency.get(str(tenant), "USD")
                    if tenant
                    else str(currency or "USD"),
                    "tenant_name": names.get(str(tenant)) if tenant else None,
                    **diff,
                }
            )
    since = datetime.now(UTC).date() - timedelta(days=days)
    meta: list[dict[str, Any]] = []
    for tenant_id, tenant_name in tenants:
        async with sm() as scoped, tenant_scoped_session(scoped, tenant_id):
            for run in (
                await scoped.scalars(
                    sa.select(MetaReconciliationRun)
                    .where(MetaReconciliationRun.date >= since, MetaReconciliationRun.diff != 0)
                    .order_by(MetaReconciliationRun.date.desc())
                )
            ).all():
                channel = await scoped.get(Channel, run.channel_id)
                meta.append(
                    {
                        "tenant_id": str(tenant_id),
                        "tenant_name": tenant_name,
                        "channel_id": str(run.channel_id),
                        "identifier": channel.provider_identifier if channel else None,
                        "date": run.date.isoformat(),
                        "meta_count": run.meta_count,
                        "stored_count": run.stored_count,
                        "diff": run.diff,
                    }
                )
    return {"ledger": ledger, "meta": meta, "since": since.isoformat()}


__all__ = ["router"]
