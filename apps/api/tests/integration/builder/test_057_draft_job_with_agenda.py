"""Spec 057, historia 1 — «Gestiona citas» en «Nuevo agente» (requisitos 1 y 7.1).

Con el interruptor encendido y Reservas apagado, Reservas se enciende en la misma
petición, **antes** de encolar o de escribir el borrador, para que el constructor vea la
agenda; la v1 sale con las nueve. Sin modo, o si encender falla, no se crea nada. Sin
interruptor (``agenda=null``), como hasta hoy. Apagado, ninguna ``reservas.*``.
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
    AgentConfigStatus,
    ClientAccess,
    Job,
    ReservationSettings,
)
from nexus_api.services.reservations.passing import RESERVAS_TOOLS
from tests.conftest import add_console_member

from ..business._business_world import Biz, new_business
from ._builder_world import RECEPTION, FakeBuilder, job_row, run_jobs, start_draft

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

DESCRIPTION = "Atiende el WhatsApp del salón, informa precios y agenda citas con las clientas."


@pytest.fixture
async def biz(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> Biz:
    # Un cliente nuevo: sin Reservas, como Spa Jemma el 2026-11-08.
    return await new_business(client, db_session, console_world, name="Spa Jemma")


def _url(biz: Biz) -> str:
    return f"/console/clients/{biz.ref}"


async def _rows(db_session: AsyncSession, tenant_id: uuid.UUID, model: Any) -> list[Any]:
    async with tenant_scoped_session(db_session, tenant_id):
        rows = await db_session.scalars(sa.select(model).execution_options(populate_existing=True))
        return list(rows.all())


async def _agent_tools(db_session: AsyncSession, biz: Biz, agent_id: uuid.UUID) -> list[str]:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        cfg = await db_session.scalar(
            sa.select(AgentConfig)
            .where(AgentConfig.agent_id == agent_id, AgentConfig.status == AgentConfigStatus.STAGED)
            .execution_options(populate_existing=True)
        )
    assert cfg is not None
    return list(cfg.tools or [])


async def test_draft_options_say_what_the_switch_needs(client: Any, biz: Biz) -> None:
    got = await client.get(f"{_url(biz)}/agents/draft-options", headers=biz.headers())
    assert got.status_code == 200, got.text
    agenda = got.json()["agenda"]
    assert agenda["offered"] is True
    assert agenda["module_on"] is False and agenda["mode"] is None
    assert agenda["suggested_mode"] == "services"
    books = {t["id"]: t["books"] for t in got.json()["templates"]}
    assert books["beauty_salon_v1"] is True
    assert books["cobranza_v1"] is False


async def test_describe_with_the_agenda_turns_reservas_on_before_the_job(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    resp = await start_draft(
        client,
        _url(biz),
        biz.headers(),
        description=DESCRIPTION,
        agenda=True,
        reservas={"mode": "services", "capacity_kind": None},
    )
    assert resp.status_code == 202, resp.text
    # Encendido antes de que el trabajo empiece: el constructor ya ve la agenda.
    [settings] = await _rows(db_session, biz.tenant_id, ReservationSettings)
    assert settings.mode == "services"
    [access] = await _rows(db_session, biz.tenant_id, ClientAccess)
    assert "reservas" in access.modules and access.enabled is False
    job = await job_row(db_session, biz.tenant_id, resp.json()["job_id"])
    assert job.progress["input"]["agenda"] == "true"

    builder = FakeBuilder(reply=RECEPTION)
    await run_jobs(fake_redis, builder)
    assert "<agenda>" in builder.prompt and "GESTIONA CITAS" in builder.prompt
    job = await job_row(db_session, biz.tenant_id, resp.json()["job_id"])
    assert job.status == "done", job.error_code
    agent_id = uuid.UUID(job.result["agent_id"])
    assert set(RESERVAS_TOOLS) <= set(await _agent_tools(db_session, biz, agent_id))


async def test_without_a_mode_nothing_is_created(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    resp = await start_draft(client, _url(biz), biz.headers(), description=DESCRIPTION, agenda=True)
    assert resp.status_code == 422, resp.text
    assert "reservas_mode_required" in resp.text
    jobs = await _rows(db_session, biz.tenant_id, Job)
    assert [j for j in jobs if j.kind == "agent_draft"] == []
    assert await _rows(db_session, biz.tenant_id, Agent) == []
    assert await _rows(db_session, biz.tenant_id, ReservationSettings) == []


async def test_an_archived_client_creates_nothing(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    await db_session.execute(
        sa.text("UPDATE tenants SET status = 'archived' WHERE id = :t"), {"t": biz.tenant_id}
    )
    await db_session.commit()
    resp = await start_draft(
        client,
        _url(biz),
        biz.headers(),
        description=DESCRIPTION,
        agenda=True,
        reservas={"mode": "services"},
    )
    assert resp.status_code in (404, 409), resp.text
    assert await _rows(db_session, biz.tenant_id, ReservationSettings) == []


async def test_without_the_switch_it_is_as_before(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    resp = await start_draft(client, _url(biz), biz.headers(), description=DESCRIPTION)
    assert resp.status_code == 202, resp.text
    assert await _rows(db_session, biz.tenant_id, ReservationSettings) == []
    job = await job_row(db_session, biz.tenant_id, resp.json()["job_id"])
    assert "agenda" not in job.progress["input"]


async def test_a_template_with_the_switch_off_drops_the_agenda(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    # Reservas encendido: la plantilla de salón traería la agenda.
    await start_draft(
        client,
        _url(biz),
        biz.headers(),
        name="Primero",
        description=DESCRIPTION,
        agenda=True,
        reservas={"mode": "services"},
    )
    resp = await start_draft(
        client,
        _url(biz),
        biz.headers(),
        name="Sin agenda",
        start="template",
        template_id="beauty_salon_v1",
        agenda=False,
    )
    assert resp.status_code == 202 and resp.json()["status"] == "done", resp.text
    agent_id = uuid.UUID(resp.json()["agent_id"])
    tools = await _agent_tools(db_session, biz, agent_id)
    assert not any(t.startswith("reservas.") for t in tools)


async def test_blank_with_the_switch_has_the_nine_and_the_procedures(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    resp = await start_draft(
        client,
        _url(biz),
        biz.headers(),
        name="En blanco",
        start="blank",
        description=None,
        agenda=True,
        reservas={"mode": "services"},
    )
    assert resp.status_code == 202 and resp.json()["status"] == "done", resp.text
    agent_id = uuid.UUID(resp.json()["agent_id"])
    assert set(RESERVAS_TOOLS) <= set(await _agent_tools(db_session, biz, agent_id))


async def test_a_builder_can_and_an_analyst_cannot(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    builder = await add_console_member(db_session, partner_id=biz.partner_id, role="builder")
    analyst = await add_console_member(db_session, partner_id=biz.partner_id, role="analyst")
    body = {
        "name": "Recepción",
        "description": DESCRIPTION,
        "agenda": True,
        "reservas": {"mode": "services"},
    }
    denied = await client.post(
        f"{_url(biz)}/agents/draft-jobs", json=body, headers=analyst["headers"]()
    )
    assert denied.status_code == 403, denied.text
    assert await _rows(db_session, biz.tenant_id, ReservationSettings) == []
    allowed = await client.post(
        f"{_url(biz)}/agents/draft-jobs", json=body, headers=builder["headers"]()
    )
    assert allowed.status_code == 202, allowed.text
    assert len(await _rows(db_session, biz.tenant_id, ReservationSettings)) == 1


async def test_a_tenant_in_the_body_is_refused(client: Any, biz: Biz) -> None:
    resp = await start_draft(
        client,
        _url(biz),
        biz.headers(),
        description=DESCRIPTION,
        agenda=True,
        tenant_id=str(uuid.uuid4()),
    )
    assert resp.status_code == 422, resp.text
