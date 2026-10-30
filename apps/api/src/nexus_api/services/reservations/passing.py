"""«Pasar a Reservas» — spec 048 (requisito 3).

``booking.*`` escribe en ``appointments``, una agenda que el negocio no ve.
Pasar a un cliente a Reservas hace tres cosas, todas bajo la RLS del cliente y
en la transacción de quien lo pide:

1. **Las versiones de cada agente** reciben ``reservas.*`` donde nombraban
   ``booking.*``: en ``tools``, en el AgentSpec (``tools`` y procedimientos) y
   en el texto, con el mapa fijo de ``agent_spec.retired`` y, además, solo
   ``reservas.services`` (los ids de servicio que pide ``reservas.find_slots``;
   048, decisiones 19 y 26). Un agente que solo miraba la agenda no sale del paso
   pudiendo reservar, cancelar ni mover citas (R3.3). Activar Reservas desde
   Acceso (``every_agent``) sigue dando las nueve a cada agente, en un borrador que
   pasa la puerta (R3.9).
2. **Las citas futuras** de ``appointments`` cuyo servicio y cuya persona casan
   con los de Reservas pasan a ``reservations``. La reserva guarda la cita de
   origen en su clave (``appointment:<id>``): repetir no duplica, y el historial
   y las comisiones no la cuentan dos veces. Las que no casan se quedan donde
   están y salen en el informe con su motivo; nadie recibe un mensaje (la
   persona ya sabe de su cita).
3. **El informe**, en la auditoría del cliente (``reservations.passed``).

Two callers ask for it:

- **Turning the module on** from Acceso (``admin.apply_choice``): every active
  agent's draft gains Reservas and is not promoted; it goes live through the
  gate, as any change (constitution §IV).
- **The automatic pass** of every deploy (``auto_pass.py``, amendment of
  2026-10-29): only the agents that name ``booking.*``. Their active version is
  published at once from itself, as Auphere and without the gate (a 1:1
  platform change, plan decision 12); a draft that names ``booking.*`` is
  rewritten the same way and is never published.
"""

from __future__ import annotations

import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import (
    Agent,
    AgentConfig,
    AgentStatus,
    Appointment,
    AppointmentStatus,
    AuditLog,
    ClientAccess,
    Customer,
    KGNode,
    Reservation,
    ReservationService,
    ReservationSettings,
)
from nexus_api.db.models.reservation import LIVE_STATUSES
from nexus_api.services.agent_spec.retired import (
    RETIRED_PREFIX,
    RETIRED_TOOLS,
    doc_names_retired,
    mentions_retired,
    rewrite_doc,
    rewrite_text,
)

#: Lo que el agente gana con Reservas (contrato ``agent-tools.md``).
RESERVAS_TOOLS: tuple[str, ...] = (
    "reservas.services",
    "reservas.find_slots",
    "reservas.create",
    "reservas.list_mine",
    "reservas.reschedule",
    "reservas.cancel",
    "reservas.confirm_attendance",
    "reservas.join_waitlist",
    "reservas.answer_offer",
)
#: Lo que pierde: escribía en ``appointments``, que la consola no ve.
LEGACY_PREFIX: Final = RETIRED_PREFIX

#: La clave de la reserva que viene de una cita de antes.
IMPORT_KEY: Final = "appointment:"
#: Quién figura como autor de lo importado.
IMPORTER: Final = "Paso a Reservas"

#: Por qué una cita no pasa (el informe lo dice con estas claves).
REASONS: Final = (
    "capacity_mode",  # Reservas en Aforo: una cita no dice para cuántos
    "service_missing",  # ningún servicio de Reservas se llama así
    "service_not_bookable",  # existe, pero no se reserva
    "staff_missing",  # la cita no dice con quién
    "staff_not_found",  # nadie del equipo de Reservas se llama así
    "staff_cannot_do_service",  # esa persona no hace ese servicio
    "slot_taken",  # esa persona ya tiene una reserva a esa hora
)

