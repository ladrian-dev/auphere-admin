"""Autorizar una vez por cliente, activar por agente — spec 047, T128 (requisitos
35 y 36; ``data-model.md`` §5, research D13).

- **La conexión** es del cliente (``tenant_connectors``): una por servicio, con su
  cuenta y sus credenciales. **La activación** es del agente
  (``agent_connector_activations``), con su permiso y sus ajustes.
- **El turno** construye las herramientas con la intersección: la lista del agente
  (su techo) y lo que deja su activación (``tool_policy``):
  - sin activación, ninguna herramienta de esa conexión (35.6, garantías 2 y 9);
  - «Solo leer» (``read``): solo las de lectura;
  - «Preguntar antes de escribir» (``ask_before_write``): las de escritura piden
    aprobación durable antes de ejecutarse (``tool_approvals``);
  - «Leer y escribir» (``read_write``): todas.
  La regla manda en los clientes de la consola nueva y en toda conexión que ya
  tenga alguna activación; las conexiones de antes sin ninguna (la API de
  partners, el admin) siguen como hoy hasta que la 0194 o la consola las activen.
- **Los ajustes** se declaran en el catálogo (``connectors.settings_schema``) y se
  validan con JSON Schema (36.2).
- **Quitar** una activación dice qué habilidades del agente se quedan sin ella
  (35.7). **Desconectar para todos** lista los agentes y las habilidades afectadas
  y pide confirmación (36.4).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Final, Literal

import sqlalchemy as sa
from jsonschema import Draft202012Validator
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import (
    Agent,
    AgentConfig,
    AgentConfigStatus,
    AgentConnectorActivation,
    AuditLog,
    Connector,
    TenantConnector,
    TenantConnectorStatus,
    ToolCatalog,
)

Permission = Literal["read", "ask_before_write", "read_write"]
PERMISSIONS: Final = ("read", "ask_before_write", "read_write")
#: Una conexión con la que se puede trabajar ahora mismo.
LIVE: Final = frozenset(
    {TenantConnectorStatus.CONNECTED.value, TenantConnectorStatus.PARTIAL.value}
)


class ActivationError(Exception):
    def __init__(self, code: str, status: int = 409, **extra: Any) -> None:
        super().__init__(code)
        self.code = code
        self.status = status
        self.extra = extra


@dataclass(frozen=True)
class ToolPolicy:
    """Lo que la activación quita y lo que pide aprobar, por nombre de herramienta."""

    blocked: frozenset[str] = frozenset()
    needs_approval: frozenset[str] = frozenset()


@dataclass
class AffectedSkills:
    skills: list[str] = field(default_factory=list)
    procedures: list[str] = field(default_factory=list)


# ── el turno ───────────────────────────────────────────────────────────────


async def tool_policy(
    session: AsyncSession, tenant_id: uuid.UUID, agent_id: uuid.UUID | None
) -> ToolPolicy:
    """La política de herramientas de conectores para el turno de ``agent_id``.
    Dentro de la sesión del cliente."""
    from nexus_api.services.channel_config import partner_on_v2

    rows = (
        await session.execute(
            sa.select(ToolCatalog.name, ToolCatalog.read_only, TenantConnector.id)
            .join(Connector, Connector.id == ToolCatalog.connector_id)
            .join(
                TenantConnector,
                sa.and_(
                    TenantConnector.connector_id == Connector.id,
                    TenantConnector.tenant_id == tenant_id,
                ),
            )
        )
    ).all()
    if not rows:
        return ToolPolicy()
    activations: dict[uuid.UUID, str] = {}
    if agent_id is not None:
        for connection_id, permission in (
            await session.execute(
                sa.select(
                    AgentConnectorActivation.connector_id, AgentConnectorActivation.permission
                ).where(
                    AgentConnectorActivation.tenant_id == tenant_id,
                    AgentConnectorActivation.agent_id == agent_id,
                )
            )
        ).all():
            activations[connection_id] = permission
    managed = set(
        (
            await session.scalars(
                sa.select(AgentConnectorActivation.connector_id)
                .where(AgentConnectorActivation.tenant_id == tenant_id)
                .distinct()
            )
        ).all()
    )
    strict = await partner_on_v2(session, tenant_id)
    blocked: set[str] = set()
    approval: set[str] = set()
    for name, read_only, connection_id in rows:
        if not (strict or connection_id in managed):
            continue
        permission = activations.get(connection_id)
        if permission is None or (permission == "read" and not read_only):
            blocked.add(name)
        elif permission == "ask_before_write" and not read_only:
            approval.add(name)
    return ToolPolicy(blocked=frozenset(blocked), needs_approval=frozenset(approval))


# ── la consola ─────────────────────────────────────────────────────────────


async def connection_of(
    session: AsyncSession, tenant_id: uuid.UUID, slug: str
) -> tuple[Connector, TenantConnector | None]:
    connector = await session.scalar(sa.select(Connector).where(Connector.slug == slug))
    if connector is None:
        raise ActivationError("unknown_integration", 404)
    install = await session.scalar(
        sa.select(TenantConnector).where(
            TenantConnector.tenant_id == tenant_id, TenantConnector.connector_id == connector.id
        )
    )
    return connector, install


def validate_settings(schema: dict[str, Any] | None, settings: dict[str, Any]) -> None:
    """Los ajustes, contra el esquema del catálogo (36.2). Sin esquema, nada."""
    if not settings:
        return
    if not schema:
        raise ActivationError("settings_not_supported", 422)
    errors = sorted(Draft202012Validator(schema).iter_errors(settings), key=lambda e: list(e.path))
    if errors:
        raise ActivationError(
            "invalid_settings",
            422,
            errors=[
                {"field": ".".join(str(p) for p in e.path) or None, "message": e.message}
                for e in errors[:10]
            ],
        )


async def activate(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    agent_id: uuid.UUID,
    slug: str,
    permission: Permission,
    settings: dict[str, Any],
    actor: str,
) -> AgentConnectorActivation:
    """Activar (o cambiar el permiso o los ajustes de) una conexión ya autorizada
    para un agente (35.3, 35.4): no vuelve a pedir la autorización."""
    if permission not in PERMISSIONS:
        raise ActivationError("invalid_permission", 422)
    connector, install = await connection_of(session, tenant_id, slug)
    if install is None or install.status not in LIVE:
        raise ActivationError("connection_not_authorized", 409, integration=slug)
    from nexus_api.services.connectors.catalog import settings_schema_of

    validate_settings(settings_schema_of(connector), settings)
    row = await session.scalar(
        sa.select(AgentConnectorActivation).where(
            AgentConnectorActivation.tenant_id == tenant_id,
            AgentConnectorActivation.agent_id == agent_id,
            AgentConnectorActivation.connector_id == install.id,
        )
    )
    before = {"permission": row.permission, "settings": row.settings} if row else None
    if row is None:
        row = AgentConnectorActivation(
            tenant_id=tenant_id,
            agent_id=agent_id,
            connector_id=install.id,
            permission=permission,
            settings=dict(settings),
            created_by=actor,
        )
        session.add(row)
    else:
        row.permission = permission
        row.settings = dict(settings)
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor=actor,
            action="integration.activated",
            target=f"agent:{agent_id}",
            before_json=before,
            after_json={"integration": slug, "permission": permission},
        )
    )
    await session.flush()
    return row


async def ensure_activation(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    agent_id: uuid.UUID,
    install: TenantConnector,
    actor: str,
    permission: Permission = "read_write",
) -> None:
    """Los flujos de antes que dan herramientas de un conector a un agente (al
    conectar, la API de partners) dejan también su activación, para que la regla
    no les quite lo que acaban de dar."""
    exists = await session.scalar(
        sa.select(AgentConnectorActivation.id).where(
            AgentConnectorActivation.tenant_id == tenant_id,
            AgentConnectorActivation.agent_id == agent_id,
            AgentConnectorActivation.connector_id == install.id,
        )
    )
    if exists is None:
        session.add(
            AgentConnectorActivation(
                tenant_id=tenant_id,
                agent_id=agent_id,
                connector_id=install.id,
                permission=permission,
                settings={},
                created_by=actor,
            )
        )
        await session.flush()


async def ensure_activations_for_tools(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    agent_id: uuid.UUID | None,
    tools: list[str] | set[str] | frozenset[str],
    actor: str,
) -> int:
    """Los caminos de antes (la consola de hoy, la API de partners, al conectar)
    dan herramientas de un conector a un agente en su lista: les dejan su
    activación «Leer y escribir», para que la regla no les quite lo que acaban de
    dar. En la consola nueva no: allí activa la persona, por agente (35.3).
    Devuelve cuántas activaciones creó."""
    from nexus_api.services.channel_config import partner_on_v2

    if agent_id is None or not tools or await partner_on_v2(session, tenant_id):
        return 0
    installs = (
        await session.scalars(
            sa.select(TenantConnector)
            .join(ToolCatalog, ToolCatalog.connector_id == TenantConnector.connector_id)
            .where(
                TenantConnector.tenant_id == tenant_id,
                TenantConnector.status != TenantConnectorStatus.DISCONNECTED.value,
                ToolCatalog.name.in_(list(tools)),
            )
            .distinct()
        )
    ).all()
    created = 0
    for install in installs:
        before = await session.scalar(
            sa.select(sa.func.count())
            .select_from(AgentConnectorActivation)
            .where(
                AgentConnectorActivation.tenant_id == tenant_id,
                AgentConnectorActivation.agent_id == agent_id,
                AgentConnectorActivation.connector_id == install.id,
            )
        )
        if not before:
            await ensure_activation(
                session, tenant_id=tenant_id, agent_id=agent_id, install=install, actor=actor
            )
            created += 1
    return created


async def _spec_of(session: AsyncSession, agent_id: uuid.UUID) -> dict[str, Any]:
    """El documento del agente: su borrador si lo hay, si no su versión activa."""
    cfg = await session.scalar(
        sa.select(AgentConfig)
        .where(AgentConfig.agent_id == agent_id)
        .order_by(
            (AgentConfig.status == AgentConfigStatus.STAGED).desc(), AgentConfig.version.desc()
        )
        .limit(1)
    )
    return dict(cfg.spec or {}) if cfg is not None else {}


async def _connector_tools(session: AsyncSession, connector: Connector) -> set[str]:
    return set(
        (
            await session.scalars(
                sa.select(ToolCatalog.name).where(ToolCatalog.connector_id == connector.id)
            )
        ).all()
    )


async def affected_skills(
    session: AsyncSession, agent_id: uuid.UUID, connector: Connector
) -> AffectedSkills:
    """Las habilidades y procedimientos del agente que usan la integración (35.7)."""
    spec = await _spec_of(session, agent_id)
    tools = await _connector_tools(session, connector)
    out = AffectedSkills()
    for skill in spec.get("skills") or []:
        if isinstance(skill, dict) and skill.get("integration") == connector.slug:
            out.skills.append(str(skill.get("key")))
    for procedure in spec.get("procedures") or []:
        if isinstance(procedure, dict) and tools & set(procedure.get("tools") or []):
            out.procedures.append(str(procedure.get("title") or procedure.get("id")))
    return out


async def deactivate(
    session: AsyncSession, *, tenant_id: uuid.UUID, agent_id: uuid.UUID, slug: str, actor: str
) -> AffectedSkills:
    """Quitar la integración de un agente: sus herramientas dejan de estar desde el
    siguiente turno, y se dice qué habilidades se quedan sin ella (35.7)."""
    connector, install = await connection_of(session, tenant_id, slug)
    if install is not None:
        await session.execute(
            sa.delete(AgentConnectorActivation).where(
                AgentConnectorActivation.tenant_id == tenant_id,
                AgentConnectorActivation.agent_id == agent_id,
                AgentConnectorActivation.connector_id == install.id,
            )
        )
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor=actor,
            action="integration.deactivated",
            target=f"agent:{agent_id}",
            after_json={"integration": slug},
        )
    )
    await session.flush()
    return await affected_skills(session, agent_id, connector)


async def needed_by(session: AsyncSession, agent_id: uuid.UUID) -> set[str]:
    """Las integraciones que piden las habilidades del agente (para ordenar el
    catálogo, 35.2): sus habilidades, sus peticiones de conexión y las
    integraciones de las herramientas que usa."""
    spec = await _spec_of(session, agent_id)
    out = {
        str(s["integration"])
        for s in spec.get("skills") or []
        if isinstance(s, dict) and s.get("integration")
    }
    out |= {
        str(r["integration"])
        for r in spec.get("connection_requests") or []
        if isinstance(r, dict) and r.get("integration")
    }
    tools = set(spec.get("tools") or [])
    for p in spec.get("procedures") or []:
        if isinstance(p, dict):
            tools |= set(p.get("tools") or [])
    if tools:
        out |= set(
            (
                await session.scalars(
                    sa.select(Connector.slug)
                    .join(ToolCatalog, ToolCatalog.connector_id == Connector.id)
                    .where(ToolCatalog.name.in_(tools))
                )
            ).all()
        )
    return out


async def users_of(
    session: AsyncSession, tenant_id: uuid.UUID, install: TenantConnector
) -> list[dict[str, Any]]:
    """Los agentes que usan una conexión, con su permiso y sus ajustes (36.1)."""
    rows = (
        await session.execute(
            sa.select(
                Agent.id,
                Agent.name,
                AgentConnectorActivation.permission,
                AgentConnectorActivation.settings,
            )
            .join(
                AgentConnectorActivation,
                sa.and_(
                    AgentConnectorActivation.agent_id == Agent.id,
                    AgentConnectorActivation.tenant_id == Agent.tenant_id,
                ),
            )
            .where(
                AgentConnectorActivation.tenant_id == tenant_id,
                AgentConnectorActivation.connector_id == install.id,
            )
            .order_by(Agent.name)
        )
    ).all()
    return [
        {
            "agent_id": r.id,
            "name": r.name,
            "permission": r.permission,
            "settings": dict(r.settings or {}),
        }
        for r in rows
    ]


async def disconnect_impact(
    session: AsyncSession, tenant_id: uuid.UUID, install: TenantConnector
) -> list[dict[str, Any]]:
    """«Desconectar para todos» (36.4): cada agente afectado y sus habilidades."""
    connector = await session.get(Connector, install.connector_id)
    assert connector is not None
    out = []
    for user in await users_of(session, tenant_id, install):
        affected = await affected_skills(session, user["agent_id"], connector)
        out.append(
            {
                "agent_id": str(user["agent_id"]),
                "name": user["name"],
                "skills": affected.skills,
                "procedures": affected.procedures,
            }
        )
    return out


async def on_needs_reauth(session: AsyncSession, install: TenantConnector) -> int:
    """La autorización caducó (36.3): las pruebas de los agentes que la usan quedan
    desactualizadas y se vuelven a pasar; el aviso al partner sale aparte. Devuelve
    cuántos agentes."""
    from nexus_api.services.business.writes import mark_tests_stale

    agents = (
        await session.scalars(
            sa.select(AgentConnectorActivation.agent_id).where(
                AgentConnectorActivation.tenant_id == install.tenant_id,
                AgentConnectorActivation.connector_id == install.id,
            )
        )
    ).all()
    for agent_id in agents:
        await mark_tests_stale(session, sections=["integrations"], only_agent=agent_id)
    return len(agents)


__all__ = [
    "LIVE",
    "PERMISSIONS",
    "ActivationError",
    "AffectedSkills",
    "Permission",
    "ToolPolicy",
    "activate",
    "affected_skills",
    "connection_of",
    "deactivate",
    "disconnect_impact",
    "ensure_activation",
    "ensure_activations_for_tools",
    "needed_by",
    "on_needs_reauth",
    "tool_policy",
    "users_of",
    "validate_settings",
]
