"""The automatic pass to Reservas at deploy time — spec 048, requirement 3
(amended on 2026-10-29; plan, decisions 11 to 16).

``release.sh`` runs ``scripts/pass_booking_to_reservas.py`` in the migration
task, after ``alembic upgrade head`` and the connectors seed. Nobody does
anything by hand:

1. The clients are listed with the migrations role — only their ids. Then each
   one passes in **its own transaction, under its RLS** (``admin.as_tenant``):
   nothing of a client is read or written while another one passes.
2. A client passes when some active agent's active version or draft names
   ``booking.*`` (``passing.legacy_client``); otherwise it is skipped, so the
   next deploy finds nobody.
3. Without Reservas, it is turned on first (:func:`turn_on_reservas`): capacity
   of a restaurant when the business is a restaurant — the saved sector (spec
   047, requirement 57), or else the template its agent comes from — and
   appointments per person otherwise, with the starting values of the mode.
   It never opens the client's people's access nor invites anybody.
4. ``passing.pass_to_reservas`` in its automatic form: the active version of
   each agent that names ``booking.*`` is published at once with
   ``reservas.*``, as Auphere (:data:`ACTOR`) and with its reason, without the
   gate; a draft that names it is rewritten and never published; the future
   appointments are imported; the report goes to the client's audit
   (``reservations.passed``, ``automatic: true``).
5. A client that fails is rolled back alone and logged
   (``reservations.auto_pass_failed``, with ``tenant_id`` and the error type —
   no personal data); the others go on. The end is one line,
   ``reservations.auto_pass_done``, with the counts: the signal the final
   deletion of ``booking.*`` (T030) waits for. The deploy never stops here: the
   runtime still runs ``booking.*`` for whoever keeps it (requirement 5.3), and
   that deletion refuses loudly while someone still names it (5.2).

The sector is only **read** here (``sector_key``): no identification is queued
and no model is called during a deploy.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexus_api.core.tenant_context import declare_tenant
from nexus_api.db.models import (
    Agent,
    AgentStatus,
    AuditLog,
    ClientAccess,
    ClientModule,
    ReservationSettings,
    Tenant,
)
from nexus_api.repositories import AgentConfigRepository
from nexus_api.services.builder.sectors import TEMPLATE_SECTOR
from nexus_api.services.business.sector import sector_key
from nexus_api.services.reservations import admin as reservations_admin
from nexus_api.services.reservations import passing
from nexus_api.services.reservations.automation import error_text

log = structlog.get_logger(__name__)

#: Who signs the pass: Auphere, not a person (plan, decision 12).
ACTOR: Final = "platform:reservas-pass"
#: Why it is published without the gate. The console shows it in the history.
REASON: Final = (
    "Cambio de la plataforma (spec 048): booking.* se retira y reservas.* la "
    "sustituye una a una. Se publica sin la puerta de pruebas."
)
#: The note of the version it publishes.
NOTE: Final = "Paso automático a Reservas"
#: The sector key (and template group) of a restaurant.
RESTAURANT: Final = "restaurante"


class AutoPassRefused(Exception):
    """This client cannot pass; it is logged and the others go on."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


# ── turning Reservas on ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class Mode:
    """The mode Reservas is turned on with, and what decided it."""

    mode: str
    capacity_kind: str | None
    source: str  # sector | template | default

    def as_dict(self) -> dict[str, Any]:
        return {"mode": self.mode, "capacity_kind": self.capacity_kind, "from": self.source}


def _mode(restaurant: bool, source: str) -> Mode:
    if restaurant:
        return Mode("capacity", "restaurant", source)
    return Mode("services", None, source)


async def _template_of_legacy_agent(session: AsyncSession) -> str | None:
    """The template of the oldest active agent that names ``booking.*`` and
    comes from one (its active version's, or else its draft's)."""
    repo = AgentConfigRepository(session)
    ids = (
        await session.execute(
            sa.select(Agent.id)
            .where(Agent.status == AgentStatus.ACTIVE.value)
            .order_by(Agent.created_at, Agent.id)
        )
    ).scalars()
    for agent_id in list(ids):
        active = await repo.get_active(agent_id=agent_id)
        draft = await repo.get_draft(agent_id=agent_id)
        if not (passing.version_names_booking(active) or passing.version_names_booking(draft)):
            continue
        ref = (active.seed_template_ref if active else None) or (
            draft.seed_template_ref if draft else None
        )
        if ref:
            return ref
    return None


async def choose_mode(session: AsyncSession) -> Mode:
    """Requirement 3.2 (plan, decision 13): a restaurant gets capacity, of a
    restaurant; anything else, appointments per person. The saved sector
    decides; without one, the template the agent comes from. Under the
    client's RLS; it only reads."""
    key = await sector_key(session)
    if key is not None:
        return _mode(key == RESTAURANT, "sector")
    template = await _template_of_legacy_agent(session)
    if template is not None:
        return _mode(TEMPLATE_SECTOR.get(template) == RESTAURANT, "template")
    return _mode(False, "default")


