"""Spec 047, enmienda del 2026-10-29, T190 — quien usa el sector lee el guardado
(requisito 57.6; research D46).

Las pruebas del sector (21.1) y el constructor del cliente (60) salen del sector
de la ficha, **nunca** de volver a clasificar el nicho: el nicho dice «Barbería»
pero una persona fijó «Clínica», y manda la ficha. Y la regla de palabras de
respaldo solo la llama quien identifica el sector, en un sitio.
"""

from __future__ import annotations

import ast
import uuid
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import Partner, PartnerTenant, Tenant
from nexus_api.db.models.agent_spec import AgentTest, AgentTestSuite
from nexus_api.db.models.business import BusinessProfile

pytestmark = pytest.mark.asyncio

SRC = Path(__file__).resolve().parents[2] / "src" / "nexus_api"
#: Los que usan el sector para algo; ninguno puede clasificar el nicho.
CONSUMERS = (
    SRC / "services" / "testing" / "sector_catalog.py",
    SRC / "services" / "builder" / "client_profile.py",
    SRC / "services" / "builder" / "agent_draft.py",
    SRC / "api" / "console" / "agent_builder.py",
)
#: Lo que clasifica por palabras: solo lo llama el servicio del sector.
CLASSIFIERS = {"sector_of_niche", "sector_of_text", "fallback_sector"}


def test_no_consumer_classifies_the_niche_again() -> None:
    offenders: list[str] = []
    for path in CONSUMERS:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            name = None
            if isinstance(node, ast.Name):
                name = node.id
            elif isinstance(node, ast.Attribute):
                name = node.attr
            elif isinstance(node, ast.alias):
                name = node.name
            if name in CLASSIFIERS:
                offenders.append(f"{path.name}: {name}")
    assert not offenders, f"vuelven a clasificar el nicho en lugar de leer la ficha: {offenders}"


async def _client(
    db_session: AsyncSession, *, niche: str, sector: dict[str, Any] | None
) -> uuid.UUID:
    tenant_id = uuid.uuid4()
    async with db_session.begin():
        partner = Partner(name=f"P {tenant_id.hex[:6]}", slug=f"p-{tenant_id.hex[:10]}")
        db_session.add(partner)
        await db_session.flush()
        db_session.add(
            Tenant(
                id=tenant_id,
                name="Cultor",
                slug=f"t-{tenant_id.hex[:10]}",
                timezone="Europe/Madrid",
                partner_id=partner.id,
            )
        )
        await db_session.flush()
        db_session.add(
            PartnerTenant(
                partner_id=partner.id,
                external_client_ref=f"ref-{tenant_id.hex[:8]}",
                tenant_id=tenant_id,
                client_name="Cultor",
            )
        )
    async with tenant_scoped_session(db_session, tenant_id):
        db_session.add(
            BusinessProfile(
                tenant_id=tenant_id,
                niche=niche,
                timezone="Europe/Madrid",
                sector=sector,
            )
        )
    return tenant_id


FIXED_CLINIC = {
    "key": "clinica",
    "label": "Clínica dental y estética",
    "confidence": 1.0,
    "source": "person",
    "decided_by": "person",
}


async def test_sector_tests_come_from_the_stored_sector(db_session: AsyncSession) -> None:
    from nexus_api.services.testing.sector_catalog import add_sector_tests, client_sector

    tenant_id = await _client(db_session, niche="Barbería de barrio", sector=FIXED_CLINIC)
    async with tenant_scoped_session(db_session, tenant_id):
        assert await client_sector(db_session) == "clinica"
        from nexus_api.db.models import Agent

        agent = Agent(id=uuid.uuid4(), tenant_id=tenant_id, name="Recepción")
        db_session.add(agent)
        await db_session.flush()
        suite = AgentTestSuite(id=uuid.uuid4(), tenant_id=tenant_id, agent_id=agent.id)
        db_session.add(suite)
        await db_session.flush()
        added = await add_sector_tests(db_session, suite)
        refs = (
            await db_session.scalars(
                sa.select(AgentTest.sector_test_ref).where(AgentTest.suite_id == suite.id)
            )
        ).all()
    assert added == 12
    assert all(ref.startswith("clinica@") for ref in refs), refs


async def test_an_unidentified_sector_is_stored_once_and_then_read(
    db_session: AsyncSession,
) -> None:
    """Sin sector todavía (la identificación va en segundo plano), quien lo necesita
    lo deja guardado con la regla de respaldo y confianza baja; desde ahí, se lee."""
    from nexus_api.services.business import sector as sector_service
    from nexus_api.services.testing.sector_catalog import client_sector

    tenant_id = await _client(db_session, niche="Barbería de barrio", sector=None)
    async with tenant_scoped_session(db_session, tenant_id):
        assert await client_sector(db_session) == "barberia_peluqueria"
        stored = await sector_service.stored(db_session)
    assert stored is not None and stored["source"] == "fallback"
    assert stored["confidence"] < 0.5 and stored["decided_by"] == "system"
    # Cambiar el nicho ya no cambia lo que leen las pruebas: lo cambia identificar.
    async with tenant_scoped_session(db_session, tenant_id):
        profile = await db_session.get(BusinessProfile, tenant_id)
        assert profile is not None
        profile.niche = "Clínica dental"
    async with tenant_scoped_session(db_session, tenant_id):
        assert await client_sector(db_session) == "barberia_peluqueria"


def test_the_client_builder_offline_proposals_follow_the_sector_key() -> None:
    from nexus_api.services.builder.client_profile import offline_output

    assert offline_output("clinica")["agents"][0]["name"] == "Citas"
    assert offline_output("barberia_peluqueria")["agents"][0]["name"] == "Recepción"
    assert offline_output("otro")["agents"][0]["name"] == "Atención"
    assert offline_output(None)["agents"][0]["name"] == "Atención"


async def test_the_client_builder_reads_the_stored_sector(db_session: AsyncSession) -> None:
    """La ficha dice «Barbería» en el nicho y «Clínica» en el sector: el constructor
    del cliente propone lo de una clínica."""
    from nexus_api.db.base import get_sessionmaker
    from nexus_api.services.builder.client_profile import build_client_profile

    tenant_id = await _client(db_session, niche="Barbería de barrio", sector=FIXED_CLINIC)

    async def progress(**_kw: Any) -> bool:
        return True

    result = await build_client_profile(
        tenant_id=tenant_id,
        job_id=uuid.uuid4(),
        complete=None,
        progress=progress,
        sessionmaker=get_sessionmaker(),
    )
    from nexus_api.db.models.business import BusinessSuggestion

    async with tenant_scoped_session(db_session, tenant_id):
        cancellation = await db_session.scalar(
            sa.select(BusinessSuggestion.proposed_value).where(
                BusinessSuggestion.pointer == "/policies/cancellation"
            )
        )
    assert cancellation == "Cancela o cambia tu cita con al menos 24 horas de antelación."
    # Spec 047, enmienda del 2026-10-30 (65.7): «Citas» da y cambia citas, y este
    # cliente no tiene Reservas encendido: se sugiere el que atiende y pasa al equipo.
    assert [a["name"] for a in result["agents"]] == ["Atención"]
