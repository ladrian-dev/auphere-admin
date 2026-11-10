"""Demo de la consola de clientes con Reservas en sus dos modos (solo desarrollo).

Siembra, en la base de ``NEXUS_DATABASE_URL``, todo lo que hace falta para
entrar en la consola de clientes (``apps/console``) como la persona de un
cliente y ver Panel, Bandeja, Reservas y Consumo con datos de un piloto
chileno (CLP, teléfonos +56, nombres en español):

- el partner «Auphere Demo Partner» con la consola encendida y su dueño
  (``socio@demo.test``);
- «Peluquería Cultor» (``demo-cultor``): Reservas en modo **Servicios**, con
  Lucía, Marcos y Nora, tres servicios y una semana de citas (una cancelada y
  una en lista de espera para adelantar); la persona ``valeria@cultor.test``;
- «Restaurante La Fonda» (``demo-fonda``): Reservas en modo **Aforo**
  (restaurante) con turnos de Comida y Cena, una semana de reservas, llegadas
  de hoy, una llegada sin reserva, un bloqueo y lista de espera en una hora
  llena; la persona ``carla@lafonda.test``;
- en los dos: un WhatsApp (Meta), un agente con versión activa, conversaciones
  atendidas (una esperando a una persona), saldo del partner, tope del
  cliente y algo de gasto del mes.

Todo pasa por los servicios de verdad: el acceso del cliente por
``services/client_access.set_access`` (como el admin, con el modo de Reservas
en la misma llamada); las reservas por ``services/reservations/core`` bajo la
RLS del cliente (``tenant_scoped_session``), con su candado y su revalidación;
el escalado por ``services/inbox_lifecycle``; el saldo por el libro
(``metering/wallet``).

Uso (lee NEXUS_DATABASE_URL del entorno):

    uv run python scripts/dev_seed_reservas_demo.py [--password '...'] \\
        [--console-origin http://localhost:3111]

Se puede repetir: lo que ya existe se reutiliza (por slug, correo, nombre,
teléfono o clave de idempotencia) y las contraseñas vuelven a ser la impresa.
Las reservas llevan la fecha del día en su clave: repetirlo otro día añade la
semana de ese día sobre la anterior, respetando los huecos ya ocupados.

Solo para desarrollo: se niega a correr con ``NEXUS_ENVIRONMENT`` de
producción.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import sqlalchemy as sa
import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexus_api.config import get_settings
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_engine, get_sessionmaker
from nexus_api.db.models import (
    Agent,
    AgentConfig,
    AgentConfigStatus,
    Channel,
    ChannelStatus,
    ChannelType,
    ClientMembership,
    ClientMemberStatus,
    ConsoleAccount,
    Conversation,
    ConversationEvent,
    ConversationStatus,
    Customer,
    InboxRead,
    MembershipStatus,
    Message,
    MessageDirection,
    MessageStatus,
    Partner,
    PartnerMembership,
    PartnerRole,
    PartnerSubscription,
    PartnerTenant,
    Reservation,
    ReservationBlock,
    ReservationService,
    ReservationServiceStaff,
    ReservationSettings,
    ReservationStaff,
    ReservationWaitlist,
    Tenant,
    TenantPlan,
    TenantStatus,
)
from nexus_api.db.models.partner_wallet import KIND_CREDIT_ADMIN
from nexus_api.metering import wallet as book
from nexus_api.services import client_access, console_identity, inbox_lifecycle
from nexus_api.services.client_access import ClientAccessError
from nexus_api.services.console_v2 import born_on_new_console
from nexus_api.services.reservations import core, engine, waitlist
from nexus_api.services.reservations.admin import RESERVAS_TOOLS, Choice
from nexus_api.services.reservations.settings import apply_patch

ACTOR = "operator:dev-seed@auphere.local"
DEFAULT_PASSWORD = "demo-demo-1234"
DEFAULT_CONSOLE_ORIGIN = "http://localhost:3111"
KEY_PREFIX = "demo-seed"
TZ_NAME = "America/Santiago"
MODULES = ["panel", "inbox", "reservas", "usage"]

PARTNER_SLUG = "auphere-demo"
PARTNER_NAME = "Auphere Demo Partner"
OWNER_EMAIL = "socio@demo.test"
OWNER_NAME = "Rodrigo Alarcón"

#: El libro cuenta en créditos: 1 000 créditos = 1 centavo de US$.
TOP_UP_CREDITS = 5_000_000  # US$ 50 de saldo recargado del partner
CREDITS_PER_USD = 100_000

AGENT = core.Actor("agent", "Agente de reservas")
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
DAY_NAMES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")

Span = tuple[str, str]


def _week(weekdays: Sequence[Span], saturday: Sequence[Span], sunday: Sequence[Span]) -> Any:
    """Un horario semanal en la forma canónica (``services/business_hours``)."""

    def ranges(spans: Sequence[Span]) -> list[dict[str, str]]:
        return [{"from": a, "to": b} for a, b in spans]

    out = {d: ranges(weekdays) for d in WEEKDAYS[:5]}
    out["saturday"] = ranges(saturday)
    out["sunday"] = ranges(sunday)
    return out


def _hm(raw: str) -> time:
    h, m = raw.split(":")
    return time(int(h), int(m))


def _day_label(d: date) -> str:
    return f"{DAY_NAMES[d.weekday()]} {d.day}"


def say(msg: str) -> None:
    print(msg, flush=True)


# ── los dos clientes ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ClientSpec:
    slug: str
    name: str
    person_email: str
    person_name: str
    number: str  # el WhatsApp del negocio, E.164
    agent_name: str
    prompt: str
    hours: dict[str, list[dict[str, str]]]
    choice: Choice
    cap_credits: int  # tope mensual del cliente
    spend: tuple[int, ...]  # gasto del mes en el canal, en créditos


CULTOR = ClientSpec(
    slug="demo-cultor",
    name="Peluquería Cultor",
    person_email="valeria@cultor.test",
    person_name="Valeria Ríos",
    number="+56932100001",
    agent_name="Asistente Cultor",
    prompt=(
        "Eres el asistente de Peluquería Cultor, en Providencia (Santiago). "
        "Atiendes por WhatsApp, agendas cortes, barba y color con Lucía, Marcos "
        "o Nora, y pasas a una persona lo que no puedes resolver."
    ),
    hours=_week([("09:00", "19:00")], [("09:00", "14:00")], []),
    choice=Choice(mode="services"),
    cap_credits=2_000_000,  # US$ 20
    spend=tuple(18_000 + (i * 7_919) % 27_000 for i in range(16)),
)

FONDA = ClientSpec(
    slug="demo-fonda",
    name="Restaurante La Fonda",
    person_email="carla@lafonda.test",
    person_name="Carla Medina",
    number="+56932100002",
    agent_name="Asistente La Fonda",
    prompt=(
        "Eres el asistente de Restaurante La Fonda, en Ñuñoa (Santiago). Tomas "
        "reservas para Comida y Cena por WhatsApp, respondes dudas de la carta y "
        "pasas a una persona los grupos grandes y lo que no puedes resolver."
    ),
    hours=_week([("12:00", "23:30")], [("12:00", "23:30")], [("12:00", "23:30")]),
    choice=Choice(mode="capacity", capacity_kind="restaurant"),
    cap_credits=1_500_000,  # US$ 15
    spend=tuple(14_000 + (i * 5_413) % 21_000 for i in range(10)),
)

#: Servicios: el equipo de Cultor. Lucía con pausa de 14 a 15 y sin sábados;
#: Marcos y Nora con el horario del negocio (``hours = NULL``).
CULTOR_STAFF: tuple[tuple[str, Any], ...] = (
    ("Lucía", _week([("09:00", "14:00"), ("15:00", "19:00")], [], [])),
    ("Marcos", None),
    ("Nora", None),
)
#: (nombre, minutos, precio CLP, solo estas personas o ``None`` = todo el equipo)
CULTOR_SERVICES: tuple[tuple[str, int, int, tuple[str, ...] | None], ...] = (
    ("Corte", 30, 15_000, None),
    ("Corte y barba", 45, 22_000, None),
    ("Color", 90, 45_000, ("Nora", "Lucía")),
)

#: Aforo: La Fonda parte de los valores de restaurante y los ajusta a su sala.
FONDA_CAPACITY = {
    "seats": 36,
    "walkin_hold": 4,
    "schedule": {
        "model": "shifts",
        "step_minutes": 30,
        "shifts": [
            {"name": "Comida", "from": "13:00", "to": "15:00"},
            {"name": "Cena", "from": "20:00", "to": "22:30"},
        ],
    },
}


# ── reservas y conversaciones ───────────────────────────────────────────────


@dataclass(frozen=True)
class ServiceBooking:
    key: str
    offset: int  # días desde hoy (en Cultor, un domingo pasa al lunes)
    at: str
    service: str
    staff: str | None  # None = cualquiera
    name: str
    phone: str
    origin: str  # agent | person
    status: str | None = None
    note: str | None = None
    waitlist: bool = False
    cancel: bool = False


@dataclass(frozen=True)
class TableBooking:
    key: str
    offset: int
    at: str
    party: int
    name: str
    phone: str
    origin: str
    status: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class ConvSpec:
    name: str
    phone: str
    ago: timedelta  # el primer mensaje del contacto
    turns: tuple[str, ...]  # alternos, empieza el contacto
    outcome: str = "open"  # open | escalated | resolved
    reason: str | None = None
    summary: str | None = None
    read: bool = False


@dataclass(frozen=True)
class Linked:
    conversation_id: uuid.UUID
    customer_id: uuid.UUID


CULTOR_BOOKINGS = (
    ServiceBooking("c01", 0, "09:30", "Corte", "Marcos", "Javiera Muñoz", "+56987650101", "person"),
    ServiceBooking(
        "c02", 0, "10:00", "Color", "Lucía", "Constanza Pérez", "+56991234502", "agent", "confirmed"
    ),
    ServiceBooking(
        "c03",
        0,
        "12:00",
        "Corte y barba",
        "Marcos",
        "Tomás Herrera",
        "+56991234503",
        "agent",
        "pending",
    ),
    ServiceBooking("c04", 0, "15:30", "Corte", "Nora", "Francisca Soto", "+56987650104", "person"),
    ServiceBooking(
        "c05", 0, "17:00", "Color", "Nora", "Catalina Rojas", "+56991234504", "agent", "pending"
    ),
    ServiceBooking(
        "c06", 1, "09:00", "Corte", "Lucía", "Ignacio Fuentes", "+56987650106", "agent", "confirmed"
    ),
    ServiceBooking(
        "c07",
        1,
        "11:30",
        "Corte y barba",
        "Marcos",
        "Benjamín Castro",
        "+56987650107",
        "person",
        note="Barba corta, perfilada",
    ),
    ServiceBooking(
        "c08", 1, "16:00", "Color", "Lucía", "Isidora Morales", "+56991234501", "agent", "confirmed"
    ),
    ServiceBooking("c09", 2, "10:30", "Corte", "Nora", "Martina Vargas", "+56987650109", "person"),
    ServiceBooking(
        "c10", 2, "12:00", "Corte", None, "Vicente Reyes", "+56987650110", "agent", "pending"
    ),
    ServiceBooking(
        "c11",
        3,
        "17:00",
        "Color",
        "Nora",
        "Antonia Silva",
        "+56991234506",
        "agent",
        "confirmed",
        waitlist=True,
    ),
    ServiceBooking(
        "c12",
        4,
        "10:00",
        "Corte y barba",
        "Marcos",
        "Matías González",
        "+56987650112",
        "person",
        cancel=True,
    ),
    ServiceBooking(
        "c13", 5, "11:00", "Corte", None, "Sofía Contreras", "+56987650113", "agent", "pending"
    ),
    ServiceBooking(
        "c14", 6, "12:30", "Corte", "Lucía", "Agustín Navarro", "+56987650114", "person"
    ),
)

#: La hora llena de La Fonda: pasado mañana a las 21:00 (8 + 8 + 6 + 6 + 4 =
#: 32 = 36 sitios menos 4 guardados para quien llega sin reserva).
FULL_OFFSET = 2
FULL_AT = "21:00"
BLOCK_OFFSET = 4

FONDA_BOOKINGS = (
    TableBooking("f01", 0, "13:00", 4, "Rodrigo Díaz", "+56987650201", "person"),
    TableBooking("f02", 0, "13:30", 2, "Josefa Bravo", "+56987650202", "agent", "confirmed"),
    TableBooking(
        "f03", 0, "14:00", 6, "Familia Henríquez", "+56987650203", "person", note="Silla de bebé"
    ),
    TableBooking("f04", 0, "20:00", 2, "Cristóbal Muñoz", "+56987650204", "person"),
    TableBooking("f05", 0, "20:30", 4, "Diego Araya", "+56992345601", "agent", "pending"),
    TableBooking("f06", 0, "21:00", 5, "Valentina Pizarro", "+56987650206", "agent", "confirmed"),
    TableBooking("f07", 1, "20:30", 6, "Gonzalo Tapia", "+56987650207", "agent", "pending"),
    TableBooking("f08", 1, "21:00", 4, "Daniela Rivas", "+56987650208", "person"),
    TableBooking(
        "f09",
        FULL_OFFSET,
        FULL_AT,
        8,
        "Andrés Fernández",
        "+56987650209",
        "person",
        note="Cumpleaños: llevan torta",
    ),
    TableBooking(
        "f10", FULL_OFFSET, FULL_AT, 8, "Macarena Soto", "+56987650210", "agent", "confirmed"
    ),
    TableBooking("f11", FULL_OFFSET, FULL_AT, 6, "Nicolás Vidal", "+56987650211", "person"),
    TableBooking(
        "f12", FULL_OFFSET, FULL_AT, 6, "Carolina Espinoza", "+56987650212", "agent", "confirmed"
    ),
    TableBooking("f13", FULL_OFFSET, FULL_AT, 4, "Sebastián Lagos", "+56987650213", "person"),
    TableBooking("f14", 3, "13:30", 3, "Ignacia Molina", "+56987650214", "person"),
    TableBooking("f15", 5, "21:00", 2, "Joaquín Rojas", "+56987650215", "agent", "pending"),
)


def cultor_conversations(antonia_day: date) -> list[ConvSpec]:
    return [
        ConvSpec(
            "Isidora Morales",
            "+56991234501",
            timedelta(minutes=35),
            (
                "Hola, tengo hora mañana a las 16:00 con Lucía para color. "
                "¿Me la pueden pasar a las 11?",
                "Hola Isidora. Revisé la agenda de Lucía y mañana a las 11:00 no "
                "tiene hueco. ¿Te sirve a esa hora con Nora, o prefieres otro día "
                "con Lucía?",
                "No, quiero con Lucía sí o sí. ¿No hay forma de que me hagan un espacio?",
                "Entiendo. Le paso tu mensaje al equipo para que lo vean "
                "directamente; te escriben por aquí apenas puedan.",
            ),
            outcome="escalated",
            reason="Pide cambiar la hora de su cita de mañana y no hay hueco con Lucía.",
            summary="Cliente habitual",
        ),
        ConvSpec(
            "Tomás Herrera",
            "+56991234503",
            timedelta(hours=3),
            (
                "Buenas, ¿cuánto cuesta corte y barba?",
                "Hola Tomás. Corte y barba cuesta $22.000 y dura 45 minutos. "
                "¿Quieres que te busque hora?",
                "Dale, hoy a mediodía si se puede",
                "Te dejé hoy a las 12:00 con Marcos. ¿Me confirmas que vienes?",
            ),
        ),
        ConvSpec(
            "Catalina Rojas",
            "+56991234504",
            timedelta(hours=5),
            (
                "Hola, ¿tienen hora para color hoy en la tarde?",
                "Hola Catalina. Nora tiene hora hoy a las 17:00 para Color "
                "($45.000, 90 minutos). ¿Te la dejo reservada?",
                "Sí, porfa",
                "Listo, quedó reservada a las 17:00 con Nora. Más tarde te pido confirmación.",
            ),
            read=True,
        ),
        ConvSpec(
            "Constanza Pérez",
            "+56991234502",
            timedelta(hours=16),
            (
                "Hola! Quería hora para color mañana temprano",
                "Hola Constanza. Lucía tiene hora mañana a las 10:00 para Color "
                "(90 minutos, $45.000). ¿Te la reservo?",
                "Sí, perfecto",
                "Listo, quedaste agendada a las 10:00 con Lucía. Te esperamos en "
                "Peluquería Cultor.",
            ),
            read=True,
        ),
        ConvSpec(
            "Antonia Silva",
            "+56991234506",
            timedelta(days=1, hours=2),
            (
                "Hola, quiero hora para color con Nora esta semana",
                f"Hola Antonia. Lo primero que tiene Nora es el {_day_label(antonia_day)} "
                "a las 17:00. ¿Te sirve?",
                "Ya, pero si se libera algo antes me avisan",
                f"Hecho: te reservé el {_day_label(antonia_day)} a las 17:00 y te anoté "
                "en la lista de espera. Si se libera algo antes te escribo por aquí.",
            ),
            read=True,
        ),
        ConvSpec(
            "Fernanda Lagos",
            "+56991234505",
            timedelta(days=2, hours=4),
            (
                "Hola, ¿atienden los domingos?",
                "Hola Fernanda. Los domingos estamos cerrados. De lunes a viernes "
                "atendemos de 9:00 a 19:00 y los sábados de 9:00 a 14:00.",
                "Ok, gracias!",
                "De nada. Cuando quieras te busco hora.",
            ),
            outcome="resolved",
            read=True,
        ),
    ]


def fonda_conversations(full_day: date) -> list[ConvSpec]:
    full = _day_label(full_day)
    return [
        ConvSpec(
            "Paula Carrasco",
            "+56992345602",
            timedelta(minutes=50),
            (
                f"Hola, quiero reservar para 14 personas el {full} en la noche, es un cumpleaños",
                "Hola Paula. Los grupos de más de 10 personas los gestiona "
                "directamente el equipo del restaurante. Les paso tu solicitud y "
                "te escriben por aquí.",
            ),
            outcome="escalated",
            reason=f"Quiere reservar para 14 personas el {full}; el máximo por reserva es 10.",
            summary="Primera vez que escribe; cumpleaños",
        ),
        ConvSpec(
            "Diego Araya",
            "+56992345601",
            timedelta(hours=1, minutes=20),
            (
                "Hola! ¿Tienen mesa para 4 hoy a las 20:30?",
                "Hola Diego. Sí, hay sitio hoy a las 20:30 para 4 personas. ¿Te la "
                "reservo a tu nombre?",
                "Sí, a nombre de Diego Araya",
                "Listo, mesa para 4 hoy a las 20:30. Te escribimos antes para confirmar.",
            ),
        ),
        ConvSpec(
            "Felipe Sepúlveda",
            "+56992345603",
            timedelta(hours=4),
            (
                f"Buenas, ¿hay mesa para 2 el {full} a las 21:00?",
                f"Hola Felipe. El {full} a las 21:00 estamos completos. Puedo "
                "anotarte en la lista de espera y te aviso por aquí si se libera "
                "sitio. ¿Te anoto?",
                "Sí, porfa",
                "Listo, estás en la lista de espera para 2 personas a las 21:00.",
            ),
            read=True,
        ),
        ConvSpec(
            "Camila Ortiz",
            "+56992345604",
            timedelta(days=3, hours=1),
            (
                "Hola, ¿tienen opciones vegetarianas?",
                "Hola Camila. Sí: pastel de choclo vegetariano, porotos granados y "
                "ensaladas de temporada.",
                "Buenísimo, gracias",
                "A ti. Si quieres reservar, dime el día y la hora.",
            ),
            outcome="resolved",
            read=True,
        ),
    ]


# ── partner, cuentas y cliente (sesión de plataforma, sin RLS) ──────────────


async def ensure_account(
    session: AsyncSession, email: str, password: str, name: str
) -> ConsoleAccount:
    account = await console_identity.get_by_email(session, email)
    if account is None:
        account = await console_identity.create_account(
            session, email=email, password=password, display_name=name
        )
        say(f"  cuenta {email} creada")
    else:
        await console_identity.set_password(session, account, password)
        say(f"  cuenta {email} ya existía: contraseña repuesta")
    return account


async def ensure_partner(session: AsyncSession, password: str, now: datetime) -> Partner:
    partner = await session.scalar(sa.select(Partner).where(Partner.slug == PARTNER_SLUG))
    if partner is None:
        partner = born_on_new_console(
            Partner(
                id=uuid.uuid4(),
                name=PARTNER_NAME,
                slug=PARTNER_SLUG,
                contact_email=OWNER_EMAIL,
                console_enabled=True,
            )
        )
        session.add(partner)
        await session.flush()  # el trigger trg_partners_seed_wallet crea su libro
        say(f"partner {PARTNER_NAME} creado")
    else:
        say(f"partner {PARTNER_NAME} ya existía")
    partner.console_enabled = True
    partner.status = "active"
    if await session.get(PartnerSubscription, partner.id) is None:
        session.add(
            PartnerSubscription(partner_id=partner.id, tier_code="business", state="current")
        )

    account = await ensure_account(session, OWNER_EMAIL, password, OWNER_NAME)
    member = await session.scalar(
        sa.select(PartnerMembership).where(
            PartnerMembership.partner_id == partner.id, PartnerMembership.email == OWNER_EMAIL
        )
    )
    if member is None:
        session.add(
            PartnerMembership(
                id=uuid.uuid4(),
                partner_id=partner.id,
                user_id=str(account.id),
                email=OWNER_EMAIL,
                display_name=OWNER_NAME,
                role=PartnerRole.OWNER.value,
                status=MembershipStatus.ACTIVE.value,
                accepted_at=now,
            )
        )
    else:
        member.user_id = str(account.id)
        member.role = PartnerRole.OWNER.value
        member.status = MembershipStatus.ACTIVE.value
    await session.flush()
    return partner


async def ensure_tenant(session: AsyncSession, partner: Partner, spec: ClientSpec) -> Tenant:
    tenant = await session.scalar(sa.select(Tenant).where(Tenant.slug == spec.slug))
    if tenant is None:
        tenant = Tenant(
            id=uuid.uuid4(),
            name=spec.name,
            slug=spec.slug,
            plan=TenantPlan.PRO,
            status=TenantStatus.ACTIVE,
            partner_id=partner.id,
            timezone=TZ_NAME,
            market="CL",
            business_hours=spec.hours,
            owner_email=spec.person_email,
        )
        session.add(tenant)
        await session.flush()
        say(f"  cliente {spec.name} ({spec.slug}) creado")
    else:
        tenant.partner_id = partner.id
        tenant.status = TenantStatus.ACTIVE
        tenant.timezone = TZ_NAME
        tenant.market = "CL"
        tenant.business_hours = spec.hours
        say(f"  cliente {spec.name} ({spec.slug}) ya existía")
    mapping = await session.scalar(
        sa.select(PartnerTenant).where(
            PartnerTenant.partner_id == partner.id, PartnerTenant.tenant_id == tenant.id
        )
    )
    if mapping is None:
        session.add(
            PartnerTenant(
                partner_id=partner.id,
                external_client_ref=spec.slug,
                tenant_id=tenant.id,
                client_name=spec.name,
            )
        )
    await session.flush()
    return tenant


async def ensure_agent_and_number(
    session: AsyncSession, tenant: Tenant, spec: ClientSpec, now: datetime
) -> tuple[Channel, Agent]:
    """Un agente con su versión activa (ya con ``reservas.*``, así que activar
    el módulo no prepara otra) y el WhatsApp del negocio que responde con él."""
    agent = await session.scalar(
        sa.select(Agent).where(Agent.tenant_id == tenant.id, Agent.name == spec.agent_name)
    )
    if agent is None:
        agent = Agent(id=uuid.uuid4(), tenant_id=tenant.id, name=spec.agent_name, status="active")
        session.add(agent)
        await session.flush()
    has_config = await session.scalar(
        sa.select(sa.func.count())
        .select_from(AgentConfig)
        .where(AgentConfig.tenant_id == tenant.id)
    )
    if not has_config:
        session.add(
            AgentConfig(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                agent_id=agent.id,
                version=1,
                status=AgentConfigStatus.ACTIVE,
                system_prompt_rendered=spec.prompt,
                channels=[],
                tools=sorted(RESERVAS_TOOLS),
                policies={},
                created_by=ACTOR,
                promoted_at=now,
                promoted_by=ACTOR,
            )
        )
    channel = await session.scalar(
        sa.select(Channel).where(
            Channel.tenant_id == tenant.id,
            Channel.type == ChannelType.WHATSAPP,
            Channel.provider == "meta",
        )
    )
    if channel is None:
        channel = Channel(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            type=ChannelType.WHATSAPP,
            provider="meta",
            provider_identifier=spec.number,
            config={"phone_number_id": "DEMO"},
            status=ChannelStatus.ACTIVE,
            agent_id=agent.id,
        )
        session.add(channel)
    else:
        channel.status = ChannelStatus.ACTIVE
        channel.agent_id = agent.id
    await session.flush()
    return channel, agent


async def ensure_person(
    session: AsyncSession,
    partner: Partner,
    tenant: Tenant,
    spec: ClientSpec,
    password: str,
    now: datetime,
) -> str:
    """La persona del cliente con su contraseña (el atajo de desarrollo de
    ``seed_console_memberships --set-password``, en versión cliente)."""
    account = await ensure_account(session, spec.person_email, password, spec.person_name)
    user_id = str(account.id)
    if await session.scalar(
        sa.select(PartnerMembership.id).where(PartnerMembership.user_id == user_id)
    ):
        raise SystemExit(f"{spec.person_email} ya es miembro de un partner; no puede ser cliente.")
    member = await session.scalar(
        sa.select(ClientMembership).where(ClientMembership.user_id == user_id)
    )
    if member is None:
        session.add(
            ClientMembership(
                id=uuid.uuid4(),
                partner_id=partner.id,
                tenant_id=tenant.id,
                user_id=user_id,
                email=spec.person_email,
                display_name=spec.person_name,
                status=ClientMemberStatus.ACTIVE.value,
                invited_by=ACTOR,
                accepted_at=now,
            )
        )
    else:
        member.partner_id = partner.id
        member.tenant_id = tenant.id
        member.status = ClientMemberStatus.ACTIVE.value
    await session.flush()
    return user_id


# ── Bandeja (bajo la RLS del cliente) ───────────────────────────────────────


async def seed_conversations(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    channel_id: uuid.UUID,
    agent_id: uuid.UUID,
    reader_id: str,
    specs: Sequence[ConvSpec],
    now: datetime,
) -> dict[str, Linked]:
    """Conversaciones atendidas por el agente (``attended_at``, spec 045), con
    entrantes del contacto y respuestas del agente. Una por teléfono."""
    linked: dict[str, Linked] = {}
    made = 0
    for spec in specs:
        customer = await session.scalar(
            sa.select(Customer).where(
                Customer.tenant_id == tenant_id, Customer.identifier == spec.phone
            )
        )
        if customer is not None:
            prior = await session.scalar(
                sa.select(Conversation.id)
                .where(
                    Conversation.tenant_id == tenant_id,
                    Conversation.customer_id == customer.id,
                    Conversation.channel_id == channel_id,
                )
                .order_by(Conversation.created_at.desc())
                .limit(1)
            )
            if prior is not None:
                linked[spec.phone] = Linked(prior, customer.id)
                continue
        else:
            customer = Customer(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                identifier=spec.phone,
                name=spec.name,
                preferences={},
            )
            session.add(customer)
            await session.flush()

        first = now - spec.ago
        at = first
        last_inbound = first
        messages: list[Message] = []
        for i, text in enumerate(spec.turns):
            inbound = i % 2 == 0
            if i:
                at += timedelta(minutes=3) if inbound else timedelta(seconds=35)
            if inbound:
                last_inbound = at
            messages.append(
                Message(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    direction=MessageDirection.INBOUND if inbound else MessageDirection.OUTBOUND,
                    status=MessageStatus.DELIVERED if inbound else MessageStatus.READ,
                    content=text,
                    actor_kind=None if inbound else "agent",
                    agent_id=None if inbound else agent_id,
                    created_at=at,
                    updated_at=at,
                )
            )
        conversation = Conversation(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            channel_id=channel_id,
            customer_id=customer.id,
            status=ConversationStatus.OPEN,
            agent_active=True,
            last_inbound_at=last_inbound,
            last_message_at=at,
            attended_at=first,
            last_attended_inbound_at=last_inbound,
            created_at=first,
            updated_at=at,
        )
        session.add(conversation)
        await session.flush()
        for m in messages:
            m.conversation_id = conversation.id
        session.add_all(messages)
        await session.flush()

        if spec.outcome == "escalated":
            mark = await inbox_lifecycle.mark_waiting(
                session, conversation, reason=spec.reason, summary=spec.summary
            )
            event = await session.get(ConversationEvent, mark.event_id)
            if event is not None:
                event.created_at = at + timedelta(seconds=5)
        elif spec.outcome == "resolved":
            await inbox_lifecycle.resolve(session, conversation, actor=f"client:{reader_id}")
        if spec.read:
            session.add(
                InboxRead(
                    tenant_id=tenant_id,
                    conversation_id=conversation.id,
                    user_id=reader_id,
                    read_at=min(at + timedelta(minutes=2), now),
                    marked_unread=False,
                )
            )
        await session.flush()
        linked[spec.phone] = Linked(conversation.id, customer.id)
        made += 1
    say(f"  bandeja: {made} conversaciones nuevas, {len(specs) - made} ya existían")
    return linked


# ── Reservas: Servicios (Cultor) ────────────────────────────────────────────


async def ensure_catalog(
    session: AsyncSession, tenant_id: uuid.UUID
) -> tuple[dict[str, uuid.UUID], dict[str, ReservationService]]:
    staff: dict[str, uuid.UUID] = {}
    for position, (name, hours) in enumerate(CULTOR_STAFF, start=1):
        row = await session.scalar(
            sa.select(ReservationStaff).where(
                ReservationStaff.tenant_id == tenant_id,
                ReservationStaff.name == name,
                ReservationStaff.archived_at.is_(None),
            )
        )
        if row is None:
            row = ReservationStaff(id=uuid.uuid4(), tenant_id=tenant_id, name=name)
            session.add(row)
        row.hours = hours
        row.position = position
        await session.flush()
        staff[name] = row.id
    services: dict[str, ReservationService] = {}
    for position, (name, minutes, price, only) in enumerate(CULTOR_SERVICES, start=1):
        svc = await session.scalar(
            sa.select(ReservationService).where(
                ReservationService.tenant_id == tenant_id,
                ReservationService.name == name,
                ReservationService.archived_at.is_(None),
            )
        )
        if svc is None:
            svc = ReservationService(id=uuid.uuid4(), tenant_id=tenant_id, name=name)
            session.add(svc)
        svc.duration_minutes = minutes
        svc.price_minor = price
        svc.currency = "CLP"
        svc.all_staff = only is None
        svc.position = position
        await session.flush()
        for who in only or ():
            linked = await session.scalar(
                sa.select(ReservationServiceStaff.staff_id).where(
                    ReservationServiceStaff.service_id == svc.id,
                    ReservationServiceStaff.staff_id == staff[who],
                )
            )
            if linked is None:
                session.add(
                    ReservationServiceStaff(
                        tenant_id=tenant_id, service_id=svc.id, staff_id=staff[who]
                    )
                )
        services[name] = svc
    await session.flush()
    say(
        f"  equipo: {', '.join(staff)}; servicios: "
        + ", ".join(
            f"{s.name} {s.duration_minutes} min ${s.price_minor:,}" for s in services.values()
        )
    )
    return staff, services


def _cultor_day(today: date, offset: int) -> date:
    """Cultor cierra los domingos: la cita de un domingo pasa al lunes."""
    d = today + timedelta(days=offset)
    while d.weekday() == 6:
        d += timedelta(days=1)
    return d


async def _service_alternatives(
    session: AsyncSession,
    ctx: core.Ctx,
    *,
    day: date,
    service: ReservationService,
    staff_id: uuid.UUID | None,
    wanted: time,
    now: datetime,
) -> list[tuple[time, uuid.UUID]]:
    """Los huecos libres de ese día, primero con la misma persona y lo más cerca
    posible de la hora pedida."""
    free = await core.services_free(
        session, ctx, day=day, service=service, staff_ids=None, not_before=now
    )
    goal = wanted.hour * 60 + wanted.minute
    ranked: list[tuple[bool, int, str, uuid.UUID]] = []
    for hm, ids in free.items():
        t = _hm(hm)
        for sid in ids:
            other = staff_id is not None and sid != staff_id
            ranked.append((other, abs(t.hour * 60 + t.minute - goal), hm, sid))
    ranked.sort()
    return [(_hm(hm), sid) for _o, _d, hm, sid in ranked[:5]]


async def book_service(
    session: AsyncSession,
    ctx: core.Ctx,
    b: ServiceBooking,
    *,
    day: date,
    staff: dict[str, uuid.UUID],
    services: dict[str, ReservationService],
    linked: dict[str, Linked],
    agent_id: uuid.UUID,
    person: core.Actor,
    now: datetime,
    run_key: str,
) -> str:
    svc = services[b.service]
    wanted_staff = staff[b.staff] if b.staff else None
    conv = linked.get(b.phone)
    key = f"{KEY_PREFIX}:{run_key}:{b.key}"
    by_agent = b.origin == "agent"
    tries: list[tuple[time, uuid.UUID | None]] = [(_hm(b.at), wanted_staff)]
    looked_around = False
    while tries:
        at, staff_id = tries.pop(0)
        start = ctx.at(day, at)
        end = start + timedelta(minutes=svc.duration_minutes)
        past = start < now
        status = b.status
        if past:
            # Lo de esta mañana ya pasó: hecho, o en curso si aún no acaba.
            status = "done" if end <= now else "confirmed"
        req = core.NewBooking(
            day=day,
            at=at,
            origin=b.origin,
            channel="whatsapp" if by_agent else "phone",
            contact_name=b.name,
            contact_phone=b.phone,
            staff_id=staff_id,
            service_id=svc.id,
            any_staff=b.staff is None,
            note=b.note,
            join_waitlist=b.waitlist and not past,
            notify=False,  # nada de mensajes reales a teléfonos inventados
            idempotency_key=key,
            customer_id=conv.customer_id if conv else None,
            conversation_id=conv.conversation_id if conv and by_agent else None,
            agent_id=agent_id if by_agent else None,
            status=status,
        )
        try:
            async with session.begin_nested():
                res, repeated = await core.create_booking(
                    session,
                    ctx,
                    req,
                    actor=AGENT if by_agent else person,
                    now=start - timedelta(days=1) if past else now,
                )
        except core.ReservationError as exc:
            if exc.code != "slot_taken":
                return f"    {b.key} {b.name}: no se pudo ({exc.code})"
            if not looked_around:
                looked_around = True
                tries = list(
                    await _service_alternatives(
                        session,
                        ctx,
                        day=day,
                        service=svc,
                        staff_id=wanted_staff,
                        wanted=at,
                        now=now,
                    )
                )
            continue
        if repeated:
            return f"    {b.key} {b.name}: ya existía"
        extra = ""
        if b.cancel:
            await core.cancel_booking(
                session, ctx, res, by="customer", actor=AGENT, now=now, notify=False
            )
            extra = " y cancelada por el cliente"
        elif res.wants_earlier:
            extra = " (en lista de espera para adelantar)"
        who = next((n for n, i in staff.items() if i == res.staff_id), "?")
        loc = ctx.local(res.starts_at)
        return (
            f"    {b.key} {_day_label(loc.date())} {loc:%H:%M} {res.service_name} con {who}: "
            f"{b.name} [{res.status}, {res.origin}]{extra}"
        )
    return f"    {b.key} {b.name}: sin hueco libre el {_day_label(day)}, se omite"


async def seed_services_bookings(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    linked: dict[str, Linked],
    agent_id: uuid.UUID,
    person: core.Actor,
    today: date,
    now: datetime,
    run_key: str,
) -> None:
    staff, services = await ensure_catalog(session, tenant_id)
    ctx = await core.load_ctx(session, tenant_id)
    if ctx is None:
        raise SystemExit("Cultor no tiene reservation_settings: set_access no activó Reservas.")
    say("  reservas (Servicios):")
    for b in CULTOR_BOOKINGS:
        say(
            await book_service(
                session,
                ctx,
                b,
                day=_cultor_day(today, b.offset),
                staff=staff,
                services=services,
                linked=linked,
                agent_id=agent_id,
                person=person,
                now=now,
                run_key=run_key,
            )
        )


# ── Reservas: Aforo (La Fonda) ──────────────────────────────────────────────


async def tune_capacity(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Los valores de restaurante (``apply_defaults`` en la activación) con la
    sala de La Fonda y la Cena hasta las 22:30, como lo cambiaría el negocio."""
    row = await session.get(ReservationSettings, tenant_id)
    if row is None:
        raise SystemExit("La Fonda no tiene reservation_settings: set_access no activó Reservas.")
    before = (row.seats, row.walkin_hold, row.schedule)
    apply_patch(row, {"capacity": FONDA_CAPACITY})
    if (row.seats, row.walkin_hold, row.schedule) != before:
        row.version += 1
        row.updated_by = ACTOR
    await session.flush()
    say(
        f"  aforo: {row.seats} sitios, {row.walkin_hold} guardados, estancia "
        f"{row.stay_minutes} min, máx. {row.max_party} por reserva; Comida 13:00-15:00 "
        "y Cena 20:00-22:30 cada 30 min"
    )


