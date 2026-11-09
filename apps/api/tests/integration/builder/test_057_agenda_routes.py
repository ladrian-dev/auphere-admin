"""Spec 057, historia 3 — «Agenda (Reservas)» de un agente ya creado (requisitos 2, 3,
4.4 y 7; ``contracts/console-api.md`` §3 a §5 y §8).

Activar pone las nueve de una vez en el borrador (y enciende Reservas si hace falta,
con confirmación del modo); desactivar las quita sin apagar el módulo ni tocar reservas.
En un agente estructurado, cada cambio encola la propuesta de texto, que nunca se aplica
sola y se mide como construcción.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import (
    AgentConfig,
    AgentConfigStatus,
    AuditLog,
    ClientAccess,
    Job,
    ReservationSettings,
)
from nexus_api.db.models.agent_spec import Proposal
from nexus_api.services.reservations.passing import RESERVAS_TOOLS
from tests.conftest import add_console_member

from ..business._business_world import Biz, new_business
from ._builder_world import job_row, run_jobs, start_draft

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def biz(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> Biz:
    return await new_business(client, db_session, console_world, name="Spa Jemma")


async def _agent(client: Any, biz: Biz, name: str = "Recepción") -> uuid.UUID:
    resp = await start_draft(
        client,
        f"/console/clients/{biz.ref}",
        biz.headers(),
        name=name,
        start="blank",
        description=None,
        agenda=False,
    )
    assert resp.status_code == 202, resp.text
    return uuid.UUID(resp.json()["agent_id"])


def _url(biz: Biz, agent_id: uuid.UUID) -> str:
    return f"/console/clients/{biz.ref}/agents/{agent_id}/agenda"


async def _draft_tools(db_session: AsyncSession, biz: Biz, agent_id: uuid.UUID) -> list[str]:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        cfg = await db_session.scalar(
            sa.select(AgentConfig)
            .where(AgentConfig.agent_id == agent_id, AgentConfig.status == AgentConfigStatus.STAGED)
            .execution_options(populate_existing=True)
        )
    assert cfg is not None
    return list(cfg.tools or [])


async def _rows(db_session: AsyncSession, biz: Biz, stmt: Any) -> list[Any]:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        return list(
            (await db_session.scalars(stmt.execution_options(populate_existing=True))).all()
        )


async def test_get_tells_the_state(client: Any, biz: Biz) -> None:
    agent_id = await _agent(client, biz)
    got = await client.get(_url(biz, agent_id), headers=biz.headers())
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["offered"] is True
    assert body["module"]["on"] is False
    assert body["ready"] is False and body["missing"] == ["reservas_off"]
    assert body["state"] == "none" and body["structured"] is True
    assert body["suggested"]["mode"] == "services"
    assert body["can_write"] is True and body["max_tools"] == 60


async def test_turning_it_on_without_a_mode_is_refused(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    agent_id = await _agent(client, biz)
    resp = await client.put(_url(biz, agent_id), json={"enabled": True}, headers=biz.headers())
    assert resp.status_code == 422, resp.text
    assert "reservas_mode_required" in resp.text
    assert await _rows(db_session, biz, sa.select(ReservationSettings)) == []
    assert not any(t.startswith("reservas.") for t in await _draft_tools(db_session, biz, agent_id))


async def test_turning_it_on_does_it_all_at_once(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, biz)
    other = await _agent(client, biz, name="Cobros")
    resp = await client.put(
        _url(biz, agent_id),
        json={"enabled": True, "reservas": {"mode": "services", "capacity_kind": None}},
        headers=biz.headers(),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["module"]["on"] is True and body["module"]["mode"] == "services"
    assert body["draft"] == {"on": True, "tools_on": 9}
    assert body["state"] == "prepared"
    assert body["job"] is not None and body["proposal_reason"] is None
    assert set(RESERVAS_TOOLS) <= set(await _draft_tools(db_session, biz, agent_id))
    # Encender el módulo no le da la agenda a quien no da citas (garantía 2).
    assert not any(t.startswith("reservas.") for t in await _draft_tools(db_session, biz, other))
    [access] = await _rows(db_session, biz, sa.select(ClientAccess))
    assert "reservas" in access.modules and access.enabled is False
    actions = {a.action for a in await _rows(db_session, biz, sa.select(AuditLog))}
    assert {"client_access.updated", "console.agenda.update"} <= actions

    # El trabajo escribe la propuesta (sin modelo: el respaldo) y no aplica nada.
    await run_jobs(fake_redis, None)
    job = await job_row(db_session, biz.tenant_id, body["job"]["id"])
    assert job.status == "done", job.error_code
    assert job.result["proposal_id"] is not None and job.result["fallback"] is True
    [proposal] = await _rows(db_session, biz, sa.select(Proposal))
    assert proposal.author == "builder" and proposal.status == "open"
    assert (proposal.expires_at - proposal.created_at).days >= 6
    assert all(
        not str(op["path"]).startswith(("/tools", "/identity", "/voice"))
        for op in proposal.diff["ops"]
    )

    listed = await client.get(
        f"/console/clients/{biz.ref}/agents/{agent_id}/proposals", headers=biz.headers()
    )
    assert listed.status_code == 200, listed.text
    [shown] = [p for p in listed.json() if p["id"] == str(proposal.id)]
    assert all("before" in op for op in shown["diff"]["ops"])

    state = (await client.get(_url(biz, agent_id), headers=biz.headers())).json()
    assert state["proposal"] == {"id": str(proposal.id), "status": "open"}
    assert state["job"] is None


async def test_repeating_does_nothing(client: Any, db_session: AsyncSession, biz: Biz) -> None:
    agent_id = await _agent(client, biz)
    body = {"enabled": True, "reservas": {"mode": "services"}}
    await client.put(_url(biz, agent_id), json=body, headers=biz.headers())
    again = await client.put(_url(biz, agent_id), json=body, headers=biz.headers())
    assert again.status_code == 200, again.text
    jobs = await _rows(db_session, biz, sa.select(Job).where(Job.kind == "agenda_text"))
    assert len(jobs) == 1


async def test_turning_it_off_keeps_the_module(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    agent_id = await _agent(client, biz)
    await client.put(
        _url(biz, agent_id),
        json={"enabled": True, "reservas": {"mode": "services"}},
        headers=biz.headers(),
    )
    off = await client.put(_url(biz, agent_id), json={"enabled": False}, headers=biz.headers())
    assert off.status_code == 200, off.text
    assert off.json()["module"]["on"] is True
    assert off.json()["draft"] == {"on": False, "tools_on": 0}
    assert not any(t.startswith("reservas.") for t in await _draft_tools(db_session, biz, agent_id))
    assert len(await _rows(db_session, biz, sa.select(ReservationSettings))) == 1


async def test_too_many_tools_writes_nothing(
    client: Any, db_session: AsyncSession, biz: Biz, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus_api.api.console import capabilities_client

    agent_id = await _agent(client, biz)
    monkeypatch.setattr(capabilities_client, "_MAX_SPEC_TOOLS", 5)
    resp = await client.put(
        _url(biz, agent_id),
        json={"enabled": True, "reservas": {"mode": "services"}},
        headers=biz.headers(),
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"] == {"code": "too_many_tools", "max": 5}
    assert not any(t.startswith("reservas.") for t in await _draft_tools(db_session, biz, agent_id))
    # Lo que encendió antes de fallar se deshace con la transacción.
    assert await _rows(db_session, biz, sa.select(ReservationSettings)) == []


async def test_without_build_budget_the_tools_change_anyway(
    client: Any, db_session: AsyncSession, biz: Biz, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus_api.api.console import agenda

    async def _exhausted(_partner_id: Any) -> None:
        raise HTTPException(status_code=402, detail={"code": "build_budget_exhausted"})

    monkeypatch.setattr(agenda, "require_build_room", _exhausted)
    agent_id = await _agent(client, biz)
    resp = await client.put(
        _url(biz, agent_id),
        json={"enabled": True, "reservas": {"mode": "services"}},
        headers=biz.headers(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["proposal_reason"] == "build_budget_exhausted"
    assert set(RESERVAS_TOOLS) <= set(await _draft_tools(db_session, biz, agent_id))
    assert await _rows(db_session, biz, sa.select(Job).where(Job.kind == "agenda_text")) == []


async def test_an_analyst_reads_and_cannot_write(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    agent_id = await _agent(client, biz)
    analyst = await add_console_member(db_session, partner_id=biz.partner_id, role="analyst")
    got = await client.get(_url(biz, agent_id), headers=analyst["headers"]())
    assert got.status_code == 200, got.text
    assert got.json()["can_write"] is False
    denied = await client.put(
        _url(biz, agent_id),
        json={"enabled": True, "reservas": {"mode": "services"}},
        headers=analyst["headers"](),
    )
    assert denied.status_code == 403, denied.text
    assert await _rows(db_session, biz, sa.select(ReservationSettings)) == []


async def test_the_tools_dialog_has_the_nine(client: Any, biz: Biz) -> None:
    agent_id = await _agent(client, biz)
    got = await client.get(f"{_url(biz, agent_id)}/tools?lang=es", headers=biz.headers())
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["slug"] == "reservas" and body["permission"] is None
    assert [t["name"] for t in body["tools"]] == list(RESERVAS_TOOLS)
    reads = {t["name"] for t in body["tools"] if t["read_only"]}
    assert reads == {"reservas.services", "reservas.find_slots", "reservas.list_mine"}
    assert all(t["needs_write_permission"] is False for t in body["tools"])


async def test_turning_it_off_takes_the_names_out_of_the_procedures(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    """Un agente creado con la agenda tiene procedimientos que citan las herramientas.
    Apagarla las quita también de ``procedures[].tools``: el AgentSpec sigue validando y
    las frases las cambia la propuesta (2.5, research R2)."""
    resp = await start_draft(
        client,
        f"/console/clients/{biz.ref}",
        biz.headers(),
        name="Con agenda",
        start="blank",
        description=None,
        agenda=True,
        reservas={"mode": "services"},
    )
    assert resp.status_code == 202, resp.text
    agent_id = uuid.UUID(resp.json()["agent_id"])
    off = await client.put(_url(biz, agent_id), json={"enabled": False}, headers=biz.headers())
    assert off.status_code == 200, off.text
    draft = (
        await client.get(
            f"/console/clients/{biz.ref}/agents/{agent_id}/draft", headers=biz.headers()
        )
    ).json()
    cited = {t for p in draft["spec"].get("procedures") or [] for t in p.get("tools") or []}
    assert not any(t.startswith("reservas.") for t in cited)
    assert not any(t.startswith("reservas.") for t in draft["spec"]["tools"])


async def test_retrying_after_a_failed_proposal_asks_again(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    """3.5: «Reintentar» repite el mismo cambio. Las herramientas ya están, pero si el
    último trabajo de la propuesta falló, se vuelve a pedir."""
    agent_id = await _agent(client, biz)
    body = {"enabled": True, "reservas": {"mode": "services"}}
    first = await client.put(_url(biz, agent_id), json=body, headers=biz.headers())
    assert first.status_code == 200, first.text
    async with tenant_scoped_session(db_session, biz.tenant_id):
        await db_session.execute(
            sa.update(Job)
            .where(Job.kind == "agenda_text")
            .values(status="failed", error_code="builder_unavailable", finished_at=sa.func.now())
        )
    again = await client.put(_url(biz, agent_id), json=body, headers=biz.headers())
    assert again.status_code == 200, again.text
    jobs = await _rows(db_session, biz, sa.select(Job).where(Job.kind == "agenda_text"))
    assert sorted(j.status for j in jobs) == ["failed", "queued"]
