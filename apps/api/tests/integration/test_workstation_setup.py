"""Requisito 6 — la puesta en marcha, derivada por persona en cada visita.

No hay tabla: cada paso se calcula de los datos. Sin ``workstation:pair`` no hay
pasos (6.5): a quien no puede emparejar no se le enseña ni apagado.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from nexus_api.db.models import DeviceClientLink, LocalExecutable, PartnerDevice

pytestmark = pytest.mark.asyncio


async def _steps(client, headers) -> dict[str, dict]:
    response = await client.get("/console/workstation/setup", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    return {s["key"]: s for s in body["steps"]} | {"_complete": {"done": body["complete"]}}


async def test_nothing_paired_means_four_pending_steps(client, console_world):
    steps = await _steps(client, console_world["a"]["headers"]())
    assert [
        k for k in ("paired", "clients", "directories", "executables") if not steps[k]["done"]
    ] == [
        "paired",
        "clients",
        "directories",
        "executables",
    ]
    assert steps["_complete"]["done"] is False


async def test_each_fact_turns_its_step_green(client, db_session, console_world):
    a = console_world["a"]
    device = PartnerDevice(
        id=uuid.uuid4(),
        partner_id=a["partner_id"],
        principal_id=a["user_id"],
        display_name="mac",
        hostname="mac.local",
        platform="macos",
        last_heartbeat_at=datetime.now(UTC),
    )
    db_session.add(device)
    await db_session.commit()
    steps = await _steps(client, a["headers"]())
    assert steps["paired"]["done"] is True
    assert steps["clients"]["done"] is False

    link = DeviceClientLink(
        id=uuid.uuid4(), tenant_id=a["tenant_id"], device_id=device.id, created_by=a["user_id"]
    )
    db_session.add(link)
    await db_session.commit()
    steps = await _steps(client, a["headers"]())
    assert steps["clients"]["done"] is True
    assert (steps["directories"]["done"], steps["directories"]["pending"]) == (False, 1)

    link.workdir = "/Users/a/cliente"
    db_session.add(
        LocalExecutable(
            id=uuid.uuid4(), tenant_id=a["tenant_id"], executable="make", added_by="auphere"
        )
    )
    await db_session.commit()
    steps = await _steps(client, a["headers"]())
    assert steps["directories"]["done"] is True
    assert steps["executables"]["done"] is True
    assert steps["_complete"]["done"] is True


async def test_the_steps_are_per_person_not_per_partner(client, db_session, console_world):
    """La máquina de la owner no cuenta para la builder: cada persona empareja la suya."""
    from tests.conftest import add_console_member

    a = console_world["a"]
    db_session.add(
        PartnerDevice(
            id=uuid.uuid4(),
            partner_id=a["partner_id"],
            principal_id=a["user_id"],
            display_name="mac",
            hostname="mac.local",
            platform="macos",
        )
    )
    await db_session.commit()
    builder = await add_console_member(db_session, partner_id=a["partner_id"], role="builder")
    assert (await _steps(client, a["headers"]()))["paired"]["done"] is True
    assert (await _steps(client, builder["headers"]()))["paired"]["done"] is False


async def test_without_the_pair_permission_there_are_no_steps(client, db_session, console_world):
    from tests.conftest import add_console_member

    analyst = await add_console_member(
        db_session, partner_id=console_world["a"]["partner_id"], role="analyst"
    )
    response = await client.get("/console/workstation/setup", headers=analyst["headers"]())
    assert response.status_code == 403
