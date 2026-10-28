"""La fábrica de agentes en la base local — spec 047, T009 (solo desarrollo).

Siembra, en la base de ``NEXUS_DATABASE_URL``, el mundo del prototipo de la
consola nueva (``quickstart.md`` §1):

- el partner «Ladrian Studio» (``ladrian-studio``) con la **consola nueva
  activada** (``partners.console_v2_enabled_at`` / ``_by``, migración 0175) y
  una persona por rol de la consola: Luis (owner), Ana (admin), Lucía
  (builder), Pablo (analyst) e Irene (billing);
- el partner «Demo USD» (``demo-usd``) **sin activar**, con su dueño, para
  entrar a la consola de hoy;
- los cuatro clientes del prototipo bajo Ladrian Studio: Flor y Encanto, ADSL
  System y Clínica Dental Sonrisa, cada uno con sus agentes (versión activa) y
  un WhatsApp ya conectado, y Café Origen, **sin agentes**;
- Marta, la persona de Flor y Encanto, para la consola lite y la app.

Los canales nacen conectados y **sin credenciales de Meta** (ni token ni
``config_encrypted``): la consola dice «El número lo conecta Auphere»
(requisito 30.10). Los números son de mentira (``+56 9 0000 01xx``…).

Lo que la spec pide y el esquema todavía no tiene (la ficha, el nicho, las
bolsas, la moneda de la cuenta, los estados del agente…) **no se inventa**:
queda escrito abajo, en «Crece con la T…», con los datos del prototipo
(KB ``research/2026-10-26-fabrica-de-agentes-v2/01-prototipo-consola-v2.md``
§11.4). La semilla crece en el mismo cambio que trae cada tabla.

Uso (lee NEXUS_DATABASE_URL del entorno):

    cd apps/api && uv run python scripts/dev_seed_fabrica.py [--password '...']

Se puede repetir: lo que ya existe se reutiliza (por slug, referencia,
nombre, número o correo), las contraseñas vuelven a ser la impresa y la
activación conserva su primer «cuándo». No duplica filas ni auditoría.

Solo para desarrollo: se niega a correr fuera de una base local.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

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
    ClientAccess,
    ClientMembership,
    ClientMemberStatus,
    ConsoleAccount,
    MembershipStatus,
    Partner,
    PartnerMembership,
    PartnerRole,
    PartnerSubscription,
    PartnerTenant,
    Tenant,
    TenantPlan,
    TenantStatus,
)
from nexus_api.services import client_access, console_identity
from nexus_api.services.business_hours import canonical_business_hours
from nexus_api.services.client_access import ClientAccessError

ACTOR = "operator:dev-seed@auphere.local"
DEFAULT_PASSWORD = "demo-demo-1234"
DEFAULT_CONSOLE_ORIGIN = "http://localhost:3111"
#: La persona del cliente entra a Panel, Bandeja, Agentes, Negocio y Consumo (la
#: Bandeja pide un WhatsApp conectado, y Flor y Encanto lo tiene; Agentes y
#: Negocio llegan con la T167).
CLIENT_MODULES = ["panel", "inbox", "agents", "business", "usage"]
#: Cien milésimas por unidad de moneda (las de las bolsas).
UNIT = 100_000
#: Un cambio de desarrollo para que las bolsas en EUR funcionen sin el cron del
#: BCE; solo se escribe si la base no tiene ninguno.
DEV_EUR_USD = "1.08"
#: La cuenta de Ladrian Studio (T155): en EUR, con 240 €.
LADRIAN_ACCOUNT = ("EUR", 240 * UNIT)
#: Las bolsas del prototipo (T155): moneda y lo asignado, en su moneda.
BAGS: dict[str, tuple[str, int]] = {
    "flor-y-encanto": ("USD", 60),
    "adsl-system": ("USD", 40),
    "clinica-dental-sonrisa": ("EUR", 30),
    "cafe-origen": ("EUR", 0),  # «Sin saldo»
}
#: El tope del mes de un agente (T157): Ventas mayoristas, 15 USD.
AGENT_CAPS: dict[tuple[str, str], int] = {("flor-y-encanto", "Ventas mayoristas"): 15 * UNIT}


def say(msg: str) -> None:
    print(msg, flush=True)


# ── el reparto ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Person:
    email: str
    name: str
    role: str = PartnerRole.OWNER.value


@dataclass(frozen=True)
class PartnerSpec:
    slug: str
    name: str
    console_v2: bool
    people: tuple[Person, ...]
    #: Flor y Encanto atiende con tres números (``partners.max_channels_per_client``
    #: vale 2 por defecto y solo lo mira la API al conectar uno nuevo).
    max_channels_per_client: int | None = None


@dataclass(frozen=True)
class SeedAgent:
    name: str
    prompt: str
    #: El WhatsApp que responde con él (E.164, de mentira). ``None`` = sin canal.
    number: str | None = None


@dataclass(frozen=True)
class ClientSpec:
    ref: str  # external_client_ref: el ``{ref}`` de la consola del partner
    name: str
    timezone: str
    market: str
    hours: dict[str, Any] | None
    agents: tuple[SeedAgent, ...]
    person: Person | None = None

    @property
    def slug(self) -> str:
        return f"ladrian-{self.ref}"


LADRIAN = PartnerSpec(
    slug="ladrian-studio",
    name="Ladrian Studio",
    console_v2=True,
    people=(
        Person("luis@ladrian.test", "Luis Matos", PartnerRole.OWNER.value),
        Person("ana@ladrian.test", "Ana Ortega", PartnerRole.ADMIN.value),
        Person("lucia@ladrian.test", "Lucía Pardo", PartnerRole.BUILDER.value),
        Person("pablo@ladrian.test", "Pablo Ruiz", PartnerRole.ANALYST.value),
        Person("irene@ladrian.test", "Irene Soler", PartnerRole.BILLING.value),
    ),
    max_channels_per_client=3,
)
# T155 (ola 7, el dinero): la cuenta de Ladrian Studio en EUR con 240 €
# (``ensure_money``); la de Demo USD sigue en USD y sin saldo.

DEMO_USD = PartnerSpec(
    slug="demo-usd",
    name="Demo USD",
    console_v2=False,
    people=(Person("socio@demo-usd.test", "Daniel Reyes", PartnerRole.OWNER.value),),
)

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday")


def _hours(
    weekdays: list[tuple[str, str]],
    *,
    friday: list[tuple[str, str]] | None = None,
    saturday: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Un horario semanal, validado por la forma canónica de hoy
    (``services/business_hours``). Lo que no se nombra, cerrado."""
    raw: dict[str, Any] = {d: [{"from": a, "to": b} for a, b in weekdays] for d in WEEKDAYS}
    if friday is not None:
        raw["friday"] = [{"from": a, "to": b} for a, b in friday]
    raw["saturday"] = [{"from": a, "to": b} for a, b in saturday or []]
    raw["sunday"] = []
    return canonical_business_hours(raw)