async def book_table(
    session: AsyncSession,
    ctx: core.Ctx,
    b: TableBooking,
    *,
    day: date,
    linked: dict[str, Linked],
    agent_id: uuid.UUID,
    person: core.Actor,
    now: datetime,
    run_key: str,
) -> str:
    conv = linked.get(b.phone)
    key = f"{KEY_PREFIX}:{run_key}:{b.key}"
    by_agent = b.origin == "agent"
    at = _hm(b.at)
    for attempt in range(2):
        start = ctx.at(day, at)
        past = start < now
        req = core.NewBooking(
            day=day,
            at=at,
            origin=b.origin,
            channel="whatsapp" if by_agent else "phone",
            contact_name=b.name,
            contact_phone=b.phone,
            party_size=b.party,
            note=b.note,
            notify=False,
            idempotency_key=key,
            customer_id=conv.customer_id if conv else None,
            conversation_id=conv.conversation_id if conv and by_agent else None,
            agent_id=agent_id if by_agent else None,
            status=b.status,
        )
        try:
            async with session.begin_nested():
                res, repeated = await core.create_booking(
                    session,
                    ctx,
                    req,
                    actor=AGENT if by_agent else person,
                    now=start - timedelta(hours=2) if past else now,
                )
        except core.ReservationError as exc:
            nxt = exc.info.get("first_fit") if exc.code == "slot_taken" else None
            if attempt == 0 and isinstance(nxt, dict) and nxt.get("date") == day.isoformat():
                at = _hm(str(nxt["time"]))
                continue
            return f"    {b.key} {b.name}: sin sitio el {_day_label(day)} ({exc.code})"
        if repeated:
            return f"    {b.key} {b.name}: ya existía"
        if past:
            # Ya es su hora: llegó (cinco minutos después de la hora).
            await core.transition(
                session, ctx, res, "arrive", actor=person, now=start + timedelta(minutes=5)
            )
        loc = ctx.local(res.starts_at)
        return (
            f"    {b.key} {_day_label(loc.date())} {loc:%H:%M} mesa para {res.party_size}: "
            f"{b.name} [{res.status}, {res.origin}]"
        )
    return f"    {b.key} {b.name}: sin sitio el {_day_label(day)}"


