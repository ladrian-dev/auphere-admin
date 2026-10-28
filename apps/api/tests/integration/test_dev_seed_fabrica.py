"""Spec 047, T009 — la semilla de desarrollo de la fábrica (requisito 55.4, CE-001).

``scripts/dev_seed_fabrica.py`` deja lo que ``quickstart.md`` §1 promete:

- «Ladrian Studio» con la consola nueva activada (``console_v2_enabled_at`` y
  ``_by``) y una persona por rol de la consola (owner, admin, builder, analyst
  y billing);
- «Demo USD» sin activar, con alguien que entre a la consola de hoy;
- los cuatro clientes del prototipo; Café Origen sin agentes, y los otros tres
  con agente, versión activa y un WhatsApp ya conectado que responde con él;
- una persona del cliente para la consola lite y la app;
- y correrla dos veces no duplica nada.

La semilla abre su propio engine (``get_sessionmaker``) y hace ``commit`` de
verdad, fuera de la sesión del test. ``db_session`` vacía las tablas al
terminar; las cuentas de ``console_auth`` no entran en ese vaciado, así que
las borra el fixture de abajo.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "dev_seed_fabrica.py"
#: De desarrollo, claramente falsa (la política pide 12 caracteres o más).
PASSWORD = "fabrica-dev-1234"
ROLES = ("owner", "admin", "builder", "analyst", "billing")
CLIENTS = {"Flor y Encanto", "Clínica Dental Sonrisa", "ADSL System", "Café Origen"}
WITHOUT_AGENTS = "Café Origen"


def _load() -> ModuleType:
    """La semilla vive en ``scripts/``, fuera del paquete: se carga por ruta."""
    assert SCRIPT.is_file(), f"falta la semilla {SCRIPT.name}"
    spec = importlib.util.spec_from_file_location("dev_seed_fabrica", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Sus dataclasses resuelven las anotaciones por ``sys.modules``.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


async def _rows(session: AsyncSession, sql: str, **params: Any) -> list[Any]:
    rows = list((await session.execute(sa.text(sql), params)).all())
    # Cada lectura cierra su transacción: la siguiente ve lo que la semilla
    # haya escrito después con su propio engine.
    await session.rollback()
    return rows


@pytest_asyncio.fixture
async def started_at(db_session: AsyncSession) -> AsyncIterator[datetime]:
    """Lo que la semilla crea en ``console_auth`` se borra al terminar."""
    start = (await _rows(db_session, "SELECT clock_timestamp() AS at"))[0].at
    try:
        yield start
    finally:
        await db_session.execute(
            sa.text("DELETE FROM console_auth.principals WHERE created_at >= :t"), {"t": start}
        )
        await db_session.commit()


async def _partners(session: AsyncSession) -> dict[str, Any]:
    rows = await _rows(
        session,
        "SELECT id, name, slug, status, console_enabled, console_v2_enabled_at, "
        "console_v2_enabled_by FROM partners",
    )
    return {r.name: r for r in rows}


async def test_la_semilla_deja_el_mundo_del_prototipo(
    db_session: AsyncSession, started_at: datetime
) -> None:
    seed = _load()
    await seed.seed(password=PASSWORD)

    partners = await _partners(db_session)
    assert set(partners) == {"Ladrian Studio", "Demo USD"}
    ladrian, demo = partners["Ladrian Studio"], partners["Demo USD"]
    # La consola nueva, activada solo en Ladrian Studio (research D38).
    assert ladrian.console_v2_enabled_at is not None
    assert ladrian.console_v2_enabled_by
    assert demo.console_v2_enabled_at is None
    assert demo.console_v2_enabled_by is None
    # Los dos entran en la consola; Demo USD, en la de hoy.
    assert ladrian.console_enabled and demo.console_enabled
    assert ladrian.status == demo.status == "active"

    clients = {
        r.client_name: r.tenant_id
        for r in await _rows(
            db_session,
            "SELECT pt.client_name, pt.tenant_id FROM partner_tenants pt "
            "JOIN tenants t ON t.id = pt.tenant_id "
            "WHERE pt.partner_id = :p AND t.partner_id = :p",
            p=ladrian.id,
        )
    }
    assert set(clients) == CLIENTS

    for name, tenant_id in clients.items():
        agents = await _rows(
            db_session,
            "SELECT g.id, g.status, g.lifecycle, g.is_default, "
            "  (SELECT count(*) FROM agent_configs c "
            "    WHERE c.agent_id = g.id AND c.status = 'active') AS active_versions "
            "FROM agents g WHERE g.tenant_id = :t",
            t=tenant_id,
        )
        versions = await _rows(
            db_session, "SELECT id FROM agent_configs WHERE tenant_id = :t", t=tenant_id
        )
        channels = await _rows(
            db_session,
            "SELECT ch.type, ch.provider, ch.status, ch.agent_id, ch.config_encrypted "
            "FROM channels ch WHERE ch.tenant_id = :t",
            t=tenant_id,
        )
        if name == WITHOUT_AGENTS:
            assert agents == [], f"{name} no tiene agentes"
            assert versions == []
            assert channels == []
            continue
        assert agents, f"{name} tiene al menos un agente"
        assert all(a.status == "active" and a.active_versions == 1 for a in agents), name
        # Como deja la migración 0190 a los agentes de antes (recorrido UI: la
        # semilla los dejaba en «draft» y sin agente por defecto, así que ni
        # «Pasar a otro agente» ni el agente por defecto se podían probar).
        assert all(a.lifecycle == "published" for a in agents), name
        assert sum(a.is_default for a in agents) == 1, name
        own_agents = {a.id for a in agents}
        whatsapp = [
            c
            for c in channels
            if c.type == "whatsapp" and c.provider == "meta" and c.status == "active"
        ]
        # Ya conectado, respondiendo con un agente del propio cliente, y sin
        # credenciales de Meta (requisito 30.10: «El número lo conecta Auphere»).
        assert whatsapp, f"{name} tiene un WhatsApp conectado"
        assert all(c.agent_id in own_agents for c in whatsapp), name
        assert all(c.config_encrypted is None for c in channels), name

    roles = await _rows(
        db_session,
        "SELECT role, count(*) AS n FROM partner_memberships "
        "WHERE partner_id = :p AND status = 'active' GROUP BY role",
        p=ladrian.id,
    )
    assert {r.role: r.n for r in roles} == dict.fromkeys(ROLES, 1)
    demo_owner = await _rows(
        db_session,
        "SELECT 1 FROM partner_memberships "
        "WHERE partner_id = :p AND status = 'active' AND role = 'owner'",
        p=demo.id,
    )
    assert len(demo_owner) == 1

    people = await _rows(
        db_session,
        "SELECT cm.tenant_id, cm.user_id, a.enabled, a.modules "
        "FROM client_memberships cm JOIN client_access a ON a.tenant_id = cm.tenant_id "
        "WHERE cm.partner_id = :p AND cm.status = 'active'",
        p=ladrian.id,
    )
    assert len(people) == 1, "una persona del cliente para la consola lite y la app"
    person = people[0]
    assert person.tenant_id in set(clients.values()) - {clients[WITHOUT_AGENTS]}
    assert person.enabled and "panel" in person.modules

    # Cada persona tiene su cuenta de consola, y la del cliente no es de un partner.
    orphans = await _rows(
        db_session,
        "SELECT m.email FROM ("
        "  SELECT user_id, email FROM partner_memberships WHERE status = 'active' "
        "  UNION ALL "
        "  SELECT user_id, email FROM client_memberships WHERE status = 'active'"
        ") m LEFT JOIN console_auth.principals p ON p.id::text = m.user_id "
        "WHERE p.id IS NULL",
    )
    assert orphans == []
    crossed = await _rows(
        db_session,
        "SELECT 1 FROM partner_memberships WHERE user_id = :u",
        u=person.user_id,
    )
    assert crossed == []
    # T167: la persona del cliente ve Agentes y Negocio en la consola lite.
    assert {"agents", "business"} <= set(person.modules)

    # T155 y T157: la cuenta de Ladrian en EUR, las bolsas del prototipo y el tope.
    from nexus_api.core.partner_context import apply_partner_to_session
    from nexus_api.core.tenant_context import tenant_scoped_session
    from nexus_api.db.models import Agent, ClientWallet, PartnerWallet
    from nexus_api.services.wallet.bags import as_client, bags_active

    async with db_session.begin():
        await apply_partner_to_session(db_session, ladrian.id)
        account = await db_session.scalar(
            sa.select(PartnerWallet).where(PartnerWallet.partner_id == ladrian.id)
        )
        assert account is not None and account.currency == "EUR"
        assert await bags_active(db_session, ladrian.id)
        seen: dict[str, tuple[str, int]] = {}
        for ref, tenant_id in clients.items():
            await as_client(db_session, tenant_id)
            bag = await db_session.get(ClientWallet, tenant_id)
            if bag is not None:
                seen[ref] = (bag.currency, bag.balance_micros)
    names = {spec.ref: spec.name for spec in seed.CLIENTS}
    assert seen == {
        names[ref]: (currency, amount * seed.UNIT) for ref, (currency, amount) in seed.BAGS.items()
    }
    async with tenant_scoped_session(db_session, clients["Flor y Encanto"]):
        cap = await db_session.scalar(
            sa.select(Agent.monthly_cap_micros).where(Agent.name == "Ventas mayoristas")
        )
    await db_session.commit()
    assert cap == 15 * seed.UNIT


_COUNTED = (
    "partners",
    "partner_wallets",
    "partner_subscriptions",
    "partner_memberships",
    "tenants",
    "partner_tenants",
    "agents",
    "agent_configs",
    "channels",
    "client_access",
    "client_memberships",
)


async def _snapshot(session: AsyncSession, since: datetime) -> dict[str, Any]:
    counts: dict[str, Any] = {}
    for table in _COUNTED:
        counts[table] = (await _rows(session, f"SELECT count(*) AS n FROM {table}"))[0].n
    counts["principals"] = (
        await _rows(
            session,
            "SELECT count(*) AS n FROM console_auth.principals WHERE created_at >= :t",
            t=since,
        )
    )[0].n
    partners = await _partners(session)
    counts["activated"] = {
        name: (p.console_v2_enabled_at, p.console_v2_enabled_by) for name, p in partners.items()
    }
    return counts


async def test_correrla_dos_veces_no_duplica_nada(
    db_session: AsyncSession, started_at: datetime
) -> None:
    seed = _load()
    await seed.seed(password=PASSWORD)
    first = await _snapshot(db_session, started_at)
    # Cinco roles del partner y la persona del cliente, como mínimo.
    assert first["principals"] >= len(ROLES) + 1

    await seed.seed(password=PASSWORD)
    second = await _snapshot(db_session, started_at)

    # Las mismas filas, y la activación conserva su primer «cuándo».
    assert second == first