_FUTURE_STATUSES: Final = (AppointmentStatus.BOOKED, AppointmentStatus.CONFIRMED)


# ── qué nombra ``booking.*`` ────────────────────────────────────────────────


def version_names_booking(cfg: AgentConfig | None) -> bool:
    """¿La versión nombra ``booking.*`` en sus herramientas, su AgentSpec o su
    texto?"""
    if cfg is None:
        return False
    return (
        any(t.startswith(LEGACY_PREFIX) for t in cfg.tools or [])
        or doc_names_retired(cfg.spec or {})
        or mentions_retired(cfg.system_prompt_rendered)
    )


@dataclass(frozen=True)
class _Fields:
    tools: list[str]
    spec: dict[str, Any] | None
    system_prompt: str


#: Lo que el paso añade al mapa uno a uno (048, decisiones 19 y 26): sin los ids de
#: servicio, ``reservas.find_slots`` y ``reservas.create`` no reservan en Servicios.
MAP_EXTRA: Final = ("reservas.services",)


def _with_reservas(tools: list[str], *, everything: bool) -> list[str]:
    """``tools`` con ``booking.*`` cambiada por su sustituta. ``everything`` (activar
    Reservas desde Acceso): y las nueve ``reservas.*``. Si no (el paso): solo el mapa
    fijo, más :data:`MAP_EXTRA` si alguna cambió."""
    kept = [
        RETIRED_TOOLS.get(t, t)
        for t in tools
        if not (t.startswith(LEGACY_PREFIX) and t not in RETIRED_TOOLS)
    ]
    if everything:
        return list(dict.fromkeys([*kept, *RESERVAS_TOOLS]))
    mapped = any(t in RETIRED_TOOLS for t in tools)
    return list(dict.fromkeys([*kept, *(MAP_EXTRA if mapped else ())]))


def _valid(spec: dict[str, Any]) -> bool:
    from pydantic import ValidationError

    from nexus_api.services.agent_spec.schema import AgentSpec

    try:
        AgentSpec.model_validate(spec)
    except ValidationError:
        return False
    return True


def _rewritten(cfg: AgentConfig, *, enable: bool, everything: bool = False) -> _Fields:
    """Lo que la versión pasa a decir: con Reservas (``enable``) o sin ella.
    ``everything``: con las nueve ``reservas.*`` (activar el módulo); si no, el
    mapa fijo (el paso, R3.3)."""
    tools = list(cfg.tools or [])
    spec = dict(cfg.spec) if cfg.spec else None
    prompt = cfg.system_prompt_rendered or ""
    if enable:
        new_tools = _with_reservas(tools, everything=everything)
        if spec is not None:
            named = list(spec.get("tools") or [])
            spec = rewrite_doc(spec)
            mapped = list(spec.get("tools") or [])
            extra = _with_reservas(named, everything=everything)
            spec["tools"] = list(dict.fromkeys([*mapped, *extra]))
            if not _valid(spec):
                # Al borde de su máximo de herramientas: solo el cambio uno a
                # uno, sin las que no tenía.
                spec["tools"] = mapped
        return _Fields(new_tools, spec, rewrite_text(prompt))
    gone = set(RESERVAS_TOOLS)
    if spec is not None:
        spec = dict(spec)
        if spec.get("tools"):
            spec["tools"] = [t for t in spec["tools"] if t not in gone]
        procedures = []
        for proc in spec.get("procedures") or []:
            proc = dict(proc)
            if proc.get("tools"):
                proc["tools"] = [t for t in proc["tools"] if t not in gone]
            procedures.append(proc)
        if spec.get("procedures") is not None:
            spec["procedures"] = procedures
    return _Fields([t for t in tools if t not in gone], spec, prompt)


def _same(cfg: AgentConfig, fields: _Fields) -> bool:
    return (
        set(cfg.tools or []) == set(fields.tools)
        and (cfg.spec or None) == fields.spec
        and (cfg.system_prompt_rendered or "") == fields.system_prompt
    )