async def walk_in(
    session: AsyncSession,
    ctx: core.Ctx,
    *,
    today: date,
    now: datetime,
    person: core.Actor,
    run_key: str,
) -> str:
    """Una llegada sin reserva en la franja en curso; si hoy aún no abrió el
    servicio, la de anoche en la última franja."""
    day = today
    cap = await core.capacity_day(session, ctx, today)
    slot = engine.current_slot(cap.slots, now)
    arrived = now
    if slot is None:
        day = today - timedelta(days=1)
        cap = await core.capacity_day(session, ctx, day)
        if not cap.slots:
            return "    llegada sin reserva: no hay franjas, se omite"
        slot = cap.slots[-1].at
        arrived = slot + timedelta(minutes=10)
    req = core.NewBooking(
        day=day,
        at=ctx.local(slot).time().replace(tzinfo=None),
        origin="walkin",
        channel="in_person",
        party_size=3,
        note="Mesa en la terraza",
        notify=False,
        idempotency_key=f"{KEY_PREFIX}:{run_key}:walkin",
    )
    try:
        async with session.begin_nested():
            res, repeated = await core.create_booking(session, ctx, req, actor=person, now=arrived)
    except core.ReservationError as exc:
        return f"    llegada sin reserva: no cupo ({exc.code})"
    if repeated:
        return "    llegada sin reserva: ya existía"
    loc = ctx.local(res.starts_at)
    return (
        f"    llegada sin reserva {_day_label(loc.date())} {loc:%H:%M} para "
        f"{res.party_size} [{res.status}]"
    )


