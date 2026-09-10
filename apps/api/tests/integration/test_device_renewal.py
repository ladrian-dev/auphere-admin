"""Requisito 10 — la credencial se renueva sola y caduca con el abandono.

Una máquina renueva antes de que le queden 6 h; el servidor sube la generación y
acepta la anterior **60 segundos** —lo que tarda un fallo de red en resolverse—
y ni uno más. Treinta días sin latir y hay que volver a emparejar. Cada renovación
deja asiento **con la máquina como actor**, no con una persona (Requisito 13.1).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from nexus_api.db.models import AuditLog, PartnerDevice
from nexus_api.services.device_credential import issue_device_token, verify_device_token

pytestmark = pytest.mark.asyncio


async def _paired(db_session, console_world, *, beat_ago: timedelta = timedelta(0)):
    w = console_world["a"]
    device = PartnerDevice(
        id=uuid.uuid4(),
        partner_id=w["partner_id"],
        principal_id=w["user_id"],
        display_name="mac",
        hostname="mac.local",
        platform="macos",
        last_heartbeat_at=datetime.now(UTC) - beat_ago,
    )
    db_session.add(device)
    await db_session.commit()
    token = issue_device_token(device_id=device.id, partner_id=w["partner_id"], generation=1)
    return device, token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_renewing_rotates_the_generation_and_returns_a_fresh_credential(
    client, db_session, console_world
):
    device, token = await _paired(db_session, console_world)
    response = await client.post("/device/renew", headers=_auth(token))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["generation"] == 2
    claims = verify_device_token(body["credential"])
    assert (claims.device_id, claims.generation) == (device.id, 2)
    await db_session.refresh(device)
    assert device.credential_generation == 2
    assert device.credential_rotated_at is not None


async def test_the_previous_generation_survives_the_grace_window_and_not_a_second_more(
    client, db_session, console_world
):
    device, old = await _paired(db_session, console_world)
    new = (await client.post("/device/renew", headers=_auth(old))).json()["credential"]
    # Dentro de la gracia: la vieja sigue latiendo.
    assert (await client.post("/device/heartbeat", headers=_auth(old), json={})).status_code == 204
    assert (await client.post("/device/heartbeat", headers=_auth(new), json={})).status_code == 204
    # Fuera de la gracia: solo la nueva.
    device.credential_rotated_at = datetime.now(UTC) - timedelta(seconds=61)
    await db_session.commit()
    assert (await client.post("/device/heartbeat", headers=_auth(old), json={})).status_code == 401
    assert (await client.post("/device/heartbeat", headers=_auth(new), json={})).status_code == 204


async def test_thirty_days_without_a_heartbeat_means_pairing_again(
    client, db_session, console_world
):
    _, token = await _paired(db_session, console_world, beat_ago=timedelta(days=31))
    for call in (
        client.post("/device/renew", headers=_auth(token)),
        client.post("/device/heartbeat", headers=_auth(token), json={}),
        client.get("/device/poll", headers=_auth(token)),
    ):
        response = await call
        assert response.status_code == 403
        assert response.json()["code"] == "pairing_required"


async def test_twenty_nine_days_is_still_fine(client, db_session, console_world):
    _, token = await _paired(db_session, console_world, beat_ago=timedelta(days=29))
    assert (await client.post("/device/renew", headers=_auth(token))).status_code == 200


async def test_a_renewal_is_audited_with_the_machine_as_actor(client, db_session, console_world):
    device, token = await _paired(db_session, console_world)
    await client.post("/device/renew", headers=_auth(token))
    rows = (
        (await db_session.execute(select(AuditLog).where(AuditLog.action == "device.renewed")))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].actor == f"device:{device.id}"
    assert rows[0].target == f"partner:{console_world['a']['partner_id']}"
