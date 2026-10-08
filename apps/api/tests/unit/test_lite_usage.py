"""Spec 030 — el Consumo de un solo cliente (Requisito 5).

``/console/lite/usage/*`` sale de las MISMAS funciones que el Consumo del
partner, con el cliente de quien entra fijo y sin lo que es del partner
entero. Lo que fija este archivo:

- gasto por día, gasto del mes y proyección coinciden con
  ``/console/usage/spend?client=<el suyo>`` del partner (CE-003);
- el resumen dice saldo, días, gasto, proyección, conversaciones del mes y
  gasto medio por conversación — sin inventar ninguno;
- el detalle técnico y su CSV solo traen filas del cliente, y solo de su
  tráfico (el Playground es la prueba del partner, no consumo del cliente);
- ninguna respuesta lleva nuestro coste ni el saldo del partner.
"""

from __future__ import annotations

import csv
import io
import uuid

import pytest
import sqlalchemy as sa

from tests.conftest import add_client_member, make_client_access, spend_from_wallet

pytestmark = pytest.mark.asyncio

BASE = "/console/lite/usage"


async def _seed_usage(db_session, tenant_id: uuid.UUID, rows: list[tuple[str, str, float]]) -> None:
    for meter, source, qty in rows:
        await db_session.execute(
            sa.text(
                "INSERT INTO usage_records (tenant_id, occurred_at, meter, quantity, cost_usd, "
                "billable_qty, idempotency_key, source) "
                "VALUES (:t, now(), :m, :q, 0.42, :q, :k, :s)"
            ),
            {"t": str(tenant_id), "m": meter, "q": qty, "k": f"k:{uuid.uuid4()}", "s": source},
        )
    await db_session.commit()


async def _fund(db_session, partner_id: uuid.UUID, credits: int) -> None:
    await db_session.execute(
        sa.text("UPDATE partner_wallets SET purchased_remaining = :c WHERE partner_id = :p"),
        {"c": credits, "p": partner_id},
    )
    await db_session.commit()


async def _member(db_session, w, modules=("panel", "usage")):
    await make_client_access(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"], modules=modules
    )
    return await add_client_member(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])


async def test_spend_matches_the_partners_view_of_this_client(
    client, db_session, console_world
) -> None:
    w = console_world["a"]
    await _fund(db_session, w["partner_id"], 3_000_000)
    await spend_from_wallet(
        partner_id=w["partner_id"], qty=250_001, lane="channel", tenant_id=w["tenant_id"]
    )
    # Gasto del partner fuera del cliente: no puede aparecer.
    await spend_from_wallet(partner_id=w["partner_id"], qty=90_000, lane="companion")
    member = await _member(db_session, w)

    lite = await client.get(f"{BASE}/spend?days=30", headers=member["headers"]())
    assert lite.status_code == 200, lite.text
    partner = (
        await client.get(f"/console/usage/spend?days=30&client={w['ref']}", headers=w["headers"]())
    ).json()
    body = lite.json()
    assert body["series_cents"] == partner["series_cents"]
    assert body["month_cents"] == partner["month_cents"]
    assert body["projected_cents"] == partner["projected_cents"]
    assert body["days"] == partner["days"]
    assert "by_client" not in body and "month_by_client" not in body


async def test_summary_says_everything_without_inventing(client, db_session, console_world) -> None:
    w = console_world["a"]
    member = await _member(db_session, w)
    body = (await client.get(f"{BASE}/summary", headers=member["headers"]())).json()
    assert body["errors"] == []
    assert body["balance"]["assigned"] is True
    assert body["balance"]["days_left"] is None  # sin gasto, sin días
    assert body["month"]["spent_cents"] == 0
    assert body["month"]["projection_cents"] is None  # nada que proyectar
    assert body["month"]["conversations"] == 0
    assert body["month"]["avg_per_conversation_cents"] is None
    assert body["by_agent"] is None


async def test_detail_and_csv_only_carry_this_clients_traffic(
    client, db_session, console_world
) -> None:
    w, b = console_world["a"], console_world["b"]
    await _seed_usage(
        db_session,
        w["tenant_id"],
        [("channel.message_sent", "channel", 12), ("llm.tokens_in", "qa", 900)],
    )
    await _seed_usage(db_session, b["tenant_id"], [("channel.message_sent", "channel", 99)])
    member = await _member(db_session, w)

    detail = (await client.get(f"{BASE}/detail?days=30", headers=member["headers"]())).json()
    meters = {(bk["meter"], bk["source"]) for bk in detail["buckets"]}
    assert meters == {("channel.message_sent", "channel")}
    assert detail["totals_by_meter"] == {"channel.message_sent": 12.0}
    assert "cost" not in str(detail).lower()

    resp = await client.get(f"{BASE}/export.csv?days=30&lang=es", headers=member["headers"]())
    assert resp.status_code == 200
    rows = list(csv.reader(io.StringIO(resp.content.decode("utf-8-sig"))))
    assert len(rows) == 2  # cabecera + la fila del cliente
    assert rows[1][0] == w["ref"]
    assert "99" not in rows[1]


async def test_no_partner_money_in_any_answer(client, db_session, console_world) -> None:
    w = console_world["a"]
    member = await _member(db_session, w)
    for path in ("/summary", "/spend?days=7", "/detail?days=7"):
        text = (await client.get(f"{BASE}{path}", headers=member["headers"]())).text
        for forbidden in ("available_cents", "purchased", "included", "reserve", "cost_usd"):
            assert forbidden not in text, (path, forbidden)


async def test_without_the_usage_module_it_is_403(client, db_session, console_world) -> None:
    w = console_world["a"]
    member = await _member(db_session, w, modules=("panel",))
    assert (await client.get(f"{BASE}/summary", headers=member["headers"]())).status_code == 403
