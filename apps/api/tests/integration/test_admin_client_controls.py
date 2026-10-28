"""Spec 047, T172 — las palancas de operador por cliente y las conciliaciones
(requisitos 54.6 y 54.9).

La restricción soberana la fija Auphere con su motivo y queda en la auditoría; el
partner la ve como insignia y no tiene ruta para cambiarla. Las conciliaciones
enseñan las diferencias del libro de las bolsas y las de los mensajes con Meta.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import AuditLog, Channel, ClientWallet, MetaReconciliationRun
from nexus_api.main import app
from tests.integration.clients._client_world import add_agent
from tests.integration.wallet._wallet_world import UNIT, as_client, money, money_world

pytestmark = [pytest.mark.integration]


async def _operator(db_session: Any, admin_headers: dict[str, str]) -> dict[str, str]:
    from nexus_api.services import operator_identity

    account = await operator_identity.create_account(
        db_session, email=f"op-{uuid.uuid4().hex[:6]}@auphere.test", password="x" * 16, role="admin"
    )
    await db_session.commit()
    return {**admin_headers, "X-Operator-Id": str(account.id)}


async def test_auphere_sets_the_sovereign_restriction_and_the_partner_only_sees_it(
    client: Any, db_session: Any, admin_headers: dict[str, str]
) -> None:
    world = await money_world(db_session, roles=())
    headers = await _operator(db_session, admin_headers)
    url = f"/admin/clients/{world.es.tenant_id}/sovereign"
    assert (await client.get(url, headers=headers)).json()["enabled"] is False
    put = await client.put(
        url, json={"enabled": True, "reason": "Contrato con datos en la UE"}, headers=headers
    )
    assert put.status_code == 200, put.text
    assert (await client.get(url, headers=headers)).json()["enabled"] is True
    async with tenant_scoped_session(db_session, world.es.tenant_id):
        row = await db_session.scalar(
            sa.select(AuditLog).where(AuditLog.action == "client.sovereign_set")
        )
        assert row is not None and row.after_json is not None
        assert row.after_json["reason"] == "Contrato con datos en la UE"
    await db_session.commit()

    detail = await client.get(f"/console/clients/{world.es.ref}", headers=world.headers())
    assert detail.status_code == 200, detail.text
    assert detail.json()["sovereign"] is True, "la insignia del cliente"
    assert detail.json()["wallet_currency"] == "EUR"
    paths = {getattr(r, "path", "") for r in app.routes}
    assert not [p for p in paths if p.startswith("/console") and "sovereign" in p]


async def test_reconciliations_show_ledger_and_meta_differences(
    client: Any, db_session: Any, admin_headers: dict[str, str]
) -> None:
    world = await money_world(db_session, roles=())
    headers = await _operator(db_session, admin_headers)
    await client.post(
        f"/console/clients/{world.us.ref}/bag/assign",
        json={"amount": money(UNIT, "USD")},
        headers=world.headers(),
    )
    async with db_session.begin():
        await apply_partner_to_session(db_session, world.partner_id)
        await as_client(db_session, world.us.tenant_id)
        await db_session.execute(
            sa.update(ClientWallet)
            .where(ClientWallet.tenant_id == world.us.tenant_id)
            .values(balance_micros=ClientWallet.balance_micros + 7)
        )
    agent = await add_agent(db_session, world.us.tenant_id, "Recepción")
    async with tenant_scoped_session(db_session, world.us.tenant_id):
        channel = await db_session.get(Channel, agent["channel_id"])
        assert channel is not None
        db_session.add(
            MetaReconciliationRun(
                tenant_id=world.us.tenant_id,
                channel_id=channel.id,
                date=datetime.now(UTC).date(),
                meta_count=12,
                stored_count=10,
                diff=2,
            )
        )
    await db_session.commit()
    resp = await client.get("/admin/reconciliations?days=7", headers=headers)
    assert resp.status_code == 200, resp.text
    out = resp.json()
    mine = [d for d in out["ledger"] if d["partner_id"] == str(world.partner_id)]
    assert mine and mine[0]["kind"] == "bag" and mine[0]["balance"] == mine[0]["entries"] + 7
    assert mine[0]["currency"] == "USD" and mine[0]["tenant_name"] == "Cliente US"
    budget = (
        await client.get(f"/admin/partners/{world.partner_id}/build-budget", headers=headers)
    ).json()
    assert budget["currency"] == "USD" and budget["cap"]["amount_micros"] == 5_000_000
    meta = [m for m in out["meta"] if m["tenant_id"] == str(world.us.tenant_id)]
    assert meta == [
        {
            "tenant_id": str(world.us.tenant_id),
            "tenant_name": "Cliente US",
            "channel_id": str(agent["channel_id"]),
            "identifier": meta[0]["identifier"],
            "date": datetime.now(UTC).date().isoformat(),
            "meta_count": 12,
            "stored_count": 10,
            "diff": 2,
        }
    ]