async def seed_capacity_extras(
    session: AsyncSession,
    ctx: core.Ctx,
    *,
    today: date,
    linked: dict[str, Linked],
    person: core.Actor,
) -> None:
    full_day = today + timedelta(days=FULL_OFFSET)
    full_at = _hm(FULL_AT)
    entries = (
        ("Felipe Sepúlveda", "+56992345603", 2, AGENT),
        ("Trinidad Cáceres", "+56987650216", 4, person),
    )
    for name, phone, party, by in entries:
        exists = await session.scalar(
            sa.select(ReservationWaitlist.id).where(
                ReservationWaitlist.contact_phone == phone,
                ReservationWaitlist.desired_day == full_day,
                ReservationWaitlist.desired_time == full_at,
                ReservationWaitlist.status == "waiting",
            )
        )
        if exists is not None:
            say(f"    lista de espera {name}: ya existía")
            continue
        conv = linked.get(phone)
        customer_id = (
            conv.customer_id if conv else await core.contact_customer(session, ctx, phone, name)
        )
        await waitlist.join(
            session,
            ctx,
            waitlist.NewEntry(
                contact_name=name,
                contact_phone=phone,
                joined_by_kind="agent" if by.kind == "agent" else "person",
                joined_by_name=by.name,
                customer_id=customer_id,
                party_size=party,
                desired_day=full_day,
                desired_time=full_at,
            ),
        )
        say(f"    lista de espera {_day_label(full_day)} {FULL_AT}: {name}, {party} personas")

    block_day = today + timedelta(days=BLOCK_OFFSET)
    label = "Cena de empresa"
    exists = await session.scalar(
        sa.select(ReservationBlock.id).where(
            ReservationBlock.day == block_day,
            ReservationBlock.label == label,
            ReservationBlock.removed_at.is_(None),
        )
    )
    if exists is None:
        session.add(
            ReservationBlock(
                id=uuid.uuid4(),
                tenant_id=ctx.tenant_id,
                day=block_day,
                from_time=time(20, 0),
                until_time=time(22, 30),
                label=label,
                created_by_name=person.name,
            )
        )
        await session.flush()
        say(f"    bloqueo «{label}» el {_day_label(block_day)} de 20:00 a 22:30")
    else:
        say(f"    bloqueo «{label}»: ya existía")


