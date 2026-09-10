"""Requisito 3 — el código de emparejamiento y su canje (`contracts/pairing.md`).

El canal entre la consola y la cáscara es la persona: la consola emite, la barra
canjea. Un solo uso, diez minutos, un cuerpo único para todo fallo, límite de
intentos, y cada denegación con su motivo real en la auditoría aunque al llamante
no se le diga.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from nexus_api.db.models import AuditLog, DevicePairingCode, PartnerDevice
from nexus_api.services.device_credential import verify_device_token
from nexus_api.services.device_pairing import ALPHABET, normalize_code

pytestmark = pytest.mark.asyncio


def _machine(**over):
    body = {"hostname": "mac.local", "platform": "macos", "app_version": "0.2.0"}
    body.update(over)
    return body


async def test_the_person_gets_a_code_and_the_machine_exchanges_it_once(
    client, db_session, console_world
):
    a = console_world["a"]
    issued = await client.post("/console/workstation/pairing-codes", headers=a["headers"]())
    assert issued.status_code == 201, issued.text
    code = issued.json()["code"]
    assert len(code) == 9 and code[4] == "-", code
    assert all(ch in ALPHABET for ch in code.replace("-", ""))

    paired = await client.post("/device/pair", json=_machine(code=code.lower()))
    assert paired.status_code == 201, paired.text
    body = paired.json()
    claims = verify_device_token(body["credential"])
    assert claims.partner_id == a["partner_id"]
    assert body["principal_id"] == a["user_id"]
    assert body["partner_slug"] == a["slug"]
    assert body["display_name"] == "mac.local"

    device = await db_session.get(PartnerDevice, uuid.UUID(body["device_id"]))
    assert device is not None
    assert (device.partner_id, device.principal_id) == (a["partner_id"], a["user_id"])

    # Segunda vez: no.
    again = await client.post("/device/pair", json=_machine(code=code))
    assert again.status_code == 404
    assert again.json() == {"code": "pairing_code_invalid"}


async def test_expired_unknown_and_foreign_codes_get_the_same_answer(
    client, db_session, console_world
):
    a = console_world["a"]
    issued = await client.post("/console/workstation/pairing-codes", headers=a["headers"]())
    code = issued.json()["code"]
    row = (await db_session.execute(select(DevicePairingCode))).scalars().one()
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()

    answers = []
    for candidate in (code, "AAAA-BBBB", "zzzz-2222"):
        response = await client.post("/device/pair", json=_machine(code=candidate))
        answers.append((response.status_code, response.json()))
    assert all(a_ == (404, {"code": "pairing_code_invalid"}) for a_ in answers), answers


async def test_a_code_belongs_to_the_partner_and_person_who_asked(client, console_world):
    """Un código de B, canjeado por cualquiera, da una máquina de B — nunca de A."""
    b = console_world["b"]
    issued = await client.post("/console/workstation/pairing-codes", headers=b["headers"]())
    paired = await client.post("/device/pair", json=_machine(code=issued.json()["code"]))
    assert paired.status_code == 201
    claims = verify_device_token(paired.json()["credential"])
    assert claims.partner_id == b["partner_id"]
    assert claims.partner_id != console_world["a"]["partner_id"]


async def test_issuing_a_new_code_invalidates_the_previous_one(client, console_world):
    a = console_world["a"]
    first = (await client.post("/console/workstation/pairing-codes", headers=a["headers"]())).json()
    second = (
        await client.post("/console/workstation/pairing-codes", headers=a["headers"]())
    ).json()
    assert (await client.post("/device/pair", json=_machine(code=first["code"]))).status_code == 404
    assert (
        await client.post("/device/pair", json=_machine(code=second["code"]))
    ).status_code == 201


async def test_too_many_failures_from_one_machine_wait(client, console_world):
    for _ in range(5):
        response = await client.post("/device/pair", json=_machine(code="AAAA-AAAA"))
        assert response.status_code == 404
    sixth = await client.post("/device/pair", json=_machine(code="AAAA-AAAA"))
    assert sixth.status_code == 429
    assert sixth.json() == {"code": "pairing_rate_limited"}
    assert int(sixth.headers["Retry-After"]) >= 1


async def test_every_denial_is_audited_with_its_real_reason(client, db_session, console_world):
    await client.post("/device/pair", json=_machine(code="not a code"))
    await client.post("/device/pair", json=_machine(code="AAAA-AAAA"))
    rows = (
        (await db_session.execute(select(AuditLog).where(AuditLog.action == "device.pair_denied")))
        .scalars()
        .all()
    )
    reasons = {row.after_json["reason"] for row in rows}
    assert reasons == {"malformed", "unknown_expired_or_used"}


async def test_pairing_is_audited_with_the_person_as_actor(client, db_session, console_world):
    a = console_world["a"]
    issued = await client.post("/console/workstation/pairing-codes", headers=a["headers"]())
    await client.post("/device/pair", json=_machine(code=issued.json()["code"]))
    rows = (
        (await db_session.execute(select(AuditLog).where(AuditLog.action == "device.paired")))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].actor.endswith(a["user_id"])
    assert rows[0].target == f"partner:{a['partner_id']}"


async def test_an_analyst_cannot_ask_for_a_code(client, db_session, console_world):
    from tests.conftest import add_console_member

    analyst = await add_console_member(
        db_session, partner_id=console_world["a"]["partner_id"], role="analyst"
    )
    response = await client.post("/console/workstation/pairing-codes", headers=analyst["headers"]())
    assert response.status_code == 403


def test_normalization_reads_what_a_person_would_type():
    assert normalize_code(" k7mp-4xq2 ") == "K7MP4XQ2"
    assert normalize_code("K7MP4XQ2") == "K7MP4XQ2"
    assert normalize_code("K7MP-4XQ") is None  # corto
    assert normalize_code("K7MP-4XQ0") is None  # el 0 no está en el alfabeto
