"""Spec 047, T042 — el alta de un cliente en tres datos (historia 3).

``POST /console/clients`` con ``{name, niche, info?, …}`` (``contracts/console-api.md`` §2):

- **lo que pide**: nombre (1 a 60), nicho (2 a 80) e información (≤ 2.000), con
  ``clients:write``;
- **lo que no hace**: no crea ningún agente ni publica ninguna versión, aunque el
  partner tenga plantilla por defecto (requisito 4.3, research D2);
- **lo que deduce**: zona, país y monedas, por este orden: dominio y prefijo,
  país del partner, navegador (4.5);
- **nombre repetido**: avisa sin bloquear y deriva otra referencia (4.6);
- **ciclo de vida**: un cliente sin agentes está ``active``, sin un
  ``provisioning`` que dependa de tener agente y canal (4.7);
- **auditoría** con el autor (4.8).

Y lo que lo rodea: la detección de enlaces y las sugerencias de nicho del modal,
la lectura que se lanza si hay web o redes (4.4), y que el alta de la consola de
hoy (``external_client_ref``) sigue igual para los partners sin la nueva.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import (
    Agent,
    AgentConfig,
    AuditLog,
    ClientWallet,
    Job,
    Partner,
    PartnerTenant,
    Tenant,
    TenantStatus,
)
from nexus_api.db.models.business import (
    BusinessFieldProvenance,
    BusinessLink,
    BusinessProfile,
    BusinessSection,
)
from nexus_api.services.jobs import JOBS_STREAM
from tests.conftest import add_console_member

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def world(db_session: AsyncSession, console_world: dict[str, Any]) -> dict[str, Any]:
    """El mundo de la consola, con sitio para varios clientes: el tope de
    ``max_clients`` es una guarda contra bucles y aquí no se prueba."""
    for label in ("a", "b"):
        partner = await db_session.get(Partner, console_world[label]["partner_id"])
        assert partner is not None
        partner.max_clients = 50
    await db_session.commit()
    return console_world


async def _create(client: Any, headers: dict[str, str], **body: Any) -> Any:
    return await client.post("/console/clients", json=body, headers=headers)


async def _tenant_of(db_session: AsyncSession, partner_id: uuid.UUID, ref: str) -> Tenant:
    async with db_session.begin():
        tenant = await db_session.scalar(
            sa.select(Tenant)
            .join(PartnerTenant, PartnerTenant.tenant_id == Tenant.id)
            .where(PartnerTenant.partner_id == partner_id, PartnerTenant.external_client_ref == ref)
            .execution_options(populate_existing=True)
        )
    assert tenant is not None, f"no tenant behind {ref}"
    return tenant


async def _scoped(db_session: AsyncSession, tenant_id: uuid.UUID, stmt: Any) -> list[Any]:
    async with tenant_scoped_session(db_session, tenant_id):
        return list((await db_session.execute(stmt)).scalars().all())


# ── lo que pide y lo que no hace ─────────────────────────────────────────────


async def test_three_fields_create_an_active_client_without_agents(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    a = world["a"]
    resp = await _create(
        client, a["headers"](), name="Barbería Cultor", niche="Barbería de barrio con 2 sedes"
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["ref"] == "barberia-cultor"
    assert body["name"] == "Barbería Cultor"
    assert body["status"] == "active"
    assert body["duplicate_name"] is False
    assert body["read_job_id"] is None  # sin web ni redes no hay nada que leer
    assert "tenant_id" not in resp.text

    tenant = await _tenant_of(db_session, a["partner_id"], "barberia-cultor")
    # Requisito 4.7: sin agentes, activo. Nada de un «preparando».
    assert tenant.status is TenantStatus.ACTIVE
    assert tenant.name == "Barbería Cultor"

    assert await _scoped(db_session, tenant.id, sa.select(Agent)) == []
    assert await _scoped(db_session, tenant.id, sa.select(AgentConfig)) == []
    reads = sa.select(Job).where(Job.kind == "client_read")
    assert await _scoped(db_session, tenant.id, reads) == []
    # Enmienda del 2026-10-29 (57.2): el sector se identifica en segundo plano.
    (sector_job,) = await _scoped(db_session, tenant.id, sa.select(Job))
    assert sector_job.kind == "sector_identify" and sector_job.status == "queued"

    (profile,) = await _scoped(db_session, tenant.id, sa.select(BusinessProfile))
    assert profile.niche == "Barbería de barrio con 2 sedes"
    assert profile.info is None
    assert profile.content_rev == 1

    sections = {
        s.section: s.state for s in await _scoped(db_session, tenant.id, sa.select(BusinessSection))
    }
    assert sections["basics"] == "complete"
    assert sections["hours"] == "pending"
    assert sections["services"] == "pending"

    provenance = {
        p.pointer: p
        for p in await _scoped(db_session, tenant.id, sa.select(BusinessFieldProvenance))
    }
    niche = provenance["/business/niche"]
    assert (niche.source, niche.actor_kind, niche.origin, niche.review) == (
        "person",
        "partner_member",
        "console",
        "confirmed",
    )
    assert niche.actor_id == a["user_id"]


async def test_the_partners_default_template_creates_no_agent(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    """Escenario 5 de la historia 3: la plantilla por defecto pasa a «Nuevo agente»."""
    a = world["a"]
    partner = await db_session.get(Partner, a["partner_id"])
    assert partner is not None
    partner.default_seed_template = "barbershop_v1"
    await db_session.commit()

    resp = await _create(client, a["headers"](), name="Café Origen", niche="Cafetería")
    assert resp.status_code == 201, resp.text
    tenant = await _tenant_of(db_session, a["partner_id"], resp.json()["ref"])
    assert await _scoped(db_session, tenant.id, sa.select(Agent)) == []
    assert await _scoped(db_session, tenant.id, sa.select(AgentConfig)) == []
    assert tenant.status is TenantStatus.ACTIVE


@pytest.mark.parametrize(
    "body",
    [
        {"name": "x" * 61, "niche": "Barbería"},
        {"name": "", "niche": "Barbería"},
        {"name": "   ", "niche": "Barbería"},
        {"name": "Barbería Cultor", "niche": "B"},
        {"name": "Barbería Cultor", "niche": "x" * 81},
        {"name": "Barbería Cultor", "niche": "Barbería", "info": "x" * 2001},
        {"name": "Barbería Cultor"},
        {"name": "Barbería Cultor", "niche": "Barbería", "timezone": "Mars/Olympus"},
        {"name": "Barbería Cultor", "niche": "Barbería", "country": "Spain"},
        {"name": "Barbería Cultor", "niche": "Barbería", "price_currency": "euro"},
        {"name": "Barbería Cultor", "niche": "Barbería", "wallet_currency": "CLP"},
    ],
)
async def test_the_three_fields_have_their_limits(
    client: Any, db_session: AsyncSession, world: dict[str, Any], body: dict[str, Any]
) -> None:
    a = world["a"]
    before = await db_session.scalar(
        sa.select(sa.func.count())
        .select_from(PartnerTenant)
        .where(PartnerTenant.partner_id == a["partner_id"])
    )
    resp = await _create(client, a["headers"](), **body)
    assert resp.status_code == 422, resp.text
    after = await db_session.scalar(
        sa.select(sa.func.count())
        .select_from(PartnerTenant)
        .where(PartnerTenant.partner_id == a["partner_id"])
    )
    assert after == before, "un alta rechazada dejó un cliente"


async def test_the_limits_are_inclusive(client: Any, world: dict[str, Any]) -> None:
    a = world["a"]
    resp = await _create(client, a["headers"](), name="x" * 60, niche="xy", info="i" * 2000)
    assert resp.status_code == 201, resp.text


async def test_only_clients_write_creates(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    a = world["a"]
    analyst = await add_console_member(db_session, partner_id=a["partner_id"], role="analyst")
    resp = await _create(client, analyst["headers"](), name="Barbería Cultor", niche="Barbería")
    assert resp.status_code == 403, resp.text
    builder = await add_console_member(db_session, partner_id=a["partner_id"], role="builder")
    resp = await _create(client, builder["headers"](), name="Barbería Cultor", niche="Barbería")
    assert resp.status_code == 201, resp.text


# ── lo que deduce ─────────────────────────────────────────────────────────────


async def test_a_cl_web_deduces_chile_and_launches_the_reading(
    client: Any, db_session: AsyncSession, world: dict[str, Any], fake_redis: Any
) -> None:
    a = world["a"]
    resp = await _create(
        client,
        a["headers"](),
        name="Flor y Encanto",
        niche="Florería",
        info="flor-y-encanto.cl · @florencanto · escríbenos a hola@flor-y-encanto.cl",
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    tenant = await _tenant_of(db_session, a["partner_id"], body["ref"])
    assert tenant.timezone == "America/Santiago"

    (profile,) = await _scoped(db_session, tenant.id, sa.select(BusinessProfile))
    assert profile.country == "CL"
    assert profile.timezone == "America/Santiago"
    assert profile.price_currency == "CLP"
    assert profile.eu_only is False
    assert profile.website == "https://flor-y-encanto.cl"
    assert profile.info.startswith("flor-y-encanto.cl")

    links = {
        (link.network, link.handle or link.url)
        for link in await _scoped(db_session, tenant.id, sa.select(BusinessLink))
    }
    # El correo no es una web ni un usuario; el @ suelto, Instagram.
    assert links == {("web", "https://flor-y-encanto.cl"), ("instagram", "@florencanto")}

    # Requisito 4.4: hay web, así que la lectura empieza en segundo plano.
    (job,) = await _scoped(db_session, tenant.id, sa.select(Job).where(Job.kind == "client_read"))
    assert body["read_job_id"] == str(job.id)
    assert (job.kind, job.status, job.agent_id) == ("client_read", "queued", None)
    assert job.created_by == a["user_id"]
    entries = await fake_redis.xrange(JOBS_STREAM)
    # La lectura, y la identificación del sector (enmienda del 2026-10-29, 57.2).
    assert [e[1]["kind"] for e in entries if e[1]["job_id"] == str(job.id)] == ["client_read"]
    assert sorted(e[1]["kind"] for e in entries) == ["client_read", "sector_identify"]


async def test_a_spanish_phone_deduces_spain_and_eu_only(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    a = world["a"]
    resp = await _create(
        client,
        a["headers"](),
        name="Barbería Cultor",
        niche="Barbería",
        info="Pedir cita al +34 600 123 456",
    )
    assert resp.status_code == 201, resp.text
    tenant = await _tenant_of(db_session, a["partner_id"], resp.json()["ref"])
    (profile,) = await _scoped(db_session, tenant.id, sa.select(BusinessProfile))
    assert (profile.country, profile.timezone, profile.price_currency, profile.eu_only) == (
        "ES",
        "Europe/Madrid",
        "EUR",
        True,
    )
    # Un teléfono no es un enlace: no hay nada que leer.
    assert resp.json()["read_job_id"] is None


async def test_what_the_person_chose_in_more_settings_wins(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    a = world["a"]
    resp = await _create(
        client,
        a["headers"](),
        name="Café Origen",
        niche="Cafetería de especialidad",
        info="cafeorigen.cl",
        country="MX",
        timezone="America/Mexico_City",
        price_currency="MXN",
        wallet_currency="EUR",
        eu_only=True,
    )
    assert resp.status_code == 201, resp.text
    tenant = await _tenant_of(db_session, a["partner_id"], resp.json()["ref"])
    assert tenant.timezone == "America/Mexico_City"
    (profile,) = await _scoped(db_session, tenant.id, sa.select(BusinessProfile))
    assert (profile.country, profile.timezone, profile.price_currency, profile.eu_only) == (
        "MX",
        "America/Mexico_City",
        "MXN",
        True,
    )


@pytest.mark.parametrize(
    ("country", "chosen", "expected"),
    [("MX", "EUR", "EUR"), ("ES", "USD", "USD"), ("CL", "USD", "USD")],
)
async def test_the_bag_is_born_in_the_chosen_currency(
    client: Any,
    db_session: AsyncSession,
    world: dict[str, Any],
    country: str,
    chosen: str,
    expected: str,
) -> None:
    """Bug «el alta descarta la moneda de la bolsa» (requisito 43.3): la moneda
    elegida en «Más ajustes» es la de la bolsa, aunque el país diga otra."""
    a = world["a"]
    resp = await _create(
        client,
        a["headers"](),
        name="Café Origen",
        niche="Cafetería",
        country=country,
        wallet_currency=chosen,
    )
    assert resp.status_code == 201, resp.text
    tenant = await _tenant_of(db_session, a["partner_id"], resp.json()["ref"])
    (bag,) = await _scoped(db_session, tenant.id, sa.select(ClientWallet))
    assert (bag.currency, bag.balance_micros) == (expected, 0)


async def test_the_link_chips_the_person_changed_are_what_is_saved(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    """Un ``@`` suelto se propone como Instagram y la persona lo cambió a TikTok."""
    a = world["a"]
    resp = await _create(
        client,
        a["headers"](),
        name="Barbería Cultor",
        niche="Barbería",
        info="@cultorbarber",
        links=[{"network": "tiktok", "handle": "@cultorbarber"}],
    )
    assert resp.status_code == 201, resp.text
    tenant = await _tenant_of(db_session, a["partner_id"], resp.json()["ref"])
    (link,) = await _scoped(db_session, tenant.id, sa.select(BusinessLink))
    assert (link.network, link.handle, link.url) == (
        "tiktok",
        "@cultorbarber",
        "https://www.tiktok.com/@cultorbarber",
    )
    # Solo redes, sin web: también se leen (los perfiles públicos, requisito 5.4).
    assert resp.json()["read_job_id"] is not None


# ── la detección y las sugerencias del modal ─────────────────────────────────


async def test_link_detection_gives_chips_and_more_settings(
    client: Any, world: dict[str, Any]
) -> None:
    a = world["a"]
    resp = await client.post(
        "/console/clients/link-detection",
        json={
            "info": "cultorbarber.com · @cultorbarber · hola@cultorbarber.com",
            "browser_timezone": "Europe/Madrid",
            "browser_locale": "es-ES",
        },
        headers=a["headers"](),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [(c["network"], c["value"], c["target"]) for c in body["links"]] == [
        ("web", "cultorbarber.com", "website"),
        ("instagram", "@cultorbarber", "links"),
    ]
    insta = body["links"][1]
    assert insta["guessed"] is True and "tiktok" in insta["alternatives"]
    # Un .com no dice el país: manda el navegador.
    assert body["deduced"] == {
        "country": "ES",
        "timezone": "Europe/Madrid",
        "price_currency": "EUR",
        "wallet_currency": "USD",
        "eu_only": True,
        "source": "browser",
    }


async def test_link_detection_rejects_a_text_over_the_limit(
    client: Any, world: dict[str, Any]
) -> None:
    resp = await client.post(
        "/console/clients/link-detection",
        json={"info": "x" * 2001},
        headers=world["a"]["headers"](),
    )
    assert resp.status_code == 422


async def test_niche_suggestions_are_the_templates_and_the_partners_own(
    client: Any, world: dict[str, Any]
) -> None:
    a, b = world["a"], world["b"]
    for headers, niche in (
        (a["headers"], "Barbería de barrio"),
        (a["headers"], "Barbería de barrio"),
        (b["headers"], "Barbería premium del partner B"),
    ):
        resp = await _create(client, headers(), name=f"Cliente {uuid.uuid4().hex[:6]}", niche=niche)
        assert resp.status_code == 201, resp.text

    resp = await client.get(
        "/console/clients/niche-suggestions", params={"q": "barber"}, headers=a["headers"]()
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert {
        "source": "template",
        "key": "barbershop",
        "group": "beauty",
        "value": None,
        "uses": 0,
    } in items
    used = [i for i in items if i["source"] == "used"]
    assert used == [
        {"source": "used", "key": None, "group": None, "value": "Barbería de barrio", "uses": 2}
    ]
    # El nicho de un cliente de otro partner no existe para este.
    assert "partner B" not in resp.text

    everything = await client.get("/console/clients/niche-suggestions", headers=a["headers"]())
    groups = {i["group"] for i in everything.json()["items"] if i["source"] == "template"}
    assert {"beauty", "health", "aesthetics", "food", "retail", "services"} <= groups


# ── nombre repetido, auditoría, idempotencia ─────────────────────────────────


async def test_a_repeated_name_warns_without_blocking_and_derives_another_ref(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    a = world["a"]
    first = await _create(client, a["headers"](), name="Barbería Cultor", niche="Barbería")
    second = await _create(client, a["headers"](), name="Barbería Cultor", niche="Barbería")
    assert first.status_code == second.status_code == 201
    assert first.json()["duplicate_name"] is False
    assert second.json()["duplicate_name"] is True
    assert second.json()["ref"] == "barberia-cultor-2"
    third = await _create(client, a["headers"](), name="barbería cultor", niche="Barbería")
    assert third.json()["duplicate_name"] is True
    assert third.json()["ref"] == "barberia-cultor-3"
    # El mismo nombre en otro partner no es repetido.
    other = await _create(client, world["b"]["headers"](), name="Barbería Cultor", niche="Barbería")
    assert other.json()["duplicate_name"] is False
    assert other.json()["ref"] == "barberia-cultor"


async def test_the_alta_is_audited_with_its_author(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    a = world["a"]
    resp = await _create(client, a["headers"](), name="Barbería Cultor", niche="Barbería")
    tenant = await _tenant_of(db_session, a["partner_id"], resp.json()["ref"])
    rows = await _scoped(
        db_session, tenant.id, sa.select(AuditLog).where(AuditLog.action == "console.client.create")
    )
    assert len(rows) == 1
    (row,) = rows
    assert row.actor == "console:owner-a@example.com"
    assert row.target == f"tenant:{tenant.id}"
    assert row.after_json is not None
    assert row.after_json["niche"] == "Barbería"
    assert row.after_json["ref"] == "barberia-cultor"


async def test_a_repeated_idempotency_key_answers_the_same(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    a = world["a"]
    headers = {**a["headers"](), "Idempotency-Key": "alta-1"}
    first = await _create(client, headers, name="Barbería Cultor", niche="Barbería")
    again = await _create(
        client,
        {**a["headers"](), "Idempotency-Key": "alta-1"},
        name="Barbería Cultor",
        niche="Barbería",
    )
    assert first.status_code == again.status_code == 201
    assert first.json() == again.json()
    count = await db_session.scalar(
        sa.select(sa.func.count())
        .select_from(PartnerTenant)
        .where(
            PartnerTenant.partner_id == a["partner_id"],
            PartnerTenant.client_name == "Barbería Cultor",
        )
    )
    assert count == 1


async def test_the_new_client_reads_as_active(client: Any, world: dict[str, Any]) -> None:
    a = world["a"]
    ref = (await _create(client, a["headers"](), name="Barbería Cultor", niche="Barbería")).json()[
        "ref"
    ]
    resp = await client.get(f"/console/clients/{ref}", headers=a["headers"]())
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "active"


# ── la consola de hoy no cambia ──────────────────────────────────────────────


async def test_todays_body_keeps_its_contract(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    """Los partners sin la consola nueva siguen con ``clients/new``: la misma
    forma, la misma respuesta y el mismo ``provisioning`` de hoy."""
    a = world["a"]
    resp = await _create(
        client,
        a["headers"](),
        external_client_ref="legacy-1",
        name="Cliente de hoy",
        timezone="Europe/Madrid",
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["external_client_ref"] == "legacy-1"
    assert body["agent_status"] == "not_configured"
    assert "quota" in body
    tenant = await _tenant_of(db_session, a["partner_id"], "legacy-1")
    assert tenant.status is TenantStatus.PROVISIONING
    assert await _scoped(db_session, tenant.id, sa.select(BusinessProfile)) == []
