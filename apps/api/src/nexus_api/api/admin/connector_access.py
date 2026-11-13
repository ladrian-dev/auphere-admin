"""Admin — qué partners pueden usar cada conector (spec 060).

Dos vistas sobre los mismos datos (requisito 3.3):

- ``GET /admin/partners/{id}/connectors``: la ficha del partner.
- ``GET /admin/connectors/{slug}/access``: la ficha del conector.

Y dos escrituras:

- ``PUT /admin/connectors/{slug}/partners/{partner_id}``: la decisión de un partner.
- ``PUT /admin/connectors/{slug}/access/default``: el valor por defecto.

Quitar el acceso a clientes con el conector conectado pide ``confirm`` y, sin él,
responde ``409 confirm_required`` con los afectados, sin guardar nada. Si el
conector es el ``default_connector_slug`` de un partner que lo pierde, ``409
partner_default_connector`` aunque venga ``confirm`` (requisito 4). Contrato en
``specs/060-acceso-conectores-por-partner/contracts/admin-api.md``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin.operator import operator_actor, require_operator
from nexus_api.api.deps import get_db_session
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import (
    AuditLog,
    ConnectorAccessDefault,
    ConnectorPartnerAccess,
    OperatorAccount,
    Partner,
)
from nexus_api.services.connectors import availability
from nexus_api.services.connectors import catalog as connector_catalog
from nexus_api.services.connectors.composio_client import ComposioClientProtocol
from nexus_api.services.connectors.runtime import get_composio_client

router = APIRouter(dependencies=[Depends(require_admin_token)])

State = Literal["enabled", "disabled", "default"]
REASON_MIN = 3
REASON_MAX = 300


class PartnerRef(BaseModel):
    id: uuid.UUID
    name: str


class PartnerConnectorOut(BaseModel):
    slug: str
    display_name: str
    category: str
    auth_kind: str
    default_enabled: bool
    partner_state: State
    effective: bool
    connected_clients: int
    set_by: str | None = None
    set_at: datetime | None = None
    reason: str | None = None


class PartnerConnectorsOut(BaseModel):
    partner: PartnerRef
    items: list[PartnerConnectorOut]


class PartnerDecisionOut(BaseModel):
    partner_id: uuid.UUID
    name: str
    state: Literal["enabled", "disabled"]
    effective: bool
    connected_clients: int
    set_by: str
    set_at: datetime
    reason: str


class ConnectorAccessOut(BaseModel):
    slug: str
    default_enabled: bool
    default_reason: str | None = None
    default_updated_by: str | None = None
    default_updated_at: datetime | None = None
    partners: list[PartnerDecisionOut]
    partners_without_decision: int
    clients_without_partner_connected: int


class PartnerStateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: State
    reason: str = Field(default="", max_length=REASON_MAX)
    confirm: bool = False


class DefaultIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    reason: str = Field(default="", max_length=REASON_MAX)
    confirm: bool = False


# ── ayudas ─────────────────────────────────────────────────────────────────


def _reason(raw: str) -> str:
    reason = raw.strip()
    if len(reason) < REASON_MIN:
        raise HTTPException(status_code=422, detail={"code": "reason_required"})
    return reason


async def _managed_entry(
    session: AsyncSession, composio: ComposioClientProtocol, slug: str
) -> connector_catalog.CatalogConnector:
    slug = availability.normalize(slug)
    if slug in await availability.unmanaged_slugs(session):
        raise HTTPException(status_code=422, detail={"code": "connector_not_managed"})
    entry = await connector_catalog.get_catalog_entry(
        session, composio, slug, audience=connector_catalog.OPERATOR
    )
    if entry is None:
        raise HTTPException(status_code=404, detail={"code": "connector_not_found"})
    return entry


async def _partner(session: AsyncSession, partner_id: uuid.UUID) -> Partner:
    partner = await session.get(Partner, partner_id)
    if partner is None:
        raise HTTPException(status_code=404, detail={"code": "partner_not_found"})
    return partner


def _impact_payload(impact: availability.Impact) -> dict[str, object]:
    return {
        "code": "confirm_required",
        "affected": [
            {
                "partner_id": str(p.partner_id) if p.partner_id else None,
                "partner_name": p.partner_name,
                "clients": [
                    {
                        "tenant_id": str(c.tenant_id),
                        "name": c.name,
                        "connection_status": c.connection_status,
                        "agents": c.agents,
                    }
                    for c in p.clients
                ],
            }
            for p in impact.partners
        ],
        "totals": {"clients": impact.clients, "agents": impact.agents},
    }


async def _refuse_if_harmful(
    session: AsyncSession,
    slug: str,
    *,
    partner_ids: set[uuid.UUID],
    include_partnerless: bool,
    confirm: bool,
) -> JSONResponse | None:
    """Requisito 4: lo que pierde el acceso, antes de guardar."""
    async with session.begin():
        impact = await availability.impact_of_losing(
            session, slug, partner_ids=partner_ids, include_partnerless=include_partnerless
        )
    if impact.default_connector_of:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": {
                    "code": "partner_default_connector",
                    "partners": [
                        {"id": str(pid), "name": name} for pid, name in impact.default_connector_of
                    ],
                }
            },
        )
    if impact.clients and not confirm:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT, content={"detail": _impact_payload(impact)}
        )
    return None


async def _connected_clients(session: AsyncSession, slug: str, partner_id: uuid.UUID | None) -> int:
    async with session.begin():
        impact = await availability.impact_of_losing(
            session,
            slug,
            partner_ids={partner_id} if partner_id else set(),
            include_partnerless=partner_id is None,
        )
    return impact.clients


# ── vista por partner ──────────────────────────────────────────────────────


@router.get("/partners/{partner_id}/connectors", response_model=PartnerConnectorsOut)
async def partner_connectors(
    partner_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    composio: ComposioClientProtocol = Depends(get_composio_client),
) -> PartnerConnectorsOut:
    """Requisito 2.1: cada conector del catálogo con su estado para el partner."""
    async with session.begin():
        partner = await _partner(session, partner_id)
        entries = await connector_catalog.list_catalog(
            session, composio, audience=connector_catalog.OPERATOR
        )
        unmanaged = await availability.unmanaged_slugs(session)
        defaults = await availability.defaults_by_slug(session)
        decisions = await availability.decisions_for_partner(session, partner_id)
        partner_ref = PartnerRef(id=partner.id, name=partner.name)
    live = await _live_slugs_for_partner(session, partner_id)
    items: list[PartnerConnectorOut] = []
    for e in entries:
        if e.slug in unmanaged or e.status == "deprecated":
            continue
        st = availability.state_of(e.slug, defaults, decisions)
        d = decisions.get(e.slug)
        items.append(
            PartnerConnectorOut(
                slug=e.slug,
                display_name=e.display_name,
                category=e.category,
                auth_kind=e.auth_kind,
                default_enabled=st.default_enabled,
                partner_state="default"
                if st.decision is None
                else ("enabled" if st.decision.enabled else "disabled"),
                effective=st.effective,
                connected_clients=live.get(e.slug, 0),
                set_by=d.set_by if d else None,
                set_at=d.set_at if d else None,
                reason=d.reason if d else None,
            )
        )
    return PartnerConnectorsOut(partner=partner_ref, items=items)


async def _live_slugs_for_partner(session: AsyncSession, partner_id: uuid.UUID) -> dict[str, int]:
    """Cuántos clientes del partner tienen cada conector con una conexión viva."""
    from nexus_api.core.tenant_context import tenant_scoped_session
    from nexus_api.db.base import get_sessionmaker
    from nexus_api.db.models import Connector, PartnerTenant, Tenant, TenantConnector

    async with session.begin():
        # El partner efectivo, como en ``availability.partners_of``: el propio o el vínculo.
        linked = (
            sa.select(PartnerTenant.partner_id)
            .where(PartnerTenant.tenant_id == Tenant.id)
            .limit(1)
            .scalar_subquery()
        )
        tenant_ids = (
            await session.scalars(
                sa.select(Tenant.id).where(
                    sa.func.coalesce(Tenant.partner_id, linked) == partner_id
                )
            )
        ).all()
    counts: dict[str, int] = {}
    sm = get_sessionmaker()
    for tenant_id in tenant_ids:
        async with sm() as s, tenant_scoped_session(s, tenant_id):
            slugs = (
                await s.scalars(
                    sa.select(Connector.slug)
                    .join(TenantConnector, TenantConnector.connector_id == Connector.id)
                    .where(
                        TenantConnector.tenant_id == tenant_id,
                        TenantConnector.status.in_(availability.LIVE_STATUSES),
                    )
                )
            ).all()
        for slug in set(slugs):
            counts[slug] = counts.get(slug, 0) + 1
    return counts


@router.put(
    "/connectors/{slug}/partners/{partner_id}",
    response_model=PartnerConnectorOut,
    responses={409: {"description": "confirm_required | partner_default_connector"}},
)
async def set_partner_state(
    slug: str,
    partner_id: uuid.UUID,
    body: PartnerStateIn,
    operator: OperatorAccount = Depends(require_operator),
    session: AsyncSession = Depends(get_db_session),
    composio: ComposioClientProtocol = Depends(get_composio_client),
) -> PartnerConnectorOut | JSONResponse:
    """Requisitos 2.2, 2.3, 3.3 y 4: habilitar, deshabilitar o volver al valor por
    defecto para un partner. Las dos vistas del panel usan esta ruta."""
    reason = _reason(body.reason)
    async with session.begin():
        entry = await _managed_entry(session, composio, slug)
        partner = await _partner(session, partner_id)
        defaults = await availability.defaults_by_slug(session)
        decisions = await availability.decisions_for_partner(session, partner_id)
        before = availability.state_of(entry.slug, defaults, decisions)
    default_enabled = before.default_enabled
    after_enabled = default_enabled if body.state == "default" else body.state == "enabled"
    unchanged = (before.decision is None and body.state == "default") or (
        before.decision is not None
        and body.state != "default"
        and before.decision.enabled == (body.state == "enabled")
    )
    if not unchanged and before.effective and not after_enabled:
        refused = await _refuse_if_harmful(
            session,
            entry.slug,
            partner_ids={partner_id},
            include_partnerless=False,
            confirm=body.confirm,
        )
        if refused is not None:
            return refused
    async with session.begin():
        row = await session.get(ConnectorPartnerAccess, (entry.slug, partner_id))
        if not unchanged:
            if body.state == "default":
                if row is not None:
                    await session.delete(row)
            elif row is None:
                session.add(
                    ConnectorPartnerAccess(
                        connector_slug=entry.slug,
                        partner_id=partner_id,
                        enabled=after_enabled,
                        reason=reason,
                        set_by=operator_actor(operator),
                    )
                )
            else:
                row.enabled = after_enabled
                row.reason = reason
                row.set_by = operator_actor(operator)
                row.set_at = datetime.now(UTC)
            session.add(
                AuditLog(
                    tenant_id=None,
                    actor=operator_actor(operator),
                    action="connector_access.partner_changed",
                    target=f"connector:{entry.slug}/partner:{partner_id}",
                    before_json={
                        "enabled": None if before.decision is None else before.decision.enabled
                    },
                    after_json={
                        "enabled": None if body.state == "default" else after_enabled,
                        "reason": reason,
                    },
                )
            )
        await session.flush()
        decisions = await availability.decisions_for_partner(session, partner_id)
        st = availability.state_of(entry.slug, defaults, decisions)
        d = decisions.get(entry.slug)
    assert partner is not None
    return PartnerConnectorOut(
        slug=entry.slug,
        display_name=entry.display_name,
        category=entry.category,
        auth_kind=entry.auth_kind,
        default_enabled=st.default_enabled,
        partner_state="default" if d is None else ("enabled" if d.enabled else "disabled"),
        effective=st.effective,
        connected_clients=await _connected_clients(session, entry.slug, partner_id),
        set_by=d.set_by if d else None,
        set_at=d.set_at if d else None,
        reason=d.reason if d else None,
    )


# ── vista por conector ─────────────────────────────────────────────────────


@router.get("/connectors/{slug}/access", response_model=ConnectorAccessOut)
async def connector_access(
    slug: str,
    session: AsyncSession = Depends(get_db_session),
    composio: ComposioClientProtocol = Depends(get_composio_client),
) -> ConnectorAccessOut:
    """Requisito 3.1: el valor por defecto y los partners con decisión propia."""
    async with session.begin():
        entry = await _managed_entry(session, composio, slug)
        default = await session.get(ConnectorAccessDefault, entry.slug)
        decisions = await availability.decisions_for_connector(session, entry.slug)
        total_partners = await session.scalar(sa.select(sa.func.count()).select_from(Partner))
    partners = [
        PartnerDecisionOut(
            partner_id=p.id,
            name=p.name,
            state="enabled" if a.enabled else "disabled",
            effective=a.enabled,
            connected_clients=await _connected_clients(session, entry.slug, p.id),
            set_by=a.set_by,
            set_at=a.set_at,
            reason=a.reason,
        )
        for a, p in decisions
    ]
    return ConnectorAccessOut(
        slug=entry.slug,
        default_enabled=True if default is None else default.enabled,
        default_reason=default.reason if default else None,
        default_updated_by=default.updated_by if default else None,
        default_updated_at=default.updated_at if default else None,
        partners=partners,
        partners_without_decision=int(total_partners or 0) - len(partners),
        clients_without_partner_connected=await _connected_clients(session, entry.slug, None),
    )


@router.put(
    "/connectors/{slug}/access/default",
    response_model=ConnectorAccessOut,
    responses={409: {"description": "confirm_required | partner_default_connector"}},
)
async def set_default(
    slug: str,
    body: DefaultIn,
    operator: OperatorAccount = Depends(require_operator),
    session: AsyncSession = Depends(get_db_session),
    composio: ComposioClientProtocol = Depends(get_composio_client),
) -> ConnectorAccessOut | JSONResponse:
    """Requisitos 3.2 y 4.1: pasar el valor por defecto a «deshabilitado» afecta a
    todo partner sin decisión propia y a los clientes sin partner."""
    reason = _reason(body.reason)
    async with session.begin():
        entry = await _managed_entry(session, composio, slug)
        row = await session.get(ConnectorAccessDefault, entry.slug)
        before = True if row is None else row.enabled
        decided = {
            a.partner_id
            for a, _p in await availability.decisions_for_connector(session, entry.slug)
        }
        undecided = set(
            (await session.scalars(sa.select(Partner.id).where(Partner.id.notin_(decided)))).all()
            if decided
            else (await session.scalars(sa.select(Partner.id))).all()
        )
    if before == body.enabled:
        return await connector_access(entry.slug, session, composio)
    if not body.enabled:
        refused = await _refuse_if_harmful(
            session,
            entry.slug,
            partner_ids=undecided,
            include_partnerless=True,
            confirm=body.confirm,
        )
        if refused is not None:
            return refused
    async with session.begin():
        row = await session.get(ConnectorAccessDefault, entry.slug)
        if row is None:
            session.add(
                ConnectorAccessDefault(
                    connector_slug=entry.slug,
                    enabled=body.enabled,
                    reason=reason,
                    updated_by=operator_actor(operator),
                )
            )
        else:
            row.enabled = body.enabled
            row.reason = reason
            row.updated_by = operator_actor(operator)
            row.updated_at = datetime.now(UTC)
        session.add(
            AuditLog(
                tenant_id=None,
                actor=operator_actor(operator),
                action="connector_access.default_changed",
                target=f"connector:{entry.slug}",
                before_json={"enabled": before},
                after_json={"enabled": body.enabled, "reason": reason},
            )
        )
    return await connector_access(entry.slug, session, composio)


__all__ = ["router"]