MARTA = Person("marta@florencanto.test", "Marta Vidal")

FLOR = ClientSpec(
    ref="flor-y-encanto",
    name="Flor y Encanto",
    timezone="America/Santiago",
    market="CL",
    hours=_hours([("09:00", "14:00"), ("16:00", "20:00")], saturday=[("09:00", "14:00")]),
    agents=(
        SeedAgent(
            "Recepción",
            "Eres Recepción, el asistente de Flor y Encanto, una floristería con "
            "entregas a domicilio en Providencia (Santiago). Atiendes el WhatsApp: "
            "tomas pedidos de ramos y arreglos, y respondes precios, horarios y "
            "plazos de entrega. Tono cercano y breve, de tú. Si alguien se queja o "
            "pide hablar con una persona, avisa a Carla.",
            "+56900000101",
        ),
        SeedAgent(
            "Ventas mayoristas",
            "Atiendes a las empresas y floristerías que compran al por mayor a Flor "
            "y Encanto: catálogo, precios por volumen y plazos. Preparas "
            "presupuestos para los pedidos grandes y avisas a Marta para que los "
            "confirme. Tono cercano, de tú.",
            "+56900000102",
        ),
        SeedAgent(
            "Cobranza",
            "Recuerdas los pagos pendientes a los clientes de Flor y Encanto y "
            "envías el enlace de pago. Tono formal, de usted. Si alguien discute el "
            "importe, avisa a Marta.",
            "+56900000103",
        ),
    ),
    person=MARTA,
)
# Crece con las T046 y T055 (ola 2, la ficha): nicho «Floristería con entregas a
# domicilio»; precios en CLP; la sede «Tienda Providencia»; el horario pasa a
# la ficha; servicios Ramo de temporada, Ramo de 12 rosas, Centro de mesa,
# Decoración de bodas (sin precio) y Arreglo de condolencias.
# Crece con la T122 (ola 4, los estados del agente): Recepción
# «Publicado», Ventas mayoristas «En prueba» y Cobranza «Pausado». Hoy los tres
# tienen versión activa y responden.
# Crece con la T108 (ola 4, la configuración del canal): Recepción a todos
# salvo 2 excepciones, en coexistencia y escalando a Carla por WhatsApp;
# Ventas mayoristas solo a 2 números de prueba, en coexistencia; Cobranza a
# todos, por la Cloud API.
# Crece con la T127 (ola 5, las activaciones): WooCommerce activado en Recepción y
# Stripe en Cobranza. Con la T132 (ola 5, el conocimiento): las fuentes, la web (14 páginas)
# y «catalogo-bodas-2026.pdf».
# T155 y T157 (ola 7): la bolsa en USD, 60 asignados; tope de 15 USD en Ventas
# mayoristas (``BAGS``, ``AGENT_CAPS``). T167 (ola 8): Marta tiene los módulos
# ``agents`` y ``business`` de la consola lite (``CLIENT_MODULES``).