@dataclass(frozen=True)
class PreparedAgent:
    agent_id: uuid.UUID
    name: str
    version: int
    revision: int | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "agent_id": str(self.agent_id),
            "name": self.name,
            "version": self.version,
            "revision": self.revision,
        }


async def prepare_agent_versions(
    session: AsyncSession,
    *,
    enable: bool,
    actor: str,
    only_booking: bool = False,
    drafts_only: bool = False,
) -> list[PreparedAgent]:
    """El borrador de cada agente activo, con Reservas (``enable``) o sin ella,
    sin promover. ``only_booking``: solo los que nombran ``booking.*`` (el paso
    a Reservas de un cliente que ya tiene el módulo). Un agente cuyo borrador ya
    dice lo que tiene que decir no se toca: repetir no crea nada.

    ``drafts_only``: only the drafts the agents already have; an agent without
    one gets none (the automatic pass publishes its active version instead)."""
    from nexus_api.services.agent_config_service import AgentConfigService
    from nexus_api.services.testing.suites import mark_stale

    svc = AgentConfigService(session)
    agents = (
        await session.execute(
            sa.select(Agent.id, Agent.name)
            .where(Agent.status == AgentStatus.ACTIVE.value)
            .order_by(Agent.created_at)
        )
    ).all()
    out: list[PreparedAgent] = []
    for agent_id, name in agents:
        draft = await svc.configs.get_draft(agent_id=agent_id)
        if drafts_only and draft is None:
            continue
        base = draft if draft is not None else await svc.configs.draft_base(agent_id=agent_id)
        if base is None:
            continue
        if only_booking and not version_names_booking(base):
            continue
        fields = _rewritten(base, enable=enable, everything=not only_booking)
        if _same(base, fields):
            continue
        await svc._validate_tools(fields.tools)
        write = await svc.open_draft(actor=actor, agent_id=agent_id)
        # Un borrador nuevo copia la versión de partida, pero no su AgentSpec:
        # se lo da esto, ya reescrito.
        target = write.draft
        target.tools = fields.tools
        target.spec = fields.spec
        target.system_prompt_rendered = fields.system_prompt
        revision = await svc.finish_draft(write, actor=actor)
        # Cambió el borrador: sus pruebas dejan de valer (spec 047, 21.7).
        await mark_stale(session, agent_id)
        out.append(PreparedAgent(agent_id, str(name), target.version, revision))
    return out


@dataclass(frozen=True)
class PublishedAgent:
    """A version the automatic pass published: the agent, the new version
    (``version`` per client, ``number`` per agent) and the one it replaced."""

    agent_id: uuid.UUID
    name: str
    version: int
    number: int
    replaced: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "agent_id": str(self.agent_id),
            "name": self.name,
            "version": self.version,
            "number": self.number,
            "replaced": self.replaced,
        }


