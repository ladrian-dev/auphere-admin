"""Spec 043 R1 — el admin activa Reservas y elige el modo en la pestaña Acceso.

Lo que fija este archivo:

- activar ``reservas`` sin modo, por primera vez, es un 422;
- activar con modo crea los ajustes con los valores de partida (y del tipo);
- cambiar de modo con reservas futuras vivas es un 409 con cuántas, y no toca
  nada; con ``cancel_and_notify`` las cancela, encola el aviso y cambia;
- activar prepara una versión del agente con ``reservas.*`` y sin ``booking.*``,
  sin promoverla; la activa no cambia;
- todo queda auditado con el operador.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Agent,
    AgentConfig,
    AgentConfigStatus,
    AuditLog,
    Reservation,
    ReservationOutbox,
    ReservationSettings,
)
from nexus_api.services import operator_identity

pytestmark = pytest.mark.asyncio


async def _headers(db_session, admin_headers) -> dict[str, str]:
    email = f"ops-{uuid.uuid4().hex[:8]}@auphere.test"
    async with db_session.begin():
        op = await operator_identity.create_account(
            db_session, email=email, password="operator-password-1", display_name="Ops"
        )
    return {**admin_headers, "X-Operator-Id": str(op.id)}


def _url(tenant_id: uuid.UUID) -> str:
    return f"/admin/tenants/{tenant_id}/client-access"


async def _agent(db_session, tenant_id: uuid.UUID) -> uuid.UUID:
    agent = Agent(tenant_id=tenant_id, name="Agente de reservas")
    db_session.add(agent)
    await db_session.flush()
    db_session.add(
        AgentConfig(
            tenant_id=tenant_id,
            agent_id=agent.id,
            version=1,
            status=AgentConfigStatus.ACTIVE,
            system_prompt_rendered="Eres el agente.",
            channels=[],
            tools=[
                "booking.check_availability",
                "booking.create_appointment",
                "escalate.escalate_to_human",
            ],
            policies={},
            created_by="test",
        )
    )
    await db_session.commit()
    return agent.id


async def test_activating_without_a_mode_is_refused(
    client, db_session, console_world, admin_headers
) -> None:
    w = console_world["a"]
    h = await _headers(db_session, admin_headers)
    r = await client.put(
        _url(w["tenant_id"]), headers=h, json={"enabled": True, "modules": ["panel", "reservas"]}
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "reservas_mode_required"
    capacity_without_kind = await client.put(
        _url(w["tenant_id"]),
        headers=h,
        json={"enabled": True, "modules": ["reservas"], "reservas": {"mode": "capacity"}},
    )
    assert capacity_without_kind.status_code == 422
    assert capacity_without_kind.json()["detail"]["code"] == "reservas_kind_required"


async def test_activating_creates_the_settings_and_stages_the_agent(
    client, db_session, console_world, admin_headers
) -> None:
    w = console_world["a"]
    agent_id = await _agent(db_session, w["tenant_id"])
    h = await _headers(db_session, admin_headers)
    r = await client.put(
        _url(w["tenant_id"]),
        headers=h,
        json={
            "enabled": True,
            "modules": ["panel", "reservas"],
            "reservas": {"mode": "capacity", "capacity_kind": "restaurant"},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["modules"] == ["panel", "reservas"]
    assert body["reservas"]["mode"] == "capacity"
    assert body["reservas"]["capacity_kind"] == "restaurant"
    assert body["reservas"]["live_future"] == 0
    assert body["reservas"]["agents_pending_promotion"] == [
        {"agent_id": str(agent_id), "name": "Agente de reservas", "version": 2}
    ]

    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, w["tenant_id"]):
        settings = await session.get(ReservationSettings, w["tenant_id"])
        assert settings is not None and settings.seats == 64 and settings.walkin_hold == 6
        configs = (
            (
                await session.execute(
                    sa.select(AgentConfig)
                    .where(AgentConfig.agent_id == agent_id)
                    .order_by(AgentConfig.version)
                )
            )
            .scalars()
            .all()
        )
    active, staged = configs
    assert active.status == AgentConfigStatus.ACTIVE  # nada se promueve solo
    assert staged.status == AgentConfigStatus.STAGED
    assert not any(t.startswith("booking.") for t in staged.tools)
    assert "reservas.create" in staged.tools and "escalate.escalate_to_human" in staged.tools


async def _versions(tenant_id: uuid.UUID, agent_id: uuid.UUID) -> list[AgentConfig]:
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        rows = await session.execute(
            sa.select(AgentConfig)
            .where(AgentConfig.agent_id == agent_id)
            .order_by(AgentConfig.version)
        )
        return list(rows.scalars().all())


async def test_switching_the_module_off_reaches_the_published_agent(
    client, db_session, console_world, admin_headers
) -> None:
    w = console_world["a"]
    agent_id = await _agent(db_session, w["tenant_id"])
    h = await _headers(db_session, admin_headers)
    on = await client.put(
        _url(w["tenant_id"]),
        headers=h,
        json={"enabled": True, "modules": ["panel", "reservas"], "reservas": {"mode": "services"}},
    )
    assert on.status_code == 200, on.text
    # La versión activa con la agenda: lo que deja publicar el borrador de activar.
    async with tenant_scoped_session(db_session, w["tenant_id"]):
        active = await db_session.scalar(
            sa.select(AgentConfig).where(
                AgentConfig.agent_id == agent_id, AgentConfig.status == AgentConfigStatus.ACTIVE
            )
        )
        assert active is not None
        active.tools = ["reservas.create", "reservas.find_slots", "escalate.escalate_to_human"]
    await db_session.commit()

    off = await client.put(
        _url(w["tenant_id"]), headers=h, json={"enabled": True, "modules": ["panel"]}
    )
    assert off.status_code == 200, off.text

    versions = await _versions(w["tenant_id"], agent_id)
    [live] = [v for v in versions if v.status == AgentConfigStatus.ACTIVE]
    assert live.version > active.version
    assert live.tools == ["escalate.escalate_to_human"]
    assert live.override_reason == "reservas_off"
    assert all(
        not any(t.startswith("reservas.") for t in v.tools)
        for v in versions
        if v.status == AgentConfigStatus.STAGED
    )

    again = await client.put(
        _url(w["tenant_id"]), headers=h, json={"enabled": True, "modules": ["panel"]}
    )
    assert again.status_code == 200, again.text
    assert len(await _versions(w["tenant_id"], agent_id)) == len(versions), "repetir no crea nada"


async def test_an_agent_that_books_with_a_connector_passes_to_reservas_in_its_draft(
    client, db_session, console_world, admin_headers
) -> None:
    """Spec 043, R11.5 (sustituye a la decisión del 2026-11-03): la cita nace en Reservas.
    Su borrador gana Reservas y pierde el conector; lo que atiende no cambia solo, y
    mientras tanto el panel dice que sigue reservando fuera."""
    w = console_world["a"]
    agent_id = await _agent(db_session, w["tenant_id"])
    async with tenant_scoped_session(db_session, w["tenant_id"]):
        active = await db_session.scalar(
            sa.select(AgentConfig).where(
                AgentConfig.agent_id == agent_id, AgentConfig.status == AgentConfigStatus.ACTIVE
            )
        )
        assert active is not None
        active.tools = ["CALENDLY_POST_INVITEE", "escalate.escalate_to_human"]
    await db_session.commit()
    h = await _headers(db_session, admin_headers)

    r = await client.put(
        _url(w["tenant_id"]),
        headers=h,
        json={"enabled": True, "modules": ["panel", "reservas"], "reservas": {"mode": "services"}},
    )

    assert r.status_code == 200, r.text
    body = r.json()["reservas"]
    assert [a["agent_id"] for a in body["agents_pending_promotion"]] == [str(agent_id)]
    assert body["agents_with_other_calendar"] == [
        {"agent_id": str(agent_id), "name": "Agente de reservas"}
    ]
    versions = await _versions(w["tenant_id"], agent_id)
    live = next(v for v in versions if v.status == AgentConfigStatus.ACTIVE)
    draft = next(v for v in versions if v.status == AgentConfigStatus.STAGED)
    assert "CALENDLY_POST_INVITEE" in live.tools
    assert "CALENDLY_POST_INVITEE" not in draft.tools
    assert "reservas.create" in draft.tools


async def test_a_template_with_reservas_needs_the_module(
    client, db_session, console_world, admin_headers
) -> None:
    w = console_world["a"]
    h = await _headers(db_session, admin_headers)
    body = {
        "seed_template_ref": "barbershop_v1",
        "placeholders": {
            "tenant.name": "Cultor Barber",
            "tenant.address": "Av. Apoquindo 1234",
            "tenant.timezone": "America/Santiago",
            "tenant.business_hours_label": "Lun-Sáb 10-19",
        },
    }

    off = await client.post(
        f"/admin/tenants/{w['tenant_id']}/agent-config/from-seed", headers=h, json=body
    )
    assert off.status_code == 409, off.text
    assert "Reservas" in off.json()["detail"]

    on = await client.put(
        _url(w["tenant_id"]),
        headers=h,
        json={"enabled": True, "modules": ["panel", "reservas"], "reservas": {"mode": "services"}},
    )
    assert on.status_code == 200, on.text
    applied = await client.post(
        f"/admin/tenants/{w['tenant_id']}/agent-config/from-seed", headers=h, json=body
    )
    assert applied.status_code == 201, applied.text


async def _live_booking(tenant_id: uuid.UUID) -> uuid.UUID:
    sm = get_sessionmaker()
    starts = datetime.now(UTC) + timedelta(days=2)
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        r = Reservation(
            tenant_id=tenant_id,
            mode="capacity",
            status="confirmed",
            starts_at=starts,
            ends_at=starts + timedelta(minutes=90),
            party_size=4,
            origin="person",
            channel="phone",
            created_by_kind="person",
            contact_name="Ana",
            contact_phone="+56911112222",
        )
        session.add(r)
        await session.flush()
        return r.id


async def test_changing_mode_with_live_bookings_needs_a_decision(
    client, db_session, console_world, admin_headers
) -> None:
    w = console_world["a"]
    h = await _headers(db_session, admin_headers)
    first = await client.put(
        _url(w["tenant_id"]),
        headers=h,
        json={
            "enabled": True,
            "modules": ["reservas"],
            "reservas": {"mode": "capacity", "capacity_kind": "bar"},
        },
    )
    assert first.status_code == 200, first.text
    booking = await _live_booking(w["tenant_id"])

    refused = await client.put(
        _url(w["tenant_id"]),
        headers=h,
        json={"enabled": True, "modules": ["reservas"], "reservas": {"mode": "services"}},
    )
    assert refused.status_code == 409
    assert refused.json()["detail"] == {"code": "live_reservations", "count": 1}

    done = await client.put(
        _url(w["tenant_id"]),
        headers=h,
        json={
            "enabled": True,
            "modules": ["reservas"],
            "reservas": {"mode": "services", "on_live": "cancel_and_notify"},
        },
    )
    assert done.status_code == 200, done.text
    assert done.json()["reservas"]["mode"] == "services"
    assert done.json()["reservas"]["live_future"] == 0

    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, w["tenant_id"]):
        res = await session.get(Reservation, booking)
        assert res is not None and res.status == "cancelled" and res.cancel_cause == "mode_change"
        outbox = (await session.execute(sa.select(ReservationOutbox))).scalars().all()
        assert [o.kind for o in outbox] == ["cancelled"]
        settings = await session.get(ReservationSettings, w["tenant_id"])
        assert settings is not None and settings.seats is None
    audit = (
        await db_session.execute(
            sa.select(AuditLog).where(AuditLog.action == "reservations.mode_changed")
        )
    ).scalar_one()
    assert audit.actor.startswith("operator:")
    assert audit.after_json == {"from": "capacity", "to": "services", "cancelled": 1}


async def test_changing_only_the_kind_never_cancels(
    client, db_session, console_world, admin_headers
) -> None:
    w = console_world["a"]
    h = await _headers(db_session, admin_headers)
    await client.put(
        _url(w["tenant_id"]),
        headers=h,
        json={
            "enabled": True,
            "modules": ["reservas"],
            "reservas": {"mode": "capacity", "capacity_kind": "bar"},
        },
    )
    await _live_booking(w["tenant_id"])
    r = await client.put(
        _url(w["tenant_id"]),
        headers=h,
        json={
            "enabled": True,
            "modules": ["reservas"],
            "reservas": {"mode": "capacity", "capacity_kind": "spa"},
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["reservas"]["capacity_kind"] == "spa"
    assert r.json()["reservas"]["live_future"] == 1


async def test_switching_the_module_off_keeps_the_settings(
    client, db_session, console_world, admin_headers
) -> None:
    w = console_world["a"]
    h = await _headers(db_session, admin_headers)
    await client.put(
        _url(w["tenant_id"]),
        headers=h,
        json={"enabled": True, "modules": ["panel", "reservas"], "reservas": {"mode": "services"}},
    )
    off = await client.put(
        _url(w["tenant_id"]), headers=h, json={"enabled": True, "modules": ["panel"]}
    )
    assert off.status_code == 200, off.text
    assert off.json()["modules"] == ["panel"]
    assert off.json()["reservas"]["mode"] == "services"
    back = await client.put(
        _url(w["tenant_id"]), headers=h, json={"enabled": True, "modules": ["panel", "reservas"]}
    )
    assert back.status_code == 200, back.text