ADSL = ClientSpec(
    ref="adsl-system",
    name="ADSL System",
    timezone="America/Lima",
    market="PE",
    hours=None,  # el prototipo lo «lee de la web»: llega con la lectura (T049)
    agents=(
        SeedAgent(
            "Soporte",
            "Eres Soporte de ADSL System, proveedor de internet y fibra para "
            "hogares en Lima. Ayudas con cortes, lentitud, el router y las visitas "
            "técnicas. Si no lo puedes resolver por aquí, avisas al equipo técnico.",
            "+51900000201",
        ),
        SeedAgent(
            "Ventas",
            "Explicas los planes de fibra de ADSL System, la instalación y la "
            "cobertura, y tomas los datos de quien quiere contratar.",
        ),
    ),
)
# Crece con las T046 y T055 (ola 2): nicho «Proveedor de internet y fibra para
# hogares», el horario leído de la web y los servicios Fibra 300 Mb, Fibra 600
# Mb e Instalación (gratis). T127 (ola 5): HubSpot en Soporte. T155 (ola 7):
# bolsa en USD, 40 asignados (``BAGS``).
# No se siembra: el chat web de Soporte ni el Instagram de Ventas. Hoy solo se
# usa WhatsApp por Meta, e Instagram sale «Próximamente» en el prototipo.

CLINICA = ClientSpec(
    ref="clinica-dental-sonrisa",
    name="Clínica Dental Sonrisa",
    timezone="Europe/Madrid",
    market="ES",
    hours=_hours([("09:00", "20:00")], friday=[("09:00", "15:00")]),
    agents=(
        SeedAgent(
            "Citas",
            "Eres el asistente de la Clínica Dental Sonrisa, una clínica dental "
            "familiar en Madrid. Das, cambias y cancelas citas, y respondes precios "
            "y horarios. Tono cercano, de tú. Si alguien tiene dolor fuerte o una "
            "urgencia, avisa a recepción.",
            "+34600000301",
        ),
        # «Listo · sin canal» en el prototipo: guardado y sin número.
        SeedAgent(
            "Recordatorios",
            "Recuerdas a los pacientes de la Clínica Dental Sonrisa su cita del día "
            "siguiente y les pides que la confirmen o la cambien.",
        ),
    ),
)
# Crece con las T046 y T055 (ola 2): nicho «Clínica dental familiar», precios en
# EUR, horario día por día en la ficha, servicios Primera visita (gratis),
# Limpieza, Blanqueamiento y Ortodoncia (sin precio). T127 (ola 5): Google
# Calendar en Citas. T132 (ola 5): «tarifas-2026.pdf», que falló al leerse.
# T155 (ola 7): bolsa en EUR, 30 asignados (``BAGS``).

