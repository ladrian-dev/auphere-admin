"""Los servicios del negocio y quién los ofrece — spec 047, T058 (requisito 11, research D16).

Son los de Reservas (``reservation_services``, spec 043): una sola tabla para la
ficha y la agenda. La ficha añade la descripción, los servicios **no
reservables** (un producto, un menú, una consulta: sin duración) y el tipo de
precio (sin precio, gratis o un importe en la moneda de los precios del
negocio, en unidades menores ISO 4217).

**Quién lo ofrece** (11.2, 11.3, garantía 9):

- un agente «Atiende todos los servicios» (``agents.serves_all_services``)
  conoce todos;
- uno con lista conoce solo los suyos (``agent_services``);
- un servicio sin filas en ``agent_services`` es «Para todos los agentes»: lo
  conocen solo los que atienden todos.

Lo que el agente ve (su prompt compilado, ``reservas.services``, los huecos y
las reservas) sale de :func:`services_for_agent` y :func:`offers`, con el agente
del turno: nunca de un argumento del modelo.

«Eliminar» archiva (11.5): las reservas pasadas guardan el nombre del servicio
(``reservations.service_name``).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final, Literal

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import (
    Agent,
    AgentService,
    AgentStatus,
    ReservationService,
    ReservationServiceStaff,
    ReservationStaff,
    Tenant,
)
from nexus_api.db.models.business import BusinessProfile
from nexus_api.db.models.reservation import PRICE_KINDS
from nexus_api.services.business import client_spec, section_write, writes
from nexus_api.services.business.sections import Actor

NAME_MAX: Final = 120
DESCRIPTION_MAX: Final = 1000
DURATION_MIN, DURATION_MAX, DURATION_STEP = 5, 480, 5
MAX_SERVICES: Final = 500
#: Quien escribe cuando no escribe una persona.
SYSTEM_ACTOR: Final = Actor(kind="system", id="services", origin="system")

#: Monedas sin decimales y con tres (ISO 4217); las demás llevan dos.
ZERO_DECIMALS: Final = frozenset(
    {
        "BIF",
        "CLP",
        "DJF",
        "GNF",
        "ISK",
        "JPY",
        "KMF",
        "KRW",
        "PYG",
        "RWF",
        "UGX",
        "VND",
        "VUV",
        "XAF",
        "XOF",
        "XPF",
    }
)
THREE_DECIMALS: Final = frozenset({"BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND"})
#: Si el negocio no dice su moneda: la de su mercado (Reservas, spec 043).
CURRENCY_BY_MARKET: Final = {
    "CL": "CLP",
    "AR": "ARS",
    "MX": "MXN",
    "CO": "COP",
    "PE": "PEN",
    "ES": "EUR",
}

PriceKind = Literal["none", "free", "amount"]
AgentsMode = Literal["all_agents", "list"]


class ServiceError(ValueError):
    """Un servicio que no se puede guardar: ``422`` con ``code`` y ``field``."""

    def __init__(self, code: str, field: str) -> None:
        super().__init__(f"{field}: {code}")
        self.code = code
        self.field = field


# ── dinero ──────────────────────────────────────────────────────────────────


def exponent(currency: str | None) -> int:
    code = (currency or "").upper()
    if code in ZERO_DECIMALS:
        return 0
    if code in THREE_DECIMALS:
        return 3
    return 2


def _group(digits: str, sep: str) -> str:
    out: list[str] = []
    while len(digits) > 3:
        out.insert(0, digits[-3:])
        digits = digits[:-3]
    out.insert(0, digits)
    return sep.join(out)


def format_amount(amount_minor: int, currency: str, *, locale: str | None = "es") -> str:
    """«15.000 CLP», «15,00 EUR» (o «15.00 EUR» en inglés): los decimales de su
    moneda (requisito 11.7). Determinista: lo usa la compilación."""
    exp = exponent(currency)
    sign = "-" if amount_minor < 0 else ""
    whole, frac = divmod(abs(int(amount_minor)), 10**exp)
    english = (locale or "").lower().startswith("en")
    thousands, decimal = (",", ".") if english else (".", ",")
    text = _group(str(whole), thousands)
    if exp:
        text += decimal + str(frac).zfill(exp)
    return f"{sign}{text} {currency.upper()}"


def price_kind_of(svc: ReservationService) -> PriceKind:
    """El tipo de precio que vale. Una fila con importe y sin tipo (de antes de
    la 0183, o escrita por Reservas) es un importe."""
    if svc.price_kind == "free":
        return "free"
    if svc.price_minor is not None:
        return "amount"
    return "none"


def price_view(svc: ReservationService) -> dict[str, Any]:
    kind = price_kind_of(svc)
    if kind == "amount":
        return {"kind": "amount", "amount_minor": int(svc.price_minor or 0)}
    return {"kind": kind}


async def business_currency(session: AsyncSession, tenant_id: uuid.UUID | None = None) -> str:
    tid = tenant_id or require_current_tenant()
    profile = await session.get(BusinessProfile, tid)
    if profile is not None and profile.price_currency:
        return profile.price_currency
    tenant = await session.get(Tenant, tid)
    market = (tenant.market or "").upper() if tenant else ""
    return CURRENCY_BY_MARKET.get(market, "CLP")


# ── validar ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ServiceData:
    name: str
    bookable: bool = True
    duration_min: int | None = None
    description: str | None = None
    price_kind: str = "none"
    amount_minor: int | None = None
    #: ``None`` = todo el equipo; una lista = esas personas (Reservas).
    staff_ids: tuple[uuid.UUID, ...] | None = None


def validate(data: ServiceData) -> ServiceData:
    name = " ".join((data.name or "").split())
    if not name:
        raise ServiceError("name_required", "name")
    if len(name) > NAME_MAX:
        raise ServiceError("name_too_long", "name")
    description = (data.description or "").strip() or None
    if description and len(description) > DESCRIPTION_MAX:
        raise ServiceError("description_too_long", "description")
    if data.bookable:
        if data.duration_min is None:
            raise ServiceError("duration_required", "duration_min")
        if (
            not DURATION_MIN <= data.duration_min <= DURATION_MAX
            or data.duration_min % DURATION_STEP
        ):
            raise ServiceError("duration_invalid", "duration_min")
    elif data.duration_min is not None:
        raise ServiceError("duration_not_allowed", "duration_min")
    if data.price_kind not in PRICE_KINDS:
        raise ServiceError("price_invalid", "price")
    amount: int | None = None
    if data.price_kind == "amount":
        if data.amount_minor is None:
            raise ServiceError("price_amount_required", "price")
        if data.amount_minor < 0:
            raise ServiceError("price_invalid", "price")
        amount = int(data.amount_minor)
    return ServiceData(
        name=name,
        bookable=data.bookable,
        duration_min=data.duration_min if data.bookable else None,
        description=description,
        price_kind=data.price_kind,
        amount_minor=amount,
        staff_ids=data.staff_ids,
    )


# ── leer ────────────────────────────────────────────────────────────────────


async def list_services(
    session: AsyncSession, *, archived: bool = False
) -> list[ReservationService]:
    stmt = sa.select(ReservationService).where(
        ReservationService.tenant_id == require_current_tenant()
    )
    if not archived:
        stmt = stmt.where(ReservationService.archived_at.is_(None))
    rows = await session.scalars(
        stmt.order_by(ReservationService.position, ReservationService.name)
    )
    return list(rows.all())


async def client_agents(session: AsyncSession) -> list[Agent]:
    """Los agentes del cliente que pueden ofrecer algo (no archivados)."""
    rows = await session.scalars(
        sa.select(Agent)
        .where(
            Agent.tenant_id == require_current_tenant(),
            Agent.status == AgentStatus.ACTIVE.value,
        )
        .order_by(Agent.created_at, Agent.name)
    )
    return list(rows.all())


async def agent_rows(session: AsyncSession) -> dict[uuid.UUID, set[uuid.UUID]]:
    """``service_id`` → los agentes que lo tienen en su lista."""
    rows = await session.execute(
        sa.select(AgentService.service_id, AgentService.agent_id).where(
            AgentService.tenant_id == require_current_tenant()
        )
    )
    out: dict[uuid.UUID, set[uuid.UUID]] = {}
    for service_id, agent_id in rows.all():
        out.setdefault(service_id, set()).add(agent_id)
    return out


def used_by(
    service_id: uuid.UUID, agents: Sequence[Agent], rows: Mapping[uuid.UUID, set[uuid.UUID]]
) -> list[Agent]:
    """«Lo usan»: los que atienden todos y los que lo tienen en su lista."""
    listed = rows.get(service_id, set())
    return [a for a in agents if a.serves_all_services or a.id in listed]


async def services_for_agent(
    session: AsyncSession, agent_id: uuid.UUID | None
) -> list[ReservationService]:
    """Los servicios (vivos) que ofrece ``agent_id``. Sin agente —una prueba,
    una llamada de antes de los agentes— los del agente principal."""
    agent = await _agent_or_principal(session, agent_id)
    services = await list_services(session)
    if agent is None or agent.serves_all_services:
        return services
    mine = set(
        (
            await session.scalars(
                sa.select(AgentService.service_id).where(
                    AgentService.tenant_id == require_current_tenant(),
                    AgentService.agent_id == agent.id,
                )
            )
        ).all()
    )
    return [s for s in services if s.id in mine]


async def offers(session: AsyncSession, agent_id: uuid.UUID | None, service_id: uuid.UUID) -> bool:
    """¿Ofrece el agente del turno este servicio? (garantía 9)."""
    return any(s.id == service_id for s in await services_for_agent(session, agent_id))


async def _agent_or_principal(session: AsyncSession, agent_id: uuid.UUID | None) -> Agent | None:
    tenant_id = require_current_tenant()
    if agent_id is not None:
        agent = await session.get(Agent, agent_id)
        if agent is not None and agent.tenant_id == tenant_id:
            return agent
        return None
    principal: Agent | None = await session.scalar(
        sa.select(Agent)
        .where(Agent.tenant_id == tenant_id, Agent.status == AgentStatus.ACTIVE.value)
        .order_by(Agent.created_at)
        .limit(1)
    )
    return principal


async def staff_of(session: AsyncSession, service_id: uuid.UUID) -> list[uuid.UUID]:
    rows = await session.scalars(
        sa.select(ReservationServiceStaff.staff_id).where(
            ReservationServiceStaff.tenant_id == require_current_tenant(),
            ReservationServiceStaff.service_id == service_id,
        )
    )
    return sorted(rows.all(), key=str)


async def assignments(session: AsyncSession) -> dict[str, Any]:
    """Quién ofrece qué: los agentes que atienden todos y las listas. No está en
    el ClientSpec (es del agente), pero cambia lo que cada agente sabe."""
    agents = await client_agents(session)
    rows = await agent_rows(session)
    return {
        "serves_all": sorted(str(a.id) for a in agents if a.serves_all_services),
        "by_service": {
            str(service_id): sorted(str(a) for a in agent_ids)
            for service_id, agent_ids in sorted(rows.items(), key=lambda kv: str(kv[0]))
        },
    }


async def section_view(session: AsyncSession) -> dict[str, Any]:
    """Lo que guarda el historial: la sección del ClientSpec y quién la ofrece."""
    return {
        **await client_spec.section_view(session, "services"),
        "assignments": await assignments(session),
    }


# ── escribir ────────────────────────────────────────────────────────────────


async def _write(
    session: AsyncSession,
    *,
    actor: Actor,
    ctx: writes.WriteContext | None,
    expected_revision: int | None,
    pointers: list[str],
    change: Any,
) -> writes.SectionWritten | None:
    return await section_write.guarded_write(
        session,
        "services",
        ctx=section_write.context(actor, ctx),
        change=change,
        pointers=pointers,
        expected_revision=expected_revision,
        view=lambda: section_view(session),
    )


def _assign(svc: ReservationService, data: ServiceData) -> None:
    svc.name = data.name
    svc.description = data.description
    svc.bookable = data.bookable
    svc.duration_minutes = data.duration_min
    svc.price_kind = data.price_kind
    svc.price_minor = data.amount_minor if data.price_kind == "amount" else None


async def _set_staff(
    session: AsyncSession, svc: ReservationService, staff_ids: Sequence[uuid.UUID] | None
) -> None:
    tenant_id = require_current_tenant()
    await session.execute(
        sa.delete(ReservationServiceStaff).where(
            ReservationServiceStaff.tenant_id == tenant_id,
            ReservationServiceStaff.service_id == svc.id,
        )
    )
    svc.all_staff = staff_ids is None
    for staff_id in staff_ids or ():
        member = await session.get(ReservationStaff, staff_id)
        if member is None or member.tenant_id != tenant_id:
            raise ServiceError("unknown_staff", "staff")
        session.add(
            ReservationServiceStaff(tenant_id=tenant_id, service_id=svc.id, staff_id=staff_id)
        )


async def create_service(
    session: AsyncSession,
    data: ServiceData,
    *,
    actor: Actor,
    expected_revision: int | None = None,
    ctx: writes.WriteContext | None = None,
    service_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID, writes.SectionWritten | None]:
    clean = validate(data)
    existing = await list_services(session, archived=True)
    if len([s for s in existing if s.archived_at is None]) >= MAX_SERVICES:
        raise ServiceError("too_many_services", "name")
    svc = ReservationService(
        id=service_id or uuid.uuid4(),
        tenant_id=require_current_tenant(),
        currency=await business_currency(session),
        all_staff=True,
        position=max((s.position for s in existing), default=0) + 1,
    )
    _assign(svc, clean)

    async def change() -> None:
        session.add(svc)
        await session.flush()
        if clean.staff_ids is not None:
            await _set_staff(session, svc, clean.staff_ids)

    written = await _write(
        session,
        actor=actor,
        ctx=ctx,
        expected_revision=expected_revision,
        pointers=[f"/services/{svc.id}"],
        change=change,
    )
    return svc.id, written


async def get_service(session: AsyncSession, service_id: uuid.UUID) -> ReservationService:
    svc = await session.get(ReservationService, service_id)
    if svc is None or svc.tenant_id != require_current_tenant():
        raise LookupError("unknown service")
    return svc


async def update_service(
    session: AsyncSession,
    service_id: uuid.UUID,
    changes: Mapping[str, Any],
    *,
    actor: Actor,
    expected_revision: int | None = None,
    ctx: writes.WriteContext | None = None,
) -> writes.SectionWritten | None:
    """``changes``: ``name``, ``description``, ``bookable``, ``duration_min``,
    ``price`` (``{kind, amount_minor?}``) o ``staff`` (``"all"`` o ids); lo que
    no llega se queda. Pasar a no reservable quita la duración. ``archived:
    false`` deshace un archivado (lo usa el deshacer)."""
    svc = await get_service(session, service_id)
    if svc.archived_at is not None and changes.get("archived") is not False:
        raise LookupError("archived service")
    bookable = bool(changes.get("bookable", svc.bookable))
    duration = changes.get("duration_min", svc.duration_minutes)
    if not bookable and "duration_min" not in changes:
        duration = None
    price = changes.get("price")
    kind = price.get("kind") if isinstance(price, Mapping) else price_kind_of(svc)
    amount = price.get("amount_minor") if isinstance(price, Mapping) else svc.price_minor
    clean = validate(
        ServiceData(
            name=changes.get("name", svc.name),
            bookable=bookable,
            duration_min=duration,
            description=changes.get("description", svc.description),
            price_kind=str(kind),
            amount_minor=amount,
        )
    )
    staff = changes.get("staff", "keep")

    async def change() -> None:
        _assign(svc, clean)
        if changes.get("archived") is False:
            svc.archived_at = None
        if staff != "keep":
            await _set_staff(
                session, svc, None if staff == "all" else [uuid.UUID(str(s)) for s in staff]
            )

    return await _write(
        session,
        actor=actor,
        ctx=ctx,
        expected_revision=expected_revision,
        pointers=[f"/services/{service_id}/{key}" for key in changes if key != "archived"],
        change=change,
    )


async def archive_service(
    session: AsyncSession,
    service_id: uuid.UUID,
    *,
    actor: Actor,
    expected_revision: int | None = None,
    ctx: writes.WriteContext | None = None,
) -> writes.SectionWritten | None:
    """«Eliminar» (11.5): archiva; las reservas pasadas guardan el nombre."""
    svc = await get_service(session, service_id)

    async def change() -> None:
        if svc.archived_at is None:
            svc.archived_at = datetime.now(UTC)

    return await _write(
        session,
        actor=actor,
        ctx=ctx,
        expected_revision=expected_revision,
        pointers=[f"/services/{service_id}"],
        change=change,
    )


async def duplicate_service(
    session: AsyncSession,
    service_id: uuid.UUID,
    *,
    actor: Actor,
    expected_revision: int | None = None,
    suffix: str = " (copia)",
) -> tuple[uuid.UUID, writes.SectionWritten | None]:
    """Duplicar (11.6): los mismos datos, el mismo equipo y los mismos agentes."""
    src = await get_service(session, service_id)
    existing = await list_services(session, archived=True)
    name = (src.name + suffix) if len(src.name) + len(suffix) <= NAME_MAX else src.name
    copy = ReservationService(
        id=uuid.uuid4(),
        tenant_id=src.tenant_id,
        name=name,
        description=src.description,
        bookable=src.bookable,
        duration_minutes=src.duration_minutes,
        price_kind=price_kind_of(src),
        price_minor=src.price_minor if price_kind_of(src) == "amount" else None,
        currency=src.currency,
        all_staff=src.all_staff,
        position=max((s.position for s in existing), default=0) + 1,
    )
    staff = await staff_of(session, src.id)
    agents = (await agent_rows(session)).get(src.id, set())

    async def change() -> None:
        session.add(copy)
        await session.flush()
        for staff_id in staff:
            session.add(
                ReservationServiceStaff(
                    tenant_id=copy.tenant_id, service_id=copy.id, staff_id=staff_id
                )
            )
        for agent_id in sorted(agents, key=str):
            session.add(
                AgentService(tenant_id=copy.tenant_id, agent_id=agent_id, service_id=copy.id)
            )

    written = await _write(
        session,
        actor=actor,
        ctx=None,
        expected_revision=expected_revision,
        pointers=[f"/services/{copy.id}"],
        change=change,
    )
    return copy.id, written


async def _replace_service_agents(
    session: AsyncSession, service_id: uuid.UUID, agent_ids: Sequence[uuid.UUID]
) -> None:
    tenant_id = require_current_tenant()
    await session.execute(
        sa.delete(AgentService).where(
            AgentService.tenant_id == tenant_id, AgentService.service_id == service_id
        )
    )
    for agent_id in agent_ids:
        session.add(AgentService(tenant_id=tenant_id, agent_id=agent_id, service_id=service_id))


async def set_service_agents(
    session: AsyncSession,
    service_id: uuid.UUID,
    *,
    mode: str,
    agent_ids: Sequence[uuid.UUID],
    actor: Actor,
    expected_revision: int | None = None,
    ctx: writes.WriteContext | None = None,
) -> writes.SectionWritten | None:
    """``PUT /services/{id}/agents``: «Para todos los agentes» (sin lista) o una
    lista de agentes del cliente."""
    svc = await get_service(session, service_id)
    if mode not in ("all_agents", "list"):
        raise ServiceError("agents_mode_invalid", "mode")
    wanted: list[uuid.UUID] = []
    if mode == "list":
        known = {a.id for a in await client_agents(session)}
        for agent_id in agent_ids:
            if agent_id not in known:
                raise ServiceError("unknown_agent", "agent_ids")
            if agent_id not in wanted:
                wanted.append(agent_id)
        if not wanted:
            raise ServiceError("agents_required", "agent_ids")

    async def change() -> None:
        await _replace_service_agents(session, svc.id, wanted)

    return await _write(
        session,
        actor=actor,
        ctx=ctx,
        expected_revision=expected_revision,
        pointers=[f"/services/{service_id}/agents"],
        change=change,
    )


async def set_agent_services(
    session: AsyncSession,
    agent_id: uuid.UUID,
    *,
    serves_all: bool,
    service_ids: Sequence[uuid.UUID] = (),
    actor: Actor,
    expected_revision: int | None = None,
    ctx: writes.WriteContext | None = None,
) -> writes.SectionWritten | None:
    """Desde el agente: «Atiende todos los servicios» o su lista (11.2)."""
    agent = await session.get(Agent, agent_id)
    tenant_id = require_current_tenant()
    if agent is None or agent.tenant_id != tenant_id:
        raise LookupError("unknown agent")
    live = {s.id for s in await list_services(session)}
    wanted = list(dict.fromkeys(service_ids))
    if any(s not in live for s in wanted):
        raise ServiceError("unknown_service", "service_ids")

    async def change() -> None:
        agent.serves_all_services = serves_all
        if not serves_all:
            await session.execute(
                sa.delete(AgentService).where(
                    AgentService.tenant_id == tenant_id, AgentService.agent_id == agent_id
                )
            )
            for service_id in wanted:
                session.add(
                    AgentService(tenant_id=tenant_id, agent_id=agent_id, service_id=service_id)
                )

    return await _write(
        session,
        actor=actor,
        ctx=ctx,
        expected_revision=expected_revision,
        pointers=[],
        change=change,
    )


async def note_reservas_write(
    session: AsyncSession, *, actor: Actor, before: dict[str, Any]
) -> writes.SectionWritten | None:
    """Reservas (la consola lite y la app) escribió un servicio por su cuenta:
    se anota como cambio de la ficha para que los agentes lo usen ya."""
    await section_write.ensure_profile(session)
    for svc in await list_services(session, archived=True):
        svc.price_kind = price_kind_of(svc)
    await session.flush()
    after = await section_view(session)
    if after == before:
        return None
    return await writes.write_section(
        session,
        "services",
        actor=actor,
        before=before,
        after=after,
        pointers=[],
        state="complete",
    )


# ── adaptadores: deshacer y aplicar propuestas o lo leído ──────────────────


def _uuid(raw: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(raw))
    except (TypeError, ValueError):
        return None


def _data_of(item: Mapping[str, Any]) -> ServiceData:
    raw_price = item.get("price")
    price: Mapping[str, Any] = raw_price if isinstance(raw_price, Mapping) else {"kind": "none"}
    staff = item.get("staff", "all")
    amount = price.get("amount_minor")
    return ServiceData(
        name=str(item.get("name") or ""),
        bookable=bool(item.get("bookable", True)),
        duration_min=item.get("duration_min"),
        description=item.get("description"),
        price_kind=str(price.get("kind") or "none"),
        amount_minor=int(amount) if amount is not None else None,
        staff_ids=None
        if staff == "all" or not isinstance(staff, list)
        else tuple(u for u in (_uuid(s) for s in staff) if u is not None),
    )


async def _restore_section(
    session: AsyncSession, view: Mapping[str, Any] | None, ctx: writes.WriteContext
) -> writes.SectionWritten:
    """La sección vuelve a ``view``: lo que no está, se archiva (las reservas
    pasadas no pierden su servicio); y, si la vista lo trae, quién lo ofrece."""
    target = list((view or {}).get("services") or [])
    wanted = {_uuid(item.get("id")): item for item in target if _uuid(item.get("id"))}
    last: writes.SectionWritten | None = None
    for svc in await list_services(session, archived=True):
        item = wanted.pop(svc.id, None)
        if item is None:
            if svc.archived_at is None:
                last = await archive_service(session, svc.id, actor=ctx.actor, ctx=ctx) or last
            continue
        changes: dict[str, Any] = {
            k: item.get(k)
            for k in ("name", "description", "bookable", "duration_min", "price", "staff")
            if k in item
        }
        changes.setdefault("description", None)
        changes.setdefault("duration_min", None)
        if bool(item.get("archived")):
            last = await archive_service(session, svc.id, actor=ctx.actor, ctx=ctx) or last
        else:
            changes["archived"] = False
            last = await update_service(session, svc.id, changes, actor=ctx.actor, ctx=ctx) or last
    for service_id, item in wanted.items():
        _new, written = await create_service(
            session, _data_of(item), actor=ctx.actor, ctx=ctx, service_id=service_id
        )
        last = written or last
    plan = (view or {}).get("assignments")
    if isinstance(plan, Mapping):
        by_service = plan.get("by_service") or {}
        serves_all = set(plan.get("serves_all") or [])

        async def reassign() -> None:
            for agent in await client_agents(session):
                agent.serves_all_services = str(agent.id) in serves_all
            for svc in await list_services(session, archived=True):
                ids = [u for u in (_uuid(a) for a in by_service.get(str(svc.id), [])) if u]
                await _replace_service_agents(session, svc.id, ids)

        last = (
            await _write(
                session,
                actor=ctx.actor,
                ctx=ctx,
                expected_revision=None,
                pointers=[],
                change=reassign,
            )
            or last
        )
    if last is None:
        raise writes.NothingWritten
    return last


async def _apply_ops(
    session: AsyncSession, ops: Sequence[writes.Op], ctx: writes.WriteContext
) -> writes.SectionWritten:
    last: writes.SectionWritten | None = None
    for op in ops:
        parts = op.path.split("/")[1:]
        value = op.value if isinstance(op.value, Mapping) else {}
        if parts[:1] != ["services"]:
            raise ServiceError("invalid_pointer", "path")
        if op.op == "add" and parts[1:] == ["-"]:
            _new, written = await create_service(session, _data_of(value), actor=ctx.actor, ctx=ctx)
            last = written or last
            continue
        service_id = _uuid(parts[1]) if len(parts) > 1 else None
        if service_id is None:
            raise ServiceError("invalid_pointer", "path")
        if op.op == "archive":
            last = await archive_service(session, service_id, actor=ctx.actor, ctx=ctx) or last
        elif op.op == "replace" and len(parts) == 2:
            last = (
                await update_service(session, service_id, dict(value), actor=ctx.actor, ctx=ctx)
                or last
            )
        elif op.op == "replace" and len(parts) == 3:
            last = (
                await update_service(
                    session, service_id, {parts[2]: op.value}, actor=ctx.actor, ctx=ctx
                )
                or last
            )
        else:
            raise ServiceError("invalid_pointer", "path")
    if last is None:
        raise writes.NothingWritten
    return last


writes.register_section_adapter("services", restore=_restore_section, apply=_apply_ops)

__all__ = [
    "CURRENCY_BY_MARKET",
    "SYSTEM_ACTOR",
    "ServiceData",
    "ServiceError",
    "agent_rows",
    "archive_service",
    "assignments",
    "business_currency",
    "client_agents",
    "create_service",
    "duplicate_service",
    "exponent",
    "format_amount",
    "get_service",
    "list_services",
    "note_reservas_write",
    "offers",
    "price_kind_of",
    "price_view",
    "section_view",
    "services_for_agent",
    "set_agent_services",
    "set_service_agents",
    "staff_of",
    "update_service",
    "used_by",
    "validate",
]