async def seed_capacity_bookings(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    linked: dict[str, Linked],
    agent_id: uuid.UUID,
    person: core.Actor,
    today: date,
    now: datetime,
    run_key: str,
) -> None:
    await tune_capacity(session, tenant_id)
    ctx = await core.load_ctx(session, tenant_id)
    if ctx is None:
        raise SystemExit("La Fonda no tiene reservation_settings.")
    say("  reservas (Aforo):")
    for b in FONDA_BOOKINGS:
        say(
            await book_table(
                session,
                ctx,
                b,
                day=today + timedelta(days=b.offset),
                linked=linked,
                agent_id=agent_id,
                person=person,
                now=now,
                run_key=run_key,
            )
        )
    say(await walk_in(session, ctx, today=today, now=now, person=person, run_key=run_key))
    await seed_capacity_extras(session, ctx, today=today, linked=linked, person=person)


# ── un cliente de principio a fin ───────────────────────────────────────────


@dataclass(frozen=True)
class Seeded:
    spec: ClientSpec
    tenant_id: uuid.UUID
    agent_id: uuid.UUID


async def seed_client(
    sm: async_sessionmaker[AsyncSession],
    partner_id: uuid.UUID,
    spec: ClientSpec,
    *,
    password: str,
    now: datetime,
    today: date,
    run_key: str,
) -> Seeded:
    say(f"\n{spec.name}")
    async with sm() as session, session.begin():
        partner = await session.get(Partner, partner_id)
        assert partner is not None
        tenant = await ensure_tenant(session, partner, spec)
        channel, agent = await ensure_agent_and_number(session, tenant, spec, now)
        try:
            await client_access.set_access(
                session,
                tenant.id,
                enabled=True,
                modules=list(MODULES),
                actor=ACTOR,
                reservas=spec.choice,
            )
        except ClientAccessError as exc:
            raise SystemExit(f"set_access({spec.slug}) falló: {exc.code}") from None
        kind = f" ({spec.choice.capacity_kind})" if spec.choice.capacity_kind else ""
        say(f"  acceso encendido: {', '.join(MODULES)}; Reservas en {spec.choice.mode}{kind}")
        reader_id = await ensure_person(session, partner, tenant, spec, password, now)
        tenant_id, channel_id, agent_id = tenant.id, channel.id, agent.id

    person = core.Actor("person", spec.person_name)
    if spec.choice.mode == "services":
        convs = cultor_conversations(
            _cultor_day(today, next(b.offset for b in CULTOR_BOOKINGS if b.waitlist))
        )
    else:
        convs = fonda_conversations(today + timedelta(days=FULL_OFFSET))
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        linked = await seed_conversations(
            session,
            tenant_id=tenant_id,
            channel_id=channel_id,
            agent_id=agent_id,
            reader_id=reader_id,
            specs=convs,
            now=now,
        )

    async with sm() as session, tenant_scoped_session(session, tenant_id):
        seed = seed_services_bookings if spec.choice.mode == "services" else seed_capacity_bookings
        await seed(
            session,
            tenant_id=tenant_id,
            linked=linked,
            agent_id=agent_id,
            person=person,
            today=today,
            now=now,
            run_key=run_key,
        )
    return Seeded(spec=spec, tenant_id=tenant_id, agent_id=agent_id)