CAFE = ClientSpec(
    ref="cafe-origen",
    name="Café Origen",
    timezone="Europe/Madrid",
    market="ES",
    hours=None,  # «leído de la web» en el prototipo (T049)
    agents=(),  # sin agentes: aquí se prueba «Nuevo agente» (quickstart, ola 3)
)
# Crece con las T046 y T055 (ola 2): nicho «Cafetería de especialidad con tostador
# propio», las redes (Instagram y TikTok) y los servicios Espresso, Flat white,
# Filtro V60, Bolsa de café 250 g y Cata de cafés (sábados, 90 min). T155
# (ola 7): bolsa en EUR sin asignar, «Sin saldo» (``BAGS``).

CLIENTS = (FLOR, ADSL, CLINICA, CAFE)

#: Todos los correos que la semilla usa, para limpiar o comprobar.
SEED_EMAILS = tuple(
    p.email for p in (*LADRIAN.people, *DEMO_USD.people, *(c.person for c in CLIENTS if c.person))
)


# ── partner, cuentas y personas (sesión de plataforma, sin RLS) ─────────────


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


async def ensure_partner(session: AsyncSession, spec: PartnerSpec, now: datetime) -> Partner:
    partner = await session.scalar(sa.select(Partner).where(Partner.slug == spec.slug))
    if partner is None:
        partner = Partner(
            id=uuid.uuid4(),
            name=spec.name,
            slug=spec.slug,
            contact_email=spec.people[0].email,
            console_enabled=True,
        )
        session.add(partner)
        await session.flush()  # el trigger trg_partners_seed_wallet crea su cuenta
        say(f"partner {spec.name} creado")
    else:
        say(f"partner {spec.name} ya existía")
    partner.name = spec.name
    partner.status = "active"
    partner.console_enabled = True
    if spec.max_channels_per_client is not None:
        partner.max_channels_per_client = max(
            partner.max_channels_per_client, spec.max_channels_per_client
        )
    # La consola nueva se activa partner a partner (research D38). Repetir la
    # semilla conserva el primer «cuándo»; el partner sin activar vuelve a la
    # consola de hoy aunque alguien lo activara a mano.
    if spec.console_v2:
        if partner.console_v2_enabled_at is None:
            partner.console_v2_enabled_at = now
            partner.console_v2_enabled_by = ACTOR
        say(f"  consola nueva activada ({partner.console_v2_enabled_at:%Y-%m-%d %H:%M} UTC)")
    else:
        partner.console_v2_enabled_at = None
        partner.console_v2_enabled_by = None
        say("  consola nueva sin activar: ve la consola de hoy")
    if await session.get(PartnerSubscription, partner.id) is None:
        session.add(
            PartnerSubscription(partner_id=partner.id, tier_code="business", state="current")
        )
    await session.flush()
    return partner


async def ensure_member(
    session: AsyncSession, partner: Partner, person: Person, password: str, now: datetime
) -> None:
    """Una persona del partner con su rol (el atajo de desarrollo de
    ``seed_console_memberships --set-password``). Una cuenta es de un solo
    partner: si ya es de otro, se para."""
    account = await ensure_account(session, person.email, password, person.name)
    user_id = str(account.id)
    if await session.scalar(
        sa.select(ClientMembership.id).where(ClientMembership.user_id == user_id)
    ):
        raise SystemExit(f"{person.email} ya es persona de un cliente; no puede ser del partner.")
    member = await session.scalar(
        sa.select(PartnerMembership).where(PartnerMembership.user_id == user_id)
    )
    if member is not None and member.partner_id != partner.id:
        raise SystemExit(f"{person.email} ya es miembro de otro partner.")
    if member is None:
        session.add(
            PartnerMembership(
                id=uuid.uuid4(),
                partner_id=partner.id,
                user_id=user_id,
                email=person.email,
                display_name=person.name,
                role=person.role,
                status=MembershipStatus.ACTIVE.value,
                accepted_at=now,
            )
        )
    else:
        member.email = person.email
        member.display_name = person.name
        member.role = person.role
        member.status = MembershipStatus.ACTIVE.value
    await session.flush()
    say(f"  {person.role:<8} {person.email}")