async def turn_on_reservas(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    partner_id: uuid.UUID | None,
    now: datetime,
) -> dict[str, Any] | None:
    """Reservas on, just what the agent needs to book (plan, decisions 13 and
    16): ``reservas`` on the client's module list and, the first time, its
    settings with the starting values of the mode (``admin.apply_choice``).
    ``enabled`` — whether the client's people can sign in — is left as it was,
    and nobody is invited.

    ``None`` when it was already on: its mode never changes. A client that had
    the settings and the module off gets the module back, with its mode."""
    settings = await session.get(ReservationSettings, tenant_id)
    access = await session.get(ClientAccess, tenant_id)
    if settings is not None and access is not None and access.reservas_on:
        return None
    if access is None:
        if partner_id is None:
            # ``client_access`` hangs from the client's partner.
            raise AutoPassRefused("no_partner")
        access = ClientAccess(tenant_id=tenant_id, partner_id=partner_id, enabled=False, modules=[])
        session.add(access)
    if not access.reservas_on:
        access.modules = list(access.ordered_modules(also=(ClientModule.RESERVAS.value,)))
        access.updated_by = ACTOR
        session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor=ACTOR,
                action="client_access.updated",
                target=f"tenant:{tenant_id}",
                after_json={
                    "enabled": access.enabled,
                    "modules": list(access.modules),
                    "automatic": True,
                },
            )
        )
    await session.flush()
    if settings is not None:
        return {"mode": settings.mode, "capacity_kind": settings.capacity_kind, "from": "existing"}
    mode = await choose_mode(session)
    await reservations_admin.apply_choice(
        session,
        tenant_id,
        had_module=False,
        wants_module=True,
        choice=reservations_admin.Choice(mode=mode.mode, capacity_kind=mode.capacity_kind),
        actor=ACTOR,
        now=now,
        # The pass publishes the agents' versions itself.
        prepare_agents=False,
    )
    return mode.as_dict()


# ── one client ──────────────────────────────────────────────────────────────


async def pass_tenant(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    partner_id: uuid.UUID | None,
    now: datetime,
) -> passing.PassReport | None:
    """One client, under its RLS, in the caller's transaction. ``None`` when
    no agent of it names ``booking.*``."""
    if await passing.legacy_client(session, tenant_id, now=now) is None:
        return None
    activated = await turn_on_reservas(session, tenant_id, partner_id=partner_id, now=now)
    return await passing.pass_to_reservas(
        session,
        tenant_id,
        actor=ACTOR,
        now=now,
        automatic=passing.Automatic(reason=REASON, note=NOTE, activated=activated),
    )


async def pass_one(
    factory: async_sessionmaker[AsyncSession], tenant_id: uuid.UUID, *, now: datetime
) -> passing.PassReport | None:
    """One client in its own transaction. Its partner is read as the platform
    (``partner_tenants`` is scoped by partner: the client's RLS would hide it);
    everything else under the client's RLS. If anything fails, nothing of it
    is kept and the error goes up."""
    from nexus_api.services.client_access import partner_of

    async with factory() as session, session.begin():
        await declare_tenant(session, tenant_id)
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            return None
        partner = await partner_of(session, tenant)
        async with reservations_admin.as_tenant(session, tenant_id):
            return await pass_tenant(
                session,
                tenant_id,
                partner_id=partner.id if partner is not None else None,
                now=now,
            )


# ── every client ────────────────────────────────────────────────────────────


@dataclass
class Summary:
    """What a run did, for ``reservations.auto_pass_done``."""

    passed: list[uuid.UUID] = field(default_factory=list)
    failed: list[uuid.UUID] = field(default_factory=list)
    activated: int = 0
    published: int = 0
    drafts: int = 0
    imported: int = 0
    already_imported: int = 0
    not_imported: int = 0

    def add(self, report: passing.PassReport) -> None:
        self.passed.append(report.tenant_id)
        self.activated += int(report.activated is not None)
        self.published += len(report.published)
        self.drafts += len(report.agents)
        self.imported += len(report.imports.imported)
        self.already_imported += report.imports.already
        self.not_imported += len(report.imports.not_imported)

    def as_log(self) -> dict[str, Any]:
        return {
            "passed": len(self.passed),
            "failed": len(self.failed),
            "failed_tenants": [str(t) for t in self.failed],
            "activated": self.activated,
            "published": self.published,
            "drafts": self.drafts,
            "imported": self.imported,
            "already_imported": self.already_imported,
            "not_imported": self.not_imported,
        }


def describe_error(exc: BaseException) -> str:
    """The error for the log, without anybody's data (``error_text``), and the
    one underneath when a later statement hid it (a failed transaction)."""
    text = error_text(exc)
    inner = exc.__cause__ or exc.__context__
    return f"{text} <- {error_text(inner)}" if inner is not None else text


async def run(factory: async_sessionmaker[AsyncSession], *, now: datetime | None = None) -> Summary:
    """Every client, one at a time. Never raises because of a client."""
    moment = now or datetime.now(UTC)
    async with factory() as session, session.begin():
        tenant_ids = list(
            (
                await session.execute(sa.select(Tenant.id).order_by(Tenant.created_at, Tenant.id))
            ).scalars()
        )
    summary = Summary()
    for tenant_id in tenant_ids:
        try:
            report = await pass_one(factory, tenant_id, now=moment)
        except Exception as exc:
            summary.failed.append(tenant_id)
            log.error(
                "reservations.auto_pass_failed",
                tenant_id=str(tenant_id),
                error=describe_error(exc),
            )
            continue
        if report is None:
            continue
        summary.add(report)
        log.info(
            "reservations.auto_passed",
            tenant_id=str(tenant_id),
            activated=report.activated,
            published=len(report.published),
            drafts=len(report.agents),
            imported=len(report.imports.imported),
            not_imported=len(report.imports.not_imported),
        )
    log.info("reservations.auto_pass_done", **summary.as_log())
    return summary


__all__ = [
    "ACTOR",
    "NOTE",
    "REASON",
    "AutoPassRefused",
    "Mode",
    "Summary",
    "choose_mode",
    "describe_error",
    "pass_one",
    "pass_tenant",
    "run",
    "turn_on_reservas",
]