async def publish_agent_versions(
    session: AsyncSession, *, actor: str, reason: str, note: str
) -> list[PublishedAgent]:
    """Spec 048 (requirement 3.3; plan, decision 12): for each active agent
    whose ACTIVE version names ``booking.*``, publish at once a version equal
    to it but for ``reservas.*`` in its four places — the same rewrite as the
    drafts (:func:`_rewritten`), with the fixed map of ``agent_spec.retired`` and
    ``reservas.services``, never the nine (R3.3; plan, decision 26). No gate: it is Auphere's change, not the
    partner's, and it says so (``actor``, ``reason``). The agent's tests go
    stale. An agent whose active version no longer names it is skipped:
    repeating publishes nothing."""
    from nexus_api.services.agent_config_service import AgentConfigService
    from nexus_api.services.reception import sync_reception_flag
    from nexus_api.services.testing.suites import mark_stale

    svc = AgentConfigService(session)
    agents = (
        await session.execute(
            sa.select(Agent.id, Agent.name)
            .where(Agent.status == AgentStatus.ACTIVE.value)
            .order_by(Agent.created_at)
        )
    ).all()
    out: list[PublishedAgent] = []
    for agent_id, name in agents:
        active = await svc.configs.get_active(agent_id=agent_id)
        if active is None or not version_names_booking(active):
            continue
        # R3.3: the fixed map, never more (T217; plan, decision 26).
        fields = _rewritten(active, enable=True)
        published = await svc.publish_platform_copy(
            active,
            actor=actor,
            reason=reason,
            note=note,
            tools=fields.tools,
            system_prompt_rendered=fields.system_prompt,
            spec=fields.spec,
        )
        # «Es Recepción» is what the published version says (spec 047, 53.1).
        await sync_reception_flag(session, agent_id)
        session.add(
            AuditLog(
                tenant_id=published.tenant_id,
                actor=actor,
                action="agent.publish",
                target=f"agent:{agent_id}",
                before_json={"version": active.agent_version_number},
                after_json={
                    "version": published.agent_version_number,
                    "origin": "platform",
                    "override_reason": reason,
                    "accepted_normal_failures": [],
                },
            )
        )
        # Its tools changed: its tests no longer say anything (spec 047, 21.7).
        await mark_stale(session, agent_id)
        out.append(
            PublishedAgent(
                agent_id=agent_id,
                name=str(name),
                version=published.version,
                number=published.agent_version_number,
                replaced=active.agent_version_number,
            )
        )
    await session.flush()
    return out


# ── las citas ───────────────────────────────────────────────────────────────


def name_key(text: str | None) -> str:
    """Para casar nombres: sin tildes, sin mayúsculas y sin espacios de más."""
    folded = unicodedata.normalize("NFKD", text or "")
    plain = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return " ".join(plain.casefold().split())


def imported_key(appointment_id: uuid.UUID | str) -> str:
    """La clave de la reserva que viene de esa cita."""
    return f"{IMPORT_KEY}{appointment_id}"


def _phone(identifier: str | None) -> str | None:
    digits = "".join(ch for ch in identifier or "" if ch.isdigit())
    return f"+{digits}" if len(digits) >= 7 else None


@dataclass
class ImportResult:
    imported: list[dict[str, Any]] = field(default_factory=list)
    already: int = 0
    not_imported: list[dict[str, Any]] = field(default_factory=list)