async def ensure_tenant(session: AsyncSession, partner: Partner, spec: ClientSpec) -> Tenant:
    tenant = await session.scalar(sa.select(Tenant).where(Tenant.slug == spec.slug))
    if tenant is None:
        tenant = Tenant(
            id=uuid.uuid4(),
            name=spec.name,
            slug=spec.slug,
            plan=TenantPlan.PRO,
            # Activo aunque no tenga agente ni canal: la 047 separa el ciclo de
            # vida de la preparación (requisito 4.7) y Café Origen nace así.
            status=TenantStatus.ACTIVE,
            partner_id=partner.id,
            timezone=spec.timezone,
            market=spec.market,
            business_hours=spec.hours,
            owner_email=spec.person.email if spec.person else None,
        )
        session.add(tenant)
        await session.flush()
        say(f"  cliente {spec.name} ({spec.ref}) creado")
    else:
        if tenant.partner_id not in (None, partner.id):
            raise SystemExit(f"{spec.slug} ya es cliente de otro partner.")
        tenant.name = spec.name
        tenant.partner_id = partner.id
        tenant.status = TenantStatus.ACTIVE
        tenant.timezone = spec.timezone
        tenant.market = spec.market
        tenant.business_hours = spec.hours
        say(f"  cliente {spec.name} ({spec.ref}) ya existía")
    mapping = await session.scalar(
        sa.select(PartnerTenant).where(
            PartnerTenant.partner_id == partner.id, PartnerTenant.tenant_id == tenant.id
        )
    )
    if mapping is None:
        session.add(
            PartnerTenant(
                partner_id=partner.id,
                external_client_ref=spec.ref,
                tenant_id=tenant.id,
                client_name=spec.name,
            )
        )
    else:
        mapping.client_name = spec.name
    await session.flush()
    return tenant


# ── agentes y números (bajo la RLS del cliente) ─────────────────────────────


async def ensure_agents(
    session: AsyncSession, tenant_id: uuid.UUID, spec: ClientSpec, now: datetime
) -> None:
    """Cada agente con una versión activa y, si tiene número, el WhatsApp que
    responde con él. El primero de la lista es el principal (el más antiguo),
    así que su ``created_at`` va por delante."""
    # Uno por defecto por cliente (``uq_agents_one_default``): al repetir, se
    # quita a los de la semilla antes de volver a ponerlo en el primero. Un
    # cliente sin agentes en la semilla no se toca.
    if spec.agents:
        await session.execute(
            sa.update(Agent)
            .where(Agent.tenant_id == tenant_id, Agent.name.in_([a.name for a in spec.agents]))
            .values(is_default=False)
        )
    for position, seed_agent in enumerate(spec.agents):
        agent = await session.scalar(
            sa.select(Agent).where(Agent.tenant_id == tenant_id, Agent.name == seed_agent.name)
        )
        if agent is None:
            agent = Agent(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                name=seed_agent.name,
                status="active",
                created_at=now + timedelta(seconds=position),
            )
            session.add(agent)
            await session.flush()
        agent.status = "active"
        # Como la migración 0190 deja a los agentes de antes: con versión activa,
        # publicado, y el más antiguo de cada cliente, el agente por defecto.
        agent.lifecycle = "published"
        agent.is_default = position == 0

        active = await session.scalar(
            sa.select(AgentConfig.id).where(
                AgentConfig.tenant_id == tenant_id,
                AgentConfig.agent_id == agent.id,
                AgentConfig.status == AgentConfigStatus.ACTIVE,
            )
        )
        if active is None:
            last = await session.scalar(
                sa.select(sa.func.max(AgentConfig.version)).where(
                    AgentConfig.tenant_id == tenant_id
                )
            )
            session.add(
                AgentConfig(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    agent_id=agent.id,
                    version=(last or 0) + 1,
                    status=AgentConfigStatus.ACTIVE,
                    system_prompt_rendered=seed_agent.prompt,
                    channels=[],
                    tools=[],
                    policies={},
                    created_by=ACTOR,
                    promoted_at=now,
                    promoted_by=ACTOR,
                )
            )
            await session.flush()

        if seed_agent.number is not None:
            channel = await session.scalar(
                sa.select(Channel).where(
                    Channel.tenant_id == tenant_id,
                    Channel.type == ChannelType.WHATSAPP,
                    Channel.provider == "meta",
                    Channel.provider_identifier == seed_agent.number,
                )
            )
            if channel is None:
                channel = Channel(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    type=ChannelType.WHATSAPP,
                    provider="meta",
                    provider_identifier=seed_agent.number,
                    # Sin token ni ``config_encrypted``: nada sale hacia Meta.
                    config={"phone_number_id": "DEV-SEED"},
                    status=ChannelStatus.ACTIVE,
                    agent_id=agent.id,
                )
                session.add(channel)
            else:
                channel.status = ChannelStatus.ACTIVE
                channel.agent_id = agent.id
            await session.flush()
        where = f"WhatsApp {seed_agent.number}" if seed_agent.number else "sin canal"
        say(f"  agente {seed_agent.name}: versión activa, {where}")
    if not spec.agents:
        say("  sin agentes")


