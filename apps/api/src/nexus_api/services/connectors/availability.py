"""Qué conectores puede usar el partner de un cliente — spec 060.

Una regla, una pregunta: **qué slugs no están disponibles para este cliente**.

- Cada conector tiene un valor por defecto para los partners
  (``connector_access_defaults``; sin fila, habilitado).
- Cada par conector y partner puede tener una decisión propia
  (``connector_partner_access``), que manda sobre el valor por defecto.
- Un cliente sin partner sigue el valor por defecto (requisito 1.4).
- Los canales y los conectores de sistema no entran (1.5, research D12).

La leen el turno (``activations.tool_policy``), las altas
(``ensure_connector_available``), el catálogo de la consola y los cargadores de
credenciales de los procesos programados. Las tablas no tienen RLS: el turno las
lee desde la sesión del cliente (research D3).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import (
    AgentConfig,
    AgentConfigStatus,
    AgentConnectorActivation,
    Connector,
    ConnectorAccessDefault,
    ConnectorPartnerAccess,
    Partner,
    PartnerTenant,
    Tenant,
    TenantConnector,
    TenantConnectorStatus,
    ToolCatalog,
)
from nexus_api.services.connectors.errors import ConnectorNotFound, not_found_message

#: Conectores que son canales: se gestionan en Canales y en las betas por partner,
#: no aquí. Son los seeds con ``provider_meta.channel_only`` (lo comprueba un test);
#: además se lee la marca de cada fila, por si mañana llega otro.
CHANNEL_CONNECTORS: Final = frozenset({"whatsapp_meta", "tiktok_bm"})

#: Conectores de sistema, que no son de ningún agente: Google Calendar lo conecta
#: cada profesional desde Reservas (spec 043). Es ``SYSTEM_ONLY_CONNECTORS`` de
#: ``service.py``; se repite aquí para no importar el servicio entero desde el turno.
SYSTEM_CONNECTORS: Final = frozenset({"googlecalendar"})

#: Estados de una conexión que todavía puede usarse o volver a usarse. Son los que
#: cuentan como «afectados» antes de quitar el acceso (requisito 4.1).
LIVE_STATUSES: Final = frozenset(
    {
        TenantConnectorStatus.CONNECTED.value,
        TenantConnectorStatus.PARTIAL.value,
        TenantConnectorStatus.NEEDS_REAUTH.value,
        TenantConnectorStatus.PAUSED.value,
    }
)


class ConnectorUnavailable(ConnectorNotFound):
    """El conector no está disponible para el partner de este cliente.

    Es un ``ConnectorNotFound`` con el mismo texto que un slug inexistente: todos
    los caminos que ya responden 404 a un conector desconocido responden igual
    a este, y no hay oráculo (requisitos 5.1 y 5.2)."""

    def __init__(self, slug: str) -> None:
        super().__init__(not_found_message(slug))
        self.slug = slug


def normalize(slug: str) -> str:
    return slug.strip().lower()


async def unmanaged_slugs(session: AsyncSession) -> frozenset[str]:
    """Canales y conectores de sistema: la regla no los toca nunca."""
    rows = await session.scalars(
        sa.select(Connector.slug).where(Connector.provider_meta["channel_only"].as_boolean())
    )
    return CHANNEL_CONNECTORS | SYSTEM_CONNECTORS | frozenset(rows.all())


def is_unmanaged(slug: str, unmanaged: frozenset[str]) -> bool:
    return normalize(slug) in unmanaged


async def partners_of(session: AsyncSession, tenant_id: uuid.UUID) -> frozenset[uuid.UUID]:
    """El partner de un cliente (research D4): ``tenants.partner_id`` y, si está
    vacío, sus vínculos en ``partner_tenants``. Un cliente creado desde el panel y
    vinculado después a un partner (``POST /admin/partners/{id}/tenants``) solo
    tiene el vínculo. Ninguna de las dos tablas tiene RLS: se leen igual dentro de
    la sesión del cliente. Vacío: cliente sin partner."""
    own = await session.scalar(sa.select(Tenant.partner_id).where(Tenant.id == tenant_id))
    if own is not None:
        return frozenset({own})
    linked = await session.scalars(
        sa.select(PartnerTenant.partner_id).where(PartnerTenant.tenant_id == tenant_id).distinct()
    )
    return frozenset(linked.all())


async def unavailable_slugs_for_partner(
    session: AsyncSession, partner_id: uuid.UUID | None
) -> frozenset[str]:
    """Los slugs no disponibles para los clientes de ``partner_id`` (``None``:
    clientes sin partner). Dos lecturas pequeñas y la fórmula de data-model.md."""
    defaults = {
        slug: enabled
        for slug, enabled in (
            await session.execute(
                sa.select(ConnectorAccessDefault.connector_slug, ConnectorAccessDefault.enabled)
            )
        ).all()
    }
    decisions: dict[str, bool] = {}
    if partner_id is not None:
        decisions = {
            slug: enabled
            for slug, enabled in (
                await session.execute(
                    sa.select(
                        ConnectorPartnerAccess.connector_slug, ConnectorPartnerAccess.enabled
                    ).where(ConnectorPartnerAccess.partner_id == partner_id)
                )
            ).all()
        }
    unavailable = {s for s, enabled in decisions.items() if not enabled}
    unavailable |= {s for s, enabled in defaults.items() if not enabled and s not in decisions}
    if not unavailable:
        return frozenset()
    return frozenset(unavailable) - await unmanaged_slugs(session)


async def unavailable_slugs_for_tenant(
    session: AsyncSession, tenant_id: uuid.UUID
) -> frozenset[str]:
    """Lo que no está disponible para este cliente. Un fallo de lectura se
    propaga: quien llama falla cerrado (requisito 5.8). Un cliente vinculado a
    más de un partner recibe lo más restrictivo: lo que alguno de ellos no puede usar."""
    partners = await partners_of(session, tenant_id)
    if not partners:
        return await unavailable_slugs_for_partner(session, None)
    out: frozenset[str] = frozenset()
    for partner_id in partners:
        out |= await unavailable_slugs_for_partner(session, partner_id)
    return out


async def ensure_connector_available(
    session: AsyncSession, tenant_id: uuid.UUID, slug: str
) -> None:
    """Para las altas (requisito 5.2): lanza ``ConnectorUnavailable`` si el
    partner del cliente no puede usar este conector."""
    if normalize(slug) in await unavailable_slugs_for_tenant(session, tenant_id):
        raise ConnectorUnavailable(normalize(slug))


# ── Lo que necesita el panel ───────────────────────────────────────────────


@dataclass(frozen=True)
class Decision:
    enabled: bool
    reason: str
    by: str
    at: object


@dataclass(frozen=True)
class AccessState:
    """El estado de un conector para un partner (o para los clientes sin partner)."""

    default_enabled: bool
    decision: Decision | None

    @property
    def effective(self) -> bool:
        return self.decision.enabled if self.decision is not None else self.default_enabled


async def defaults_by_slug(session: AsyncSession) -> dict[str, ConnectorAccessDefault]:
    rows = (await session.scalars(sa.select(ConnectorAccessDefault))).all()
    return {r.connector_slug: r for r in rows}


async def decisions_for_partner(
    session: AsyncSession, partner_id: uuid.UUID
) -> dict[str, ConnectorPartnerAccess]:
    rows = (
        await session.scalars(
            sa.select(ConnectorPartnerAccess).where(ConnectorPartnerAccess.partner_id == partner_id)
        )
    ).all()
    return {r.connector_slug: r for r in rows}


async def decisions_for_connector(
    session: AsyncSession, slug: str
) -> list[tuple[ConnectorPartnerAccess, Partner]]:
    rows = (
        await session.execute(
            sa.select(ConnectorPartnerAccess, Partner)
            .join(Partner, Partner.id == ConnectorPartnerAccess.partner_id)
            .where(ConnectorPartnerAccess.connector_slug == normalize(slug))
            .order_by(Partner.name)
        )
    ).all()
    return [(a, p) for a, p in rows]


def state_of(
    slug: str,
    defaults: dict[str, ConnectorAccessDefault],
    decisions: dict[str, ConnectorPartnerAccess],
) -> AccessState:
    d = defaults.get(slug)
    p = decisions.get(slug)
    return AccessState(
        default_enabled=True if d is None else d.enabled,
        decision=None
        if p is None
        else Decision(enabled=p.enabled, reason=p.reason, by=p.set_by, at=p.set_at),
    )


# ── Antes de quitar el acceso (requisito 4) ────────────────────────────────


@dataclass
class AffectedClient:
    tenant_id: uuid.UUID
    name: str
    connection_status: str
    agents: int


@dataclass
class AffectedPartner:
    partner_id: uuid.UUID | None
    partner_name: str | None
    clients: list[AffectedClient] = field(default_factory=list)


@dataclass
class Impact:
    partners: list[AffectedPartner]
    default_connector_of: list[tuple[uuid.UUID, str]]

    @property
    def clients(self) -> int:
        return sum(len(p.clients) for p in self.partners)

    @property
    def agents(self) -> int:
        return sum(c.agents for p in self.partners for c in p.clients)


async def impact_of_losing(
    session: AsyncSession,
    slug: str,
    *,
    partner_ids: set[uuid.UUID],
    include_partnerless: bool,
) -> Impact:
    """A quién afecta que ``slug`` deje de estar disponible para ``partner_ids``
    (y para los clientes sin partner, si ``include_partnerless``).

    Las conexiones están bajo RLS: se leen cliente a cliente, cada uno en su
    propia sesión, como ``/admin/connectors-installs``. Los partners cuyo
    conector por defecto es ``slug`` también salen (requisito 4.3).
    """
    from nexus_api.core.tenant_context import tenant_scoped_session
    from nexus_api.db.base import get_sessionmaker

    slug = normalize(slug)
    if not partner_ids and not include_partnerless:
        return Impact(partners=[], default_connector_of=[])
    # El partner efectivo de cada cliente, como en ``partners_of``: el propio o, si
    # está vacío, el del vínculo en ``partner_tenants``.
    linked = (
        sa.select(PartnerTenant.partner_id)
        .where(PartnerTenant.tenant_id == Tenant.id)
        .limit(1)
        .scalar_subquery()
    )
    effective = sa.func.coalesce(Tenant.partner_id, linked).label("effective_partner")
    conditions = []
    if partner_ids:
        conditions.append(effective.in_(partner_ids))
    if include_partnerless:
        conditions.append(effective.is_(None))
    tenants = (
        await session.execute(
            sa.select(Tenant.id, Tenant.name, effective, Partner.name)
            .outerjoin(Partner, Partner.id == effective)
            .where(sa.or_(*conditions))
            .order_by(Partner.name, Tenant.name)
        )
    ).all()
    default_of = (
        [
            (pid, name)
            for pid, name in (
                await session.execute(
                    sa.select(Partner.id, Partner.name).where(
                        Partner.id.in_(partner_ids),
                        sa.func.lower(Partner.default_connector_slug) == slug,
                    )
                )
            ).all()
        ]
        if partner_ids
        else []
    )

    # Las herramientas del conector (catálogo global), para contar también los
    # agentes que las nombran sin activación: fuera de la consola nueva las usan así.
    tool_names = frozenset(
        (
            await session.scalars(
                sa.select(ToolCatalog.name)
                .join(Connector, Connector.id == ToolCatalog.connector_id)
                .where(Connector.slug == slug)
            )
        ).all()
    )
    by_partner: dict[uuid.UUID | None, AffectedPartner] = {}
    sm = get_sessionmaker()
    for tenant_id, tenant_name, partner_id, partner_name in tenants:
        async with sm() as s, tenant_scoped_session(s, tenant_id):
            row = (
                await s.execute(
                    sa.select(TenantConnector.id, TenantConnector.status)
                    .join(Connector, Connector.id == TenantConnector.connector_id)
                    .where(
                        TenantConnector.tenant_id == tenant_id,
                        Connector.slug == slug,
                        TenantConnector.status.in_(LIVE_STATUSES),
                    )
                )
            ).first()
            if row is None:
                continue
            connection_id, status = row
            activated = set(
                (
                    await s.scalars(
                        sa.select(AgentConnectorActivation.agent_id).where(
                            AgentConnectorActivation.tenant_id == tenant_id,
                            AgentConnectorActivation.connector_id == connection_id,
                        )
                    )
                ).all()
            )
            naming = {
                agent_id
                for agent_id, tools in (
                    await s.execute(
                        sa.select(AgentConfig.agent_id, AgentConfig.tools).where(
                            AgentConfig.tenant_id == tenant_id,
                            AgentConfig.status == AgentConfigStatus.ACTIVE,
                        )
                    )
                ).all()
                if agent_id is not None and tool_names & set(tools or [])
            }
            agents = len(activated | naming)
        group = by_partner.setdefault(
            partner_id, AffectedPartner(partner_id=partner_id, partner_name=partner_name)
        )
        group.clients.append(
            AffectedClient(
                tenant_id=tenant_id,
                name=tenant_name,
                connection_status=str(getattr(status, "value", status)),
                agents=agents,
            )
        )
    return Impact(partners=list(by_partner.values()), default_connector_of=default_of)


__all__ = [
    "CHANNEL_CONNECTORS",
    "LIVE_STATUSES",
    "SYSTEM_CONNECTORS",
    "AccessState",
    "AffectedClient",
    "AffectedPartner",
    "ConnectorUnavailable",
    "Decision",
    "Impact",
    "decisions_for_connector",
    "decisions_for_partner",
    "defaults_by_slug",
    "ensure_connector_available",
    "impact_of_losing",
    "is_unmanaged",
    "normalize",
    "partners_of",
    "state_of",
    "unavailable_slugs_for_partner",
    "unavailable_slugs_for_tenant",
    "unmanaged_slugs",
]