async def import_appointments(
    session: AsyncSession, tenant_id: uuid.UUID, *, now: datetime
) -> ImportResult:
    """Las citas futuras de ``appointments`` que casan, a ``reservations``.
    Corre bajo la RLS del cliente: solo ve las suyas."""
    from nexus_api.services.reservations.core import (
        Actor,
        _staff_lock,
        active_staff,
        add_event,
        load_ctx,
        lock,
        staff_for_service,
    )

    result = ImportResult()
    rows = list(
        (
            await session.execute(
                sa.select(Appointment)
                .where(Appointment.starts_at > now, Appointment.status.in_(_FUTURE_STATUSES))
                .order_by(Appointment.starts_at, Appointment.id)
            )
        ).scalars()
    )
    if not rows:
        return result
    keys = [imported_key(a.id) for a in rows]
    done = set(
        (
            await session.execute(
                sa.select(Reservation.idempotency_key).where(Reservation.idempotency_key.in_(keys))
            )
        ).scalars()
    )
    barber_ids = {a.barber_id for a in rows if a.barber_id is not None}
    barbers: dict[uuid.UUID, str] = {}
    if barber_ids:
        for node in (
            await session.execute(sa.select(KGNode).where(KGNode.id.in_(barber_ids)))
        ).scalars():
            barbers[node.id] = str((node.properties or {}).get("name") or "")
    customers = {
        c.id: c
        for c in (
            await session.execute(
                sa.select(Customer).where(Customer.id.in_({a.customer_id for a in rows}))
            )
        ).scalars()
    }
    ctx = await load_ctx(session, tenant_id)
    services = {
        name_key(s.name): s
        for s in (
            await session.execute(
                sa.select(ReservationService).where(ReservationService.archived_at.is_(None))
            )
        ).scalars()
    }
    staff = {name_key(s.name): s for s in await active_staff(session)}
    importer = Actor("system", IMPORTER)

    for appt in rows:
        key = imported_key(appt.id)
        if key in done:
            result.already += 1
            continue
        barber = barbers.get(appt.barber_id) if appt.barber_id is not None else None
        line: dict[str, Any] = {
            "appointment_id": str(appt.id),
            "starts_at": appt.starts_at.isoformat(),
            "service_name": appt.service_name.strip(),
            "staff_name": barber or None,
        }

        def refuse(reason: str, line: dict[str, Any] = line) -> None:
            result.not_imported.append({**line, "reason": reason})

        if ctx is None or ctx.mode != "services":
            refuse("capacity_mode")
            continue
        service = services.get(name_key(appt.service_name))
        if service is None:
            refuse("service_missing")
            continue
        if not service.bookable:
            refuse("service_not_bookable")
            continue
        if appt.barber_id is None:
            refuse("staff_missing")
            continue
        member = staff.get(name_key(barber)) if barber else None
        if member is None:
            refuse("staff_not_found")
            continue
        if member.id not in {s.id for s in await staff_for_service(session, service)}:
            refuse("staff_cannot_do_service")
            continue
        await lock(session, _staff_lock(ctx, member.id))
        taken = await session.scalar(
            sa.select(sa.func.count())
            .select_from(Reservation)
            .where(
                Reservation.staff_id == member.id,
                Reservation.status.in_(LIVE_STATUSES),
                Reservation.starts_at < appt.ends_at,
                Reservation.ends_at > appt.starts_at,
            )
        )
        if taken:
            refuse("slot_taken")
            continue
        cust = customers.get(appt.customer_id)
        res = Reservation(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            mode="services",
            status="confirmed",
            starts_at=appt.starts_at,
            ends_at=appt.ends_at,
            party_size=1,
            staff_id=member.id,
            service_id=service.id,
            service_name=service.name,
            price_minor=appt.price_cents,
            currency=appt.currency,
            customer_id=appt.customer_id,
            contact_name=((cust.name or "").strip()[:120] or None) if cust else None,
            contact_phone=_phone(cust.identifier) if cust else None,
            origin="agent",
            channel="whatsapp",
            created_by_kind=importer.kind,
            created_by_name=importer.name,
            note=(appt.notes or "").strip()[:500] or None,
            idempotency_key=key,
            any_staff=False,
            version=1,
        )
        session.add(res)
        await session.flush()
        add_event(
            session,
            res,
            "created",
            importer,
            {
                "channel": res.channel,
                "origin": res.origin,
                "imported_from": "appointments",
                "appointment_id": str(appt.id),
            },
        )
        result.imported.append(
            {
                **line,
                "reservation_id": str(res.id),
                "service_name": service.name,
                "staff_name": member.name,
            }
        )
    await session.flush()
    return result


# ── el paso entero ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PassReport:
    tenant_id: uuid.UUID
    agents: list[PreparedAgent]
    imports: ImportResult
    #: The automatic pass: the versions it published and how it turned
    #: Reservas on (``None`` if the client already had it).
    published: list[PublishedAgent] = field(default_factory=list)
    activated: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": str(self.tenant_id),
            "agents": [a.as_dict() for a in self.agents],
            "published": [p.as_dict() for p in self.published],
            "activated": self.activated,
            "imported": list(self.imports.imported),
            "already_imported": self.imports.already,
            "not_imported": list(self.imports.not_imported),
        }


@dataclass(frozen=True)
class Automatic:
    """What the automatic pass adds: why it publishes without the gate, the
    note the new versions carry, and how Reservas was turned on (``None`` if
    the client already had it)."""

    reason: str
    note: str
    activated: dict[str, Any] | None = None


