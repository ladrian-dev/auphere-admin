"""Spec 031 · R8.2, R10.2, R11.2, R11.4 — lo que el teléfono decide de sí mismo
(tareas T088, T101 y T102).

- ``PUT /phones/current/push``: el destino de avisos de este teléfono. Un
  destino tiene un solo dueño: si aparece en otra fila, se le quita.
- ``GET/PUT /phones/current/notices``: los interruptores de Ajustes, por
  teléfono, solo con los tres tipos que existen.
- ``POST /account/deletion-request``: pedir que se borre la cuenta. No borra
  nada; deja constancia y avisa a Auphere, una vez al día como mucho.
"""

from __future__ import annotations

from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.config import get_settings
from nexus_api.db.models import AuditLog, ClientPhone
from tests.conftest import add_client_member, add_client_phone, make_client_access

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture
async def phones(db_session, console_world) -> dict[str, Any]:
    w = console_world["a"]
    await make_client_access(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    member = await add_client_member(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"]
    )
    one = await add_client_phone(db_session, membership_id=member["membership_id"])
    two = await add_client_phone(
        db_session, membership_id=member["membership_id"], platform="android"
    )
    return {"member": member, "one": one, "two": two}


async def _row(db_session, phone_id) -> ClientPhone:
    db_session.expire_all()
    row = await db_session.get(ClientPhone, phone_id)
    assert row is not None
    return row


async def test_the_phone_registers_its_destination(client, db_session, phones) -> None:
    resp = await client.put(
        "/console/lite/phones/current/push",
        headers=phones["one"]["headers"](),
        json={"provider": "apns", "token": "a" * 64, "apns_environment": "sandbox"},
    )
    assert resp.status_code == 204, resp.text
    row = await _row(db_session, phones["one"]["phone_id"])
    assert (row.push_provider, row.push_token, row.apns_environment) == (
        "apns",
        "a" * 64,
        "sandbox",
    )
    assert row.push_token_updated_at is not None


async def test_a_destination_has_one_owner(client, db_session, phones) -> None:
    for key in ("one", "two"):
        resp = await client.put(
            "/console/lite/phones/current/push",
            headers=phones[key]["headers"](),
            json={"provider": "fcm", "token": "mismo-destino-123"},
        )
        assert resp.status_code == 204
    one_token = (await _row(db_session, phones["one"]["phone_id"])).push_token
    two = await _row(db_session, phones["two"]["phone_id"])
    assert one_token is None
    assert two.push_token == "mismo-destino-123"
    assert two.apns_environment is None


async def test_notices_start_with_the_three_kinds_and_can_be_switched(client, phones) -> None:
    headers = phones["one"]["headers"]()
    start = await client.get("/console/lite/phones/current/notices", headers=headers)
    assert start.json() == {"kinds": ["inbox.waiting", "inbox.message_for_you", "client.balance"]}

    resp = await client.put(
        "/console/lite/phones/current/notices",
        headers=headers,
        json={"kinds": ["client.balance", "inbox.waiting"]},
    )
    assert resp.status_code == 200
    assert resp.json() == {"kinds": ["inbox.waiting", "client.balance"]}

    other = await client.get(
        "/console/lite/phones/current/notices", headers=phones["two"]["headers"]()
    )
    assert len(other.json()["kinds"]) == 3


async def test_an_unknown_kind_is_rejected(client, phones) -> None:
    resp = await client.put(
        "/console/lite/phones/current/notices",
        headers=phones["one"]["headers"](),
        json={"kinds": ["inbox.waiting", "reservas.nueva"]},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == {"code": "unknown_kind", "kinds": ["reservas.nueva"]}


async def test_asking_to_delete_the_account_tells_auphere_once_a_day(
    client, db_session, phones, monkeypatch
) -> None:
    sent: list[dict[str, Any]] = []

    async def _send(**kw: Any) -> bool:
        sent.append(kw)
        return True

    monkeypatch.setattr("nexus_api.services.account_deletion.send_email", _send)
    monkeypatch.setattr(get_settings(), "security_contact_email", "seguridad@auphere.test")

    first = await client.post(
        "/console/lite/account/deletion-request", headers=phones["one"]["headers"]()
    )
    again = await client.post(
        "/console/lite/account/deletion-request", headers=phones["member"]["headers"]()
    )

    assert first.status_code == again.status_code == 202
    assert len(sent) == 1
    assert sent[0]["to"] == "seguridad@auphere.test"
    rows = await db_session.scalar(
        sa.select(sa.func.count())
        .select_from(AuditLog)
        .where(AuditLog.action == "client_account.deletion_requested")
    )
    assert rows == 2
