"""Requisito 9 — nada de la identidad de una máquina gasta.

Emparejar, renovar, declarar un directorio, desemparejar y archivar no consumen
modelo, reloj ni herramienta de pago, así que **no** dejan asiento en el libro.
Es una métrica de no-regresión: hoy se cumple, y el riesgo es romperla con buena
intención («vamos a apuntar el emparejamiento en el consumo para que se vea»).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from nexus_api.db.models import PartnerDevice, UsageLedger
from nexus_api.services.device_credential import issue_device_token

pytestmark = pytest.mark.asyncio


async def _ledger_rows(db_session) -> int:
    return int(await db_session.scalar(select(func.count()).select_from(UsageLedger)) or 0)


async def test_the_five_identity_acts_leave_the_ledger_untouched(client, db_session, console_world):
    a = console_world["a"]
    before = await _ledger_rows(db_session)

    # Emparejar: código emitido por la consola y canjeado por la máquina.
    issued = await client.post("/console/workstation/pairing-codes", headers=a["headers"]())
    assert issued.status_code == 201, issued.text
    paired = await client.post(
        "/device/pair",
        json={
            "code": issued.json()["code"],
            "hostname": "mac.local",
            "platform": "macos",
            "app_version": "0.2.0",
        },
    )
    assert paired.status_code == 201, paired.text
    token = paired.json()["credential"]
    auth = {"Authorization": f"Bearer {token}"}

    # Renovar, declarar, archivar.
    assert (await client.post("/device/renew", headers=auth)).status_code == 200
    linked = await client.post(
        f"/console/workstation/devices/{paired.json()['device_id']}/clients",
        headers=a["headers"](),
        json={"client_ref": a["ref"]},
    )
    assert linked.status_code == 201, linked.text
    declared = await client.post(
        "/device/links",
        headers=auth,
        json={
            "client_ref": a["ref"],
            "workdir": "/Users/a/proyecto",
            "checks": {"exists": True, "is_dir": True, "resolves_within": True, "readable": True},
        },
    )
    assert declared.status_code == 204, declared.text
    archived = await client.delete(
        f"/console/workstation/devices/{paired.json()['device_id']}", headers=a["headers"]()
    )
    assert archived.status_code == 204, archived.text

    assert await _ledger_rows(db_session) == before


async def test_a_direct_heartbeat_does_not_meter_either(client, db_session, console_world):
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
    before = await _ledger_rows(db_session)
    token = issue_device_token(device_id=device.id, partner_id=a["partner_id"], generation=1)
    for _ in range(3):
        response = await client.post(
            "/device/heartbeat", headers={"Authorization": f"Bearer {token}"}, json={}
        )
        assert response.status_code == 204
    assert await _ledger_rows(db_session) == before
