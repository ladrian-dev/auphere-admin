"""Spec 057, requisitos 1.4, 1.8, 5.2, 7.3 y 7.5 — encender Reservas desde un agente.

Corre bajo la RLS del cliente (``nexus_app``), como cualquier ruta de la consola con
``client_scope``: añade ``reservas`` a los módulos sin tocar ``enabled`` ni los demás,
crea los ajustes con el modo elegido, prepara la agenda solo a los otros agentes que
dan citas y lo deja dicho en la auditoría. Nunca hace ``RESET ROLE``.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Agent,
    AgentConfig,
    AgentConfigStatus,
    AuditLog,
    ClientAccess,
    ReservationSettings,
)
from nexus_api.services.reservations.admin import Choice, ReservasChoiceError
from nexus_api.services.reservations.turn_on import TurnOnRefused, turn_on_from_agent

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

ACTOR = "console:owner@partner.test"


def _spec(description: str, *, tools: list[str] | None = None) -> dict[str, Any]:
    return {
        "schema_version": "1",
        "mode": "instructions",
        "identity": {"name": "Agente", "description": description},
        "instructions": {"legacy_text": description},
        "tools": tools or [],
        "ai_disclosure": {"decided": False},
        "model_policy": {"kind": "profile", "profile": "auto"},
        "memory": {"scope": "shared"},
    }


async def _agent(tenant_id: uuid.UUID, name: str, description: str, version: int) -> uuid.UUID:
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        agent = Agent(tenant_id=tenant_id, name=name)
        session.add(agent)
        await session.flush()
        session.add(
            AgentConfig(
                tenant_id=tenant_id,
                agent_id=agent.id,
                version=version,
                status=AgentConfigStatus.ACTIVE,
                system_prompt_rendered=description,
                channels=[],
                tools=["escalate.escalate_to_human"],
                policies={},
                spec=_spec(description, tools=["escalate.escalate_to_human"]),
                created_by="test",
            )
        )
        await session.commit()
        return agent.id


async def _turn_on(w: dict[str, Any], *, choice: Choice | None, origin: uuid.UUID | None) -> Any:
    async with get_sessionmaker()() as session, tenant_scoped_session(session, w["tenant_id"]):
        out = await turn_on_from_agent(
            session,
            tenant_id=w["tenant_id"],
            partner_id=w["partner_id"],
            choice=choice,
            actor=ACTOR,
            origin_agent_id=origin,
            now=datetime.now(UTC),
        )
        role = await session.scalar(sa.text("SELECT current_user"))
        await session.commit()
        return out, role


async def _read(tenant_id: uuid.UUID, stmt: Any) -> Any:
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        return (await session.execute(stmt)).scalars().all()


async def test_it_turns_reservas_on_keeping_the_rest(db_session, console_world) -> None:
    w = console_world["a"]
    db_session.add(
        ClientAccess(
            tenant_id=w["tenant_id"], partner_id=w["partner_id"], enabled=True, modules=["panel"]
        )
    )
    await db_session.commit()

    out, role = await _turn_on(w, choice=Choice(mode="services"), origin=None)

    assert out.turned_on is True and out.mode == "services"
    assert role == "nexus_app"  # sin RESET ROLE: la petición sigue bajo la RLS
    [access] = await _read(w["tenant_id"], sa.select(ClientAccess))
    assert access.enabled is True
    assert list(access.modules) == ["panel", "reservas"]
    [settings] = await _read(w["tenant_id"], sa.select(ReservationSettings))
    assert settings.mode == "services"
    audits = await _read(
        w["tenant_id"], sa.select(AuditLog).where(AuditLog.action == "client_access.updated")
    )
    assert audits and audits[-1].actor == ACTOR
    assert audits[-1].after_json["mode"] == "services"
    assert "from_agent" in audits[-1].after_json


async def test_without_access_it_creates_it_closed(db_session, console_world) -> None:
    w = console_world["a"]
    out, _ = await _turn_on(
        w, choice=Choice(mode="capacity", capacity_kind="restaurant"), origin=None
    )
    assert out.turned_on is True
    [access] = await _read(w["tenant_id"], sa.select(ClientAccess))
    assert access.enabled is False
    assert access.partner_id == w["partner_id"]
    assert list(access.modules) == ["reservas"]


async def test_the_mode_is_required_the_first_time(db_session, console_world) -> None:
    w = console_world["a"]
    with pytest.raises(ReservasChoiceError) as exc:
        await _turn_on(w, choice=None, origin=None)
    assert exc.value.code == "reservas_mode_required"
    assert await _read(w["tenant_id"], sa.select(ReservationSettings)) == []


@pytest.mark.parametrize(
    ("choice", "code"),
    [
        (Choice(mode="capacity"), "reservas_kind_required"),
        (Choice(mode="services", capacity_kind="restaurant"), "reservas_kind_forbidden"),
    ],
)
async def test_a_wrong_mode_is_refused(db_session, console_world, choice, code) -> None:
    w = console_world["a"]
    with pytest.raises(ReservasChoiceError) as exc:
        await _turn_on(w, choice=choice, origin=None)
    assert exc.value.code == code


async def test_already_on_does_nothing(db_session, console_world) -> None:
    w = console_world["a"]
    await _turn_on(w, choice=Choice(mode="services"), origin=None)
    out, _ = await _turn_on(w, choice=Choice(mode="capacity", capacity_kind="bar"), origin=None)
    assert out.turned_on is False and out.mode == "services"  # el modo no cambia desde aquí


async def test_an_archived_client_is_refused(db_session, console_world) -> None:
    w = console_world["a"]
    await db_session.execute(
        sa.text("UPDATE tenants SET status = 'archived' WHERE id = :t"), {"t": w["tenant_id"]}
    )
    await db_session.commit()
    with pytest.raises(TurnOnRefused) as exc:
        await _turn_on(w, choice=Choice(mode="services"), origin=None)
    assert exc.value.code == "archived"


async def test_two_at_once_turn_it_on_once(db_session, console_world) -> None:
    w = console_world["a"]
    results = await asyncio.gather(
        _turn_on(w, choice=Choice(mode="services"), origin=None),
        _turn_on(w, choice=Choice(mode="services"), origin=None),
    )
    assert sorted(r[0].turned_on for r in results) == [False, True]
    assert len(await _read(w["tenant_id"], sa.select(ReservationSettings))) == 1


async def test_only_the_other_agents_that_give_appointments_get_a_draft(
    db_session, console_world
) -> None:
    w = console_world["a"]
    origin = await _agent(w["tenant_id"], "Recepción", "Da citas y cambia citas del salón.", 1)
    other = await _agent(w["tenant_id"], "Reservas web", "Reservas citas para las clientas.", 2)
    billing = await _agent(
        w["tenant_id"], "Cobros", "Revisas los comprobantes de pago de las clientas.", 3
    )

    out, _ = await _turn_on(w, choice=Choice(mode="services"), origin=origin)

    assert {p.agent_id for p in out.prepared} == {other}
    drafts = await _read(
        w["tenant_id"],
        sa.select(AgentConfig).where(AgentConfig.status == AgentConfigStatus.STAGED),
    )
    assert {d.agent_id for d in drafts} == {other}
    assert "reservas.create" in drafts[0].tools
    assert billing not in {d.agent_id for d in drafts}