async def pass_to_reservas(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    actor: str,
    now: datetime,
    every_agent: bool = False,
    automatic: Automatic | None = None,
) -> PassReport:
    """Los borradores, la importación y el informe en la auditoría. Corre bajo
    la RLS del cliente (``admin.as_tenant``) en la transacción del llamante.

    ``every_agent``: al activar el módulo, cada agente activo gana Reservas; si
    no, solo los que nombran ``booking.*``.

    ``automatic`` (the deploy-time pass, plan decisions 11 and 12): only the
    agents that name ``booking.*``; the active version is published from
    itself, an existing draft is rewritten and not published, and no draft is
    created. The audit row says it was automatic, why, and the activation."""
    if automatic is not None and every_agent:
        raise ValueError("the automatic pass only touches the agents that name booking.*")
    published: list[PublishedAgent] = []
    if automatic is not None:
        published = await publish_agent_versions(
            session, actor=actor, reason=automatic.reason, note=automatic.note
        )
    agents = await prepare_agent_versions(
        session,
        enable=True,
        actor=actor,
        only_booking=not every_agent,
        drafts_only=automatic is not None,
    )
    imports = await import_appointments(session, tenant_id, now=now)
    activated = automatic.activated if automatic is not None else None
    report = PassReport(tenant_id, agents, imports, published, activated)
    after: dict[str, Any] = {
        "automatic": automatic is not None,
        "agents": [a.as_dict() for a in agents],
        "imported": len(imports.imported),
        "already_imported": imports.already,
        "not_imported": imports.not_imported,
    }
    if automatic is not None:
        after.update(
            reason=automatic.reason,
            published=[p.as_dict() for p in published],
            activated=activated,
        )
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor=actor,
            action="reservations.passed",
            target=f"tenant:{tenant_id}",
            after_json=after,
        )
    )
    await session.flush()
    return report


# ── quién sigue con ``booking.*`` ───────────────────────────────────────────


@dataclass(frozen=True)
class LegacyClient:
    tenant_id: uuid.UUID
    agents: int
    future_appointments: int
    reservas_enabled: bool


async def reservas_enabled(session: AsyncSession, tenant_id: uuid.UUID) -> bool:
    """El módulo encendido y con su modo elegido. On the list is on, whether or
    not the client's people can sign in (plan, decision 16)."""
    if await session.get(ReservationSettings, tenant_id) is None:
        return False
    access = await session.get(ClientAccess, tenant_id)
    return bool(access and access.reservas_on)


async def legacy_client(
    session: AsyncSession, tenant_id: uuid.UUID, *, now: datetime
) -> LegacyClient | None:
    """Si el cliente tiene algún agente activo cuya versión activa o borrador
    nombra ``booking.*``: cuántos, y cuántas citas futuras tiene. Bajo la RLS
    del cliente."""
    from nexus_api.repositories import AgentConfigRepository

    repo = AgentConfigRepository(session)
    ids = (
        await session.execute(sa.select(Agent.id).where(Agent.status == AgentStatus.ACTIVE.value))
    ).scalars()
    agents = 0
    for agent_id in list(ids):
        active = await repo.get_active(agent_id=agent_id)
        draft = await repo.get_draft(agent_id=agent_id)
        if version_names_booking(active) or version_names_booking(draft):
            agents += 1
    if not agents:
        return None
    future = await session.scalar(
        sa.select(sa.func.count())
        .select_from(Appointment)
        .where(Appointment.starts_at > now, Appointment.status.in_(_FUTURE_STATUSES))
    )
    return LegacyClient(
        tenant_id=tenant_id,
        agents=agents,
        future_appointments=int(future or 0),
        reservas_enabled=await reservas_enabled(session, tenant_id),
    )


__all__ = [
    "IMPORT_KEY",
    "LEGACY_PREFIX",
    "MAP_EXTRA",
    "REASONS",
    "RESERVAS_TOOLS",
    "Automatic",
    "ImportResult",
    "LegacyClient",
    "PassReport",
    "PreparedAgent",
    "PublishedAgent",
    "import_appointments",
    "imported_key",
    "legacy_client",
    "name_key",
    "pass_to_reservas",
    "prepare_agent_versions",
    "publish_agent_versions",
    "reservas_enabled",
    "version_names_booking",
]