# ── saldo: recarga del partner, tope por cliente y gasto del mes ────────────


async def seed_money(partner_id: uuid.UUID, clients: Sequence[Seeded]) -> None:
    say("\nSaldo")
    credit = await book.add_purchased(
        partner_id,
        TOP_UP_CREDITS,
        kind=KIND_CREDIT_ADMIN,
        idempotency_key=f"{KEY_PREFIX}:topup:{PARTNER_SLUG}",
    )
    say(
        f"  recarga del partner US$ {TOP_UP_CREDITS / CREDITS_PER_USD:.2f}"
        + (" (ya estaba)" if credit.duplicate else "")
    )
    for c in clients:
        await book.set_allocation(partner_id, c.tenant_id, c.spec.cap_credits)
        spent = 0
        for i, qty in enumerate(c.spec.spend):
            # El prefijo es el del carril del canal (consumo de los clientes
            # finales): solo gasta saldo recargado, como el worker.
            result = await book.debit_wallet(
                partner_id=partner_id,
                qty=qty,
                idempotency_key=f"channel:{KEY_PREFIX}:{c.spec.slug}:{i:02d}",
                tenant_id=c.tenant_id,
                agent_id=c.agent_id,
                allow_included=False,
            )
            spent += result.spent
        say(
            f"  {c.spec.name}: tope US$ {c.spec.cap_credits / CREDITS_PER_USD:.2f}, "
            f"gasto nuevo US$ {spent / CREDITS_PER_USD:.2f}"
        )
    snap = await book.read_wallet(partner_id)
    if snap is not None:
        say(f"  saldo recargado del partner: US$ {snap.purchased_remaining / CREDITS_PER_USD:.2f}")