# ── la persona del cliente (consola lite y app) ─────────────────────────────


async def ensure_client_person(
    session: AsyncSession,
    partner: Partner,
    tenant: Tenant,
    person: Person,
    password: str,
    now: datetime,
) -> None:
    """Enciende el acceso del cliente por el servicio del admin (solo si no
    está ya así: cada llamada deja su auditoría) y cuelga a la persona."""
    access = await session.get(ClientAccess, tenant.id)
    if access is None or not access.enabled or list(access.modules) != CLIENT_MODULES:
        try:
            await client_access.set_access(
                session, tenant.id, enabled=True, modules=list(CLIENT_MODULES), actor=ACTOR
            )
        except ClientAccessError as exc:
            raise SystemExit(f"set_access({tenant.slug}) falló: {exc.code}") from None
    say(f"  acceso del cliente: {', '.join(CLIENT_MODULES)}")

    account = await ensure_account(session, person.email, password, person.name)
    user_id = str(account.id)
    if await session.scalar(
        sa.select(PartnerMembership.id).where(PartnerMembership.user_id == user_id)
    ):
        raise SystemExit(f"{person.email} ya es miembro de un partner; no puede ser cliente.")
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
                email=person.email,
                display_name=person.name,
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


# ── el dinero (T155, T157) ──────────────────────────────────────────────────


async def ensure_money(
    sm: async_sessionmaker[AsyncSession],
    partner_id: uuid.UUID,
    clients: dict[str, uuid.UUID],
    now: datetime,
) -> None:
    """La cuenta en EUR de Ladrian Studio, las bolsas de sus clientes y el tope de
    Ventas mayoristas. Idempotente: las asignaciones llevan su clave."""
    from nexus_api.core.partner_context import apply_partner_to_session
    from nexus_api.db.models import FxRate, PartnerWallet
    from nexus_api.services.wallet import bags

    say("\nEl dinero")
    async with sm() as session, session.begin():
        if await session.scalar(sa.select(sa.func.count()).select_from(FxRate)) == 0:
            session.add(FxRate(date=now.date(), base="EUR", quote="USD", rate=DEV_EUR_USD))
            say(f"  cambio de desarrollo 1 EUR = {DEV_EUR_USD} USD")
    async with sm() as session, session.begin():
        await apply_partner_to_session(session, partner_id)
        account = await session.scalar(
            sa.select(PartnerWallet).where(PartnerWallet.partner_id == partner_id)
        )
        currency, purchased = LADRIAN_ACCOUNT
        if account is not None and account.currency != currency:
            account.currency = currency
            account.purchased_remaining = purchased
        say(f"  cuenta en {currency}")
        for ref, (bag_currency, amount) in BAGS.items():
            tenant_id = clients.get(ref)
            if tenant_id is None:
                continue
            bag = await bags.bag_for_update(session, tenant_id, partner_id=partner_id)
            if bag.currency != bag_currency and bag.balance_micros == 0:
                await bags.change_currency(
                    session,
                    partner_id=partner_id,
                    tenant_id=tenant_id,
                    currency=bag_currency,
                    actor=ACTOR,
                )
            if amount:
                await bags.assign(
                    session,
                    partner_id=partner_id,
                    tenant_id=tenant_id,
                    amount=amount * UNIT,
                    idempotency_key=f"seed:{ref}",
                    actor=ACTOR,
                    in_bag_currency=True,
                )
            say(f"  bolsa de {ref}: {amount} {bag_currency}")
    for (ref, agent_name), cap in AGENT_CAPS.items():
        tenant_id = clients.get(ref)
        if tenant_id is None:
            continue
        async with sm() as session, tenant_scoped_session(session, tenant_id):
            await session.execute(
                sa.update(Agent)
                .where(Agent.tenant_id == tenant_id, Agent.name == agent_name)
                .values(monthly_cap_micros=cap)
            )
        say(f"  tope de {agent_name}: {cap // UNIT}")


