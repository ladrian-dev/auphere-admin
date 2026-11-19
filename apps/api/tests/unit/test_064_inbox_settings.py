"""Spec 064, requisito 5.1 — los ajustes de la Bandeja del cliente.

Un solo valor: tras cuánto tiempo sin mensajes se resuelve sola una
conversación que lleva el agente. ``null`` es «nunca», y es el valor de partida.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from nexus_api.db.models import AuditLog, ClientAccess
from tests.conftest import make_inbox

pytestmark = pytest.mark.asyncio

URL = "/console/lite/inbox/settings"


async def _stored(db_session, tenant_id) -> int | None:
    db_session.expire_all()
    return await db_session.scalar(
        sa.select(ClientAccess.inbox_autoclose_hours).where(ClientAccess.tenant_id == tenant_id)
    )


async def test_it_starts_at_never(client, db_session, console_world) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    r = await client.get(URL, headers=inbox["headers"]())
    assert r.status_code == 200, r.text
    assert r.json() == {"autoclose_hours": None}


@pytest.mark.parametrize("hours", [24, 72, 168, 720, None])
async def test_it_takes_the_four_terms_and_never(client, db_session, console_world, hours) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    if hours is None:  # de un plazo a «nunca»
        await client.patch(URL, headers=inbox["headers"](), json={"autoclose_hours": 24})
    r = await client.patch(URL, headers=inbox["headers"](), json={"autoclose_hours": hours})
    assert r.status_code == 200, r.text
    assert r.json() == {"autoclose_hours": hours}
    assert await _stored(db_session, w["tenant_id"]) == hours
    assert (await client.get(URL, headers=inbox["headers"]())).json() == {"autoclose_hours": hours}


@pytest.mark.parametrize("hours", [0, 1, 48, 1000, -24])
async def test_another_term_names_the_field(client, db_session, console_world, hours) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    r = await client.patch(URL, headers=inbox["headers"](), json={"autoclose_hours": hours})
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == {"code": "invalid", "field": "autoclose_hours"}
    assert await _stored(db_session, w["tenant_id"]) is None


async def test_the_body_takes_nothing_else(client, db_session, console_world) -> None:
    """Ni un cliente ni nada más: el cliente sale de la sesión (constitución §I)."""
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    other = console_world["b"]["tenant_id"]
    r = await client.patch(
        URL, headers=inbox["headers"](), json={"autoclose_hours": 24, "tenant_id": str(other)}
    )
    assert r.status_code == 422, r.text
    assert await _stored(db_session, w["tenant_id"]) is None


async def test_a_change_is_audited_with_before_and_after(client, db_session, console_world) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    await client.patch(URL, headers=inbox["headers"](), json={"autoclose_hours": 24})
    await client.patch(URL, headers=inbox["headers"](), json={"autoclose_hours": 168})
    # Guardar lo mismo no deja otra línea.
    await client.patch(URL, headers=inbox["headers"](), json={"autoclose_hours": 168})
    rows = (
        await db_session.execute(
            sa.select(AuditLog.actor, AuditLog.before_json, AuditLog.after_json)
            .where(
                AuditLog.tenant_id == w["tenant_id"], AuditLog.action == "inbox.settings_changed"
            )
            .order_by(AuditLog.created_at)
        )
    ).all()
    assert [(b, a) for _, b, a in rows] == [
        ({"autoclose_hours": None}, {"autoclose_hours": 24}),
        ({"autoclose_hours": 24}, {"autoclose_hours": 168}),
    ]
    assert all(actor.startswith("client:") for actor, _, _ in rows)


async def test_without_the_inbox_there_are_no_settings(client, db_session, console_world) -> None:
    w = console_world["a"]
    inbox = await make_inbox(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"], modules=("panel", "usage")
    )
    assert (await client.get(URL, headers=inbox["headers"]())).status_code == 403
    r = await client.patch(URL, headers=inbox["headers"](), json={"autoclose_hours": 24})
    assert r.status_code == 403
    assert await _stored(db_session, w["tenant_id"]) is None