async def summary(sm: async_sessionmaker[AsyncSession], clients: Sequence[Seeded]) -> None:
    say("\nResumen")
    async with sm() as session, session.begin():
        for c in clients:
            tid = c.tenant_id
            by_status = dict(
                (
                    await session.execute(
                        sa.select(Reservation.status, sa.func.count())
                        .where(Reservation.tenant_id == tid)
                        .group_by(Reservation.status)
                    )
                ).all()
            )
            waiting = await session.scalar(
                sa.select(sa.func.count())
                .select_from(ReservationWaitlist)
                .where(
                    ReservationWaitlist.tenant_id == tid, ReservationWaitlist.status == "waiting"
                )
            )
            convs = dict(
                (
                    await session.execute(
                        sa.select(Conversation.status, sa.func.count())
                        .where(Conversation.tenant_id == tid, Conversation.attended_at.is_not(None))
                        .group_by(Conversation.status)
                    )
                ).all()
            )
            states = ", ".join(f"{k} {v}" for k, v in sorted(by_status.items()))
            threads = ", ".join(f"{k.value} {v}" for k, v in sorted(convs.items(), key=str))
            say(
                f"  {c.spec.name}: {sum(by_status.values())} reservas ({states}); "
                f"{waiting} en lista de espera; conversaciones: {threads}"
            )


