"""La consola nueva, partner a partner — spec 047, T004 (requisito 55.2, research D38).

La consola de la fábrica no se enciende para todos a la vez: Auphere la activa
para cada partner desde el panel de operador. Hasta entonces el partner ve la
consola de hoy y la API sirve a las dos. Tres reglas viven aquí:

* **Un partner sin activar ve ``v1``.** La versión sale de una sola columna,
  ``partners.console_v2_enabled_at``: con fecha, ``v2``; sin ella, ``v1``.
* **Se guarda quién y cuándo.** ``console_v2_enabled_by`` es la persona de
  Auphere que la activó (la base no deja un «quién» sin «cuándo»), y cada
  cambio deja una fila de auditoría de plataforma con antes y después (§IV).
* **Desactivar devuelve la consola de hoy** (55.5). Que solo se pueda hasta
  que el partner confirme el reparto en bolsas llega con esa confirmación
  (ola 10); hoy no hay nada que confirmar.

No es un módulo de ``console_modules`` (spec 032): es un modo de la consola
con estado de migración. Ninguna función confirma: la transacción es del
llamante.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Final, Literal

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import AuditLog, Partner

ConsoleVersion = Literal["v1", "v2"]

ENABLED_ACTION = "partner.console_v2_enabled"
DISABLED_ACTION = "partner.console_v2_disabled"


class ConsoleV2Error(Exception):
    """Un no con nombre. ``code`` es vocabulario cerrado; ``status``, el HTTP."""

    def __init__(self, code: str, status: int) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class ConsoleV2State:
    version: ConsoleVersion
    enabled_at: datetime | None
    enabled_by: str | None


def console_version(partner: Partner) -> ConsoleVersion:
    """La consola que ve el partner: ``v2`` solo si Auphere la activó."""
    return "v2" if partner.console_v2_enabled_at is not None else "v1"


def _state(partner: Partner) -> ConsoleV2State:
    return ConsoleV2State(
        version=console_version(partner),
        enabled_at=partner.console_v2_enabled_at,
        enabled_by=partner.console_v2_enabled_by,
    )


async def _locked(session: AsyncSession, partner_id: uuid.UUID) -> Partner:
    partner = await session.scalar(
        sa.select(Partner)
        .where(Partner.id == partner_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if partner is None:
        raise ConsoleV2Error("unknown_partner", 404)
    return partner


async def _set(
    session: AsyncSession,
    partner_id: uuid.UUID,
    *,
    enable: bool,
    actor: str,
    reason: str | None = None,
) -> ConsoleV2State:
    if not actor.strip():
        raise ValueError("enabling or disabling the new console needs the person")
    partner = await _locked(session, partner_id)
    before = console_version(partner)
    after: ConsoleVersion = "v2" if enable else "v1"
    if before == after:
        # Repetir no cambia quién ni cuándo, ni deja otra fila.
        return _state(partner)
    if enable:
        partner.console_v2_enabled_at = await session.scalar(sa.select(sa.func.now()))
        partner.console_v2_enabled_by = actor
    else:
        partner.console_v2_enabled_at = None
        partner.console_v2_enabled_by = None
    session.add(
        AuditLog(
            tenant_id=None,
            actor=actor,
            action=ENABLED_ACTION if enable else DISABLED_ACTION,
            target=f"partner:{partner_id}",
            before_json={"console_version": before},
            after_json={"console_version": after, **({"reason": reason} if reason else {})},
        )
    )
    await session.flush()
    return _state(partner)


async def enable_console_v2(
    session: AsyncSession, partner_id: uuid.UUID, *, actor: str, reason: str | None = None
) -> ConsoleV2State:
    """Activa la consola nueva para el partner, en nombre de ``actor``."""
    return await _set(session, partner_id, enable=True, actor=actor, reason=reason)


async def disable_console_v2(
    session: AsyncSession, partner_id: uuid.UUID, *, actor: str, reason: str | None = None
) -> ConsoleV2State:
    """Devuelve al partner la consola de hoy, en nombre de ``actor``."""
    return await _set(session, partner_id, enable=False, actor=actor, reason=reason)


async def state_of(session: AsyncSession, partner_id: uuid.UUID) -> ConsoleV2State:
    """Qué consola ve hoy el partner. ``session`` sin transacción abierta."""
    async with session.begin():
        partner = await session.get(Partner, partner_id, populate_existing=True)
        if partner is None:
            raise ConsoleV2Error("unknown_partner", 404)
        return _state(partner)


# ── el ensayo y la activación (T179, T180; requisitos 55.4 y 55.5) ─────────────

#: Un ensayo vale para activar durante este tiempo; después hay que repetirlo.
DRY_RUN_VALID_FOR: Final = timedelta(hours=24)
_E164: Final = re.compile(r"^\+[1-9]\d{6,14}$")


def legacy_numbers(policies: dict[str, Any] | None) -> list[str] | None:
    """La audiencia de un número con las reglas de hoy: los números de prueba del
    agente (``admin_access.admin_only``), o ``None`` si responde a todos. La misma
    regla que la migración 0192 y que ``core.admin_gate``."""
    access = (policies or {}).get("admin_access")
    if not (isinstance(access, dict) and access.get("admin_only")):
        return None
    out: list[str] = []
    for raw in access.get("admin_phones") or []:
        digits = re.sub(r"\D", "", str(raw or ""))
        e164 = f"+{digits}"
        if len(digits) >= 7 and _E164.match(e164) and e164 not in out:
            out.append(e164)
    return out


@dataclass
class DryRun:
    status: str  # clean · diff
    agents: list[dict[str, Any]] = field(default_factory=list)
    channels: list[dict[str, Any]] = field(default_factory=list)


async def _partner_tenants(session: AsyncSession, partner_id: uuid.UUID) -> list[uuid.UUID]:
    from nexus_api.db.models import PartnerTenant

    return list(
        (
            await session.scalars(
                sa.select(PartnerTenant.tenant_id).where(PartnerTenant.partner_id == partner_id)
            )
        ).all()
    )


async def _agents_of(tenant_id: uuid.UUID) -> list[dict[str, Any]]:
    """Por agente con versión activa: si su prompt compila los mismos bytes que el
    de hoy y si su modelo sigue fijado (55.1). Los agentes hechos con la consola
    nueva no tienen un «antes» con que compararse."""
    from nexus_api.core.tenant_context import tenant_scoped_session
    from nexus_api.db.base import get_sessionmaker
    from nexus_api.db.models import Agent, AgentConfig, AgentConfigStatus
    from nexus_api.services.agent_spec.compiler import compile_spec
    from nexus_api.services.agent_spec.legacy import runtime_model_policy, spec_from_version
    from nexus_api.services.agent_spec.schema import AgentSpec

    out: list[dict[str, Any]] = []
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        rows = (
            await session.execute(
                sa.select(Agent.name, AgentConfig)
                .join(Agent, Agent.id == AgentConfig.agent_id)
                .where(
                    AgentConfig.tenant_id == tenant_id,
                    AgentConfig.status == AgentConfigStatus.ACTIVE,
                )
            )
        ).all()
        for name, version in rows:
            row: dict[str, Any] = {
                "tenant_id": str(tenant_id),
                "agent_id": str(version.agent_id),
                "agent_name": name,
                "version_id": str(version.id),
            }
            if version.spec is None:
                out.append({**row, "same": False, "reason": "no_spec"})
                continue
            spec = AgentSpec.model_validate(version.spec)
            if spec.mode != "instructions":
                continue
            today = spec_from_version(
                agent_name=name,
                system_prompt_rendered=version.system_prompt_rendered,
                tools=list(version.tools or []),
                policies=dict(version.policies or {}),
            )
            prompt = compile_spec(spec) == compile_spec(today)
            model = runtime_model_policy(spec) == runtime_model_policy(today)
            out.append(
                {
                    **row,
                    "same": prompt and model,
                    "prompt_identical": prompt,
                    "model_pinned": model,
                }
            )
    return out


_POLICIES = sa.text(
    """
    SELECT v.policies FROM agent_configs v
     WHERE v.tenant_id = :t
       AND v.agent_id = COALESCE(
             :a,
             (SELECT g.id FROM agents g
               WHERE g.tenant_id = :t AND g.lifecycle <> 'archived'
               ORDER BY g.is_default DESC, g.created_at, g.id LIMIT 1))
     ORDER BY (v.status = 'active') DESC, v.version DESC LIMIT 1
    """
)


async def _audiences_of(tenant_id: uuid.UUID, *, apply: bool) -> list[dict[str, Any]]:
    """Por número: la audiencia efectiva con las reglas de hoy y con las de la
    consola nueva (55.4). Un número aún en ``unset`` recibe lo que le daría la
    migración 0192; con ``apply`` se guarda (al activar), si no, solo se compara."""
    from nexus_api.core.tenant_context import tenant_scoped_session
    from nexus_api.db.base import get_sessionmaker
    from nexus_api.db.models import Channel, ChannelAudienceNumber

    out: list[dict[str, Any]] = []
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        channels = (
            await session.scalars(
                sa.select(Channel).where(
                    Channel.tenant_id == tenant_id,
                    Channel.status != "disconnected",
                    Channel.provider != "qa_playground",
                )
            )
        ).all()
        for channel in channels:
            policies = await session.scalar(_POLICIES, {"t": tenant_id, "a": channel.agent_id})
            numbers = legacy_numbers(policies)
            mode = "everyone" if numbers is None else "team_only"
            before: dict[str, Any] = {"mode": mode, "numbers": sorted(numbers or [])}
            pending = channel.audience_mode == "unset"
            if pending:
                after = {**before, "exceptions": []}
                if apply:
                    channel.audience_mode = mode
                    for phone in sorted(numbers or []):
                        session.add(
                            ChannelAudienceNumber(
                                tenant_id=tenant_id,
                                channel_id=channel.id,
                                kind="test",
                                phone_e164=phone,
                            )
                        )
            else:
                stored = (
                    await session.execute(
                        sa.select(
                            ChannelAudienceNumber.kind, ChannelAudienceNumber.phone_e164
                        ).where(ChannelAudienceNumber.channel_id == channel.id)
                    )
                ).all()
                after = {
                    "mode": channel.audience_mode,
                    "numbers": sorted(p for k, p in stored if k == "test"),
                    "exceptions": sorted(p for k, p in stored if k == "exception"),
                }
            same = (
                before["mode"] == after["mode"]
                and (before["mode"] == "everyone" or before["numbers"] == after["numbers"])
                and not after["exceptions"]
            )
            out.append(
                {
                    "tenant_id": str(tenant_id),
                    "channel_id": str(channel.id),
                    # El número del propio negocio: el operador lo reconoce así.
                    "identifier": channel.provider_identifier,
                    "before": before,
                    "after": after,
                    "pending_migration": pending,
                    "same": same,
                }
            )
    return out


async def _record(
    session: AsyncSession,
    partner_id: uuid.UUID,
    kind: str,
    run: DryRun,
    actor: str,
    *,
    reason: str | None = None,
) -> None:
    from nexus_api.core.partner_context import apply_partner_to_session
    from nexus_api.db.models import MigrationReport

    async with session.begin():
        await apply_partner_to_session(session, partner_id)
        session.add(
            MigrationReport(
                partner_id=partner_id,
                kind=kind,
                status=run.status,
                eval_diff=run.agents,
                audience_diff=run.channels,
                created_by=actor,
                reason=reason,
            )
        )


async def dry_run(
    session: AsyncSession, partner_id: uuid.UUID, *, actor: str, reason: str | None = None
) -> DryRun:
    """El ensayo (55.4): compara, por agente y por número, y deja su informe. No
    cambia nada. ``session`` sin transacción abierta."""
    async with session.begin():
        await _locked(session, partner_id)
        tenants = await _partner_tenants(session, partner_id)
    run = DryRun(status="clean")
    for tenant_id in tenants:
        run.agents += await _agents_of(tenant_id)
        run.channels += await _audiences_of(tenant_id, apply=False)
    if not all(a["same"] for a in run.agents) or not all(c["same"] for c in run.channels):
        run.status = "diff"
    await _record(session, partner_id, "dry_run", run, actor, reason=reason)
    return run


async def _last_dry_run(
    session: AsyncSession, partner_id: uuid.UUID
) -> tuple[str, datetime] | None:
    from nexus_api.core.partner_context import apply_partner_to_session
    from nexus_api.db.models import MigrationReport

    async with session.begin():
        await apply_partner_to_session(session, partner_id)
        row = (
            await session.execute(
                sa.select(MigrationReport.status, MigrationReport.created_at)
                .where(MigrationReport.partner_id == partner_id, MigrationReport.kind == "dry_run")
                .order_by(MigrationReport.created_at.desc())
                .limit(1)
            )
        ).first()
    return None if row is None else (str(row[0]), row[1])


async def activate(
    session: AsyncSession, partner_id: uuid.UUID, *, actor: str, reason: str | None = None
) -> ConsoleV2State:
    """Activa con un ensayo limpio de las últimas 24 h (55.4): guarda la audiencia
    de los números que aún no la tenían y enciende la consola nueva."""
    last = await _last_dry_run(session, partner_id)
    if last is None or last[1] < datetime.now(UTC) - DRY_RUN_VALID_FOR:
        raise ConsoleV2Error("dry_run_required", 409)
    if last[0] != "clean":
        raise ConsoleV2Error("dry_run_has_differences", 409)
    async with session.begin():
        tenants = await _partner_tenants(session, partner_id)
    run = DryRun(status="clean")
    for tenant_id in tenants:
        run.channels += await _audiences_of(tenant_id, apply=True)
    async with session.begin():
        state = await enable_console_v2(session, partner_id, actor=actor, reason=reason)
    await _record(session, partner_id, "activation", run, actor, reason=reason)
    return state


async def deactivate(
    session: AsyncSession, partner_id: uuid.UUID, *, actor: str, reason: str | None = None
) -> ConsoleV2State:
    """Devuelve la consola de hoy, solo hasta que el partner confirma el reparto en
    bolsas (55.5): después, su dinero ya es de las bolsas."""
    from nexus_api.core.partner_context import apply_partner_to_session
    from nexus_api.db.models import WalletMigrationProposal

    async with session.begin():
        await apply_partner_to_session(session, partner_id)
        confirmed = await session.scalar(
            sa.select(WalletMigrationProposal.id).where(
                WalletMigrationProposal.partner_id == partner_id,
                WalletMigrationProposal.confirmed_at.is_not(None),
            )
        )
    if confirmed is not None:
        raise ConsoleV2Error("wallet_split_confirmed", 409)
    async with session.begin():
        return await disable_console_v2(session, partner_id, actor=actor, reason=reason)


__all__ = [
    "DISABLED_ACTION",
    "DRY_RUN_VALID_FOR",
    "ENABLED_ACTION",
    "ConsoleV2Error",
    "ConsoleV2State",
    "ConsoleVersion",
    "DryRun",
    "activate",
    "console_version",
    "deactivate",
    "disable_console_v2",
    "dry_run",
    "enable_console_v2",
    "legacy_numbers",
    "state_of",
]
