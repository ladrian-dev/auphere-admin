"""Spec 030 — la campana de la persona de un cliente (R15).

La tabla de avisos es del partner; con la spec 030 un aviso tiene también un
destinatario (``audience``). Lo que fija este archivo:

- la persona de un cliente ve solo avisos ``client`` de SU cliente;
- el partner deja de ver los avisos ``client`` (R15.3: la espera de una
  conversación del cliente con Bandeja no le llega a él);
- el estado de leído es por persona;
- ninguna de las dos campanas abre la otra.
"""

from __future__ import annotations

import pytest

from nexus_api.db.models import ConsoleNotification
from tests.conftest import add_client_member, make_client_access

pytestmark = pytest.mark.asyncio

BASE = "/console/lite/notifications"


async def _seed(db_session, console_world):
    a, b = console_world["a"], console_world["b"]
    await make_client_access(db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"])
    member = await add_client_member(
        db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"]
    )
    rows = [
        # Del cliente de la persona: lo ve ella, no el partner.
        ConsoleNotification(
            partner_id=a["partner_id"],
            external_client_ref=a["ref"],
            kind="inbox.waiting",
            severity="warning",
            payload={"contact": "Martín Ruiz"},
            audience="client",
        ),
        # De otro cliente del MISMO partner: no lo ve nadie de este cliente.
        ConsoleNotification(
            partner_id=a["partner_id"],
            external_client_ref="otro-cliente",
            kind="inbox.waiting",
            severity="warning",
            payload={},
            audience="client",
        ),
        # Del partner: lo ve el partner, nunca la persona del cliente.
        ConsoleNotification(
            partner_id=a["partner_id"],
            external_client_ref=a["ref"],
            kind="client.out_of_quota",
            severity="warning",
            payload={},
            audience="partner",
        ),
        ConsoleNotification(
            partner_id=a["partner_id"], kind="wallet.low", severity="warning", payload={}
        ),
        # De otro partner.
        ConsoleNotification(
            partner_id=b["partner_id"],
            external_client_ref=b["ref"],
            kind="inbox.waiting",
            payload={},
            audience="client",
        ),
    ]
    db_session.add_all(rows)
    await db_session.commit()
    return a, member


async def test_client_sees_only_its_client_notices(client, db_session, console_world) -> None:
    _a, member = await _seed(db_session, console_world)
    resp = await client.get(BASE, headers=member["headers"]())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [n["kind"] for n in body["items"]] == ["inbox.waiting"]
    assert body["unread"] == 1
    count = await client.get(f"{BASE}/unread-count", headers=member["headers"]())
    assert count.json() == {"unread": 1}


async def test_partner_no_longer_sees_client_notices(client, db_session, console_world) -> None:
    a, _member = await _seed(db_session, console_world)
    resp = await client.get("/console/notifications", headers=a["headers"]())
    kinds = sorted(n["kind"] for n in resp.json()["items"])
    assert kinds == ["client.out_of_quota", "wallet.low"]


async def test_read_state_is_per_person(client, db_session, console_world) -> None:
    a, member = await _seed(db_session, console_world)
    other = await add_client_member(
        db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"]
    )
    marked = await client.post(f"{BASE}/read-all", headers=member["headers"]())
    assert marked.json() == {"marked": 1}
    assert (await client.get(f"{BASE}/unread-count", headers=member["headers"]())).json() == {
        "unread": 0
    }
    assert (await client.get(f"{BASE}/unread-count", headers=other["headers"]())).json() == {
        "unread": 1
    }


async def test_marking_a_foreign_notice_is_404(client, db_session, console_world) -> None:
    a, member = await _seed(db_session, console_world)
    partner_row = (await client.get("/console/notifications", headers=a["headers"]())).json()[
        "items"
    ][0]
    resp = await client.post(f"{BASE}/{partner_row['id']}/read", headers=member["headers"]())
    assert resp.status_code == 404


async def test_the_two_bells_do_not_open_each_other(client, db_session, console_world) -> None:
    a, member = await _seed(db_session, console_world)
    assert (await client.get(BASE, headers=a["headers"]())).status_code == 403
    assert (
        await client.get("/console/notifications", headers=member["headers"]())
    ).status_code == 403