# ── todo junto ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Seeded:
    partners: dict[str, uuid.UUID]
    clients: dict[str, uuid.UUID]


async def _seed_client(
    sm: async_sessionmaker[AsyncSession],
    partner_id: uuid.UUID,
    spec: ClientSpec,
    *,
    password: str,
    now: datetime,
) -> uuid.UUID:
    say(f"\n{spec.name}")
    async with sm() as session, session.begin():
        partner = await session.get(Partner, partner_id)
        assert partner is not None
        tenant = await ensure_tenant(session, partner, spec)
        tenant_id = tenant.id
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        await ensure_agents(session, tenant_id, spec, now)
    if spec.person is not None:
        async with sm() as session, session.begin():
            owner = await session.get(Partner, partner_id)
            client = await session.get(Tenant, tenant_id)
            assert owner is not None and client is not None
            await ensure_client_person(session, owner, client, spec.person, password, now)
    return tenant_id


async def seed(*, password: str = DEFAULT_PASSWORD, now: datetime | None = None) -> Seeded:
    """Siembra todo contra la base de ``get_settings()``. Idempotente."""
    console_identity.validate_password(password)
    now = now or datetime.now(UTC)
    sm = get_sessionmaker()
    partners: dict[str, uuid.UUID] = {}
    for spec in (LADRIAN, DEMO_USD):
        async with sm() as session, session.begin():
            partner = await ensure_partner(session, spec, now)
            for person in spec.people:
                await ensure_member(session, partner, person, password, now)
            partners[spec.slug] = partner.id
    clients = {
        spec.ref: await _seed_client(sm, partners[LADRIAN.slug], spec, password=password, now=now)
        for spec in CLIENTS
    }
    await ensure_money(sm, partners[LADRIAN.slug], clients, now)
    return Seeded(partners=partners, clients=clients)


# ── main ────────────────────────────────────────────────────────────────────


def _args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="La fábrica de agentes (spec 047) en la base local (solo desarrollo)."
    )
    p.add_argument(
        "--password",
        default=DEFAULT_PASSWORD,
        help=f"contraseña de todas las cuentas (por defecto {DEFAULT_PASSWORD})",
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
    # Pone una contraseña conocida a cuentas de dueño: solo contra una base
    # local, no basta con «no es producción» (como dev_seed_reservas_demo).
    host = urlparse(settings.database_url.replace("+asyncpg", "")).hostname or ""
    if settings.is_prod or host not in {"localhost", "127.0.0.1", "::1"}:
        print(f"dev_seed_fabrica: solo contra una base local (host={host!r}).", file=sys.stderr)
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
    try:
        await seed(password=args.password)
    finally:
        await get_engine().dispose()

    say(f"\nConsola: {origin}/login")
    for person in LADRIAN.people:
        say(f"  {person.email:<24} {person.role} de {LADRIAN.name} (consola nueva)")
    for person in DEMO_USD.people:
        say(f"  {person.email:<24} {person.role} de {DEMO_USD.name} (consola de hoy)")
    say(f"  {MARTA.email:<24} persona de {FLOR.name} (consola lite y app)")
    say(f"  contraseña de todas: {args.password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