# ── main ────────────────────────────────────────────────────────────────────


def _args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Demo de la consola de clientes con Reservas (solo desarrollo)."
    )
    p.add_argument(
        "--password",
        default=DEFAULT_PASSWORD,
        help=f"contraseña de las tres cuentas (por defecto {DEFAULT_PASSWORD})",
    )
    p.add_argument(
        "--console-origin",
        default=None,
        help=f"origen de la consola (NEXUS_CONSOLE_ORIGIN o {DEFAULT_CONSOLE_ORIGIN})",
    )
    return p.parse_args()


def _quiet() -> None:
    """Los servicios registran con structlog; aquí solo interesan los avisos."""
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))


async def main() -> int:
    args = _args()
    settings = get_settings()
    # Pone una contraseña conocida a tres cuentas, una de ellas dueña de un
    # partner: solo contra una base local, no basta con «no es producción»
    # (el entorno vale `dev` si nadie lo fija). Como dev_eval_battery_snapshot.
    host = urlparse(settings.database_url.replace("+asyncpg", "")).hostname or ""
    if settings.is_prod or host not in {"localhost", "127.0.0.1", "::1"}:
        print(
            f"dev_seed_reservas_demo: solo contra una base local (host={host!r}).",
            file=sys.stderr,
        )
        return 2
    try:
        console_identity.validate_password(args.password)
    except console_identity.PasswordPolicyError as exc:
        print(f"Contraseña no válida: {exc}", file=sys.stderr)
        return 2
    _quiet()
    origin = (
        args.console_origin or os.environ.get("NEXUS_CONSOLE_ORIGIN") or DEFAULT_CONSOLE_ORIGIN
    ).rstrip("/")
    now = datetime.now(UTC)
    today = now.astimezone(ZoneInfo(TZ_NAME)).date()
    run_key = today.isoformat()
    sm = get_sessionmaker()
    try:
        async with sm() as session, session.begin():
            partner = await ensure_partner(session, args.password, now)
            partner_id = partner.id
        seeded = [
            await seed_client(
                sm,
                partner_id,
                spec,
                password=args.password,
                now=now,
                today=today,
                run_key=run_key,
            )
            for spec in (CULTOR, FONDA)
        ]
        await seed_money(partner_id, seeded)
        await summary(sm, seeded)
    finally:
        await get_engine().dispose()

    say(f"\nConsola: {origin}/login")
    say(f"  {CULTOR.person_email:<22} cliente de {CULTOR.name} (Servicios)")
    say(f"  {FONDA.person_email:<22} cliente de {FONDA.name} (Aforo)")
    say(f"  {OWNER_EMAIL:<22} dueño de {PARTNER_NAME} (consola de partner)")
    say(f"  contraseña de las tres: {args.password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
