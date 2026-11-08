"""Bug ``gasto-del-mes-a-cero-con-bolsas`` (QA H-20; spec 047, requisito 46.7).

Con bolsas el turno se cobra **solo** de la bolsa del cliente
(``wallet/turns.charge_turn``): el libro de la cuenta no lo ve. El gasto del mes
del cliente —su total y el de cada agente— tiene que salir de la bolsa, en su
moneda, y ser la misma cifra en la consola lite (Panel, Consumo y su gráfica) y
en el Panel del cliente de la consola del partner.

Y la bolsa que aún no se ha tocado este mes no enseña lo del mes pasado: su
``month_spent_micros`` solo vuelve a cero con el primer movimiento del mes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.billing.pricing import credits_to_cents
from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.db.models import ClientWallet
from nexus_api.services.wallet.turns import charge_turn
from tests.conftest import add_client_member, make_client_access
from tests.integration.clients._client_world import add_agent

from ._wallet_world import UNIT, MoneyWorld, as_client, bag_of, money, money_world

pytestmark = [pytest.mark.integration]


async def _world(client: Any, db_session: Any) -> tuple[MoneyWorld, dict[str, Any]]:
    """El cliente de España (bolsa en EUR) con 20 EUR, dos agentes y su persona
    en la consola lite con Panel y Consumo."""
    world = await money_world(db_session, roles=())
    resp = await client.post(
        f"/console/clients/{world.es.ref}/bag/assign",
        json={"amount": money(20 * UNIT, "EUR")},
        headers=world.headers(),
    )
    assert resp.status_code == 200, resp.text
    now = datetime.now(UTC)
    citas = await add_agent(
        db_session, world.es.tenant_id, "Citas", created_at=now - timedelta(hours=3)
    )
    ventas = await add_agent(
        db_session, world.es.tenant_id, "Ventas", created_at=now - timedelta(hours=2)
    )
    await db_session.commit()
    await make_client_access(
        db_session,
        partner_id=world.partner_id,
        tenant_id=world.es.tenant_id,
        modules=("panel", "usage"),
    )
    member = await add_client_member(
        db_session, partner_id=world.partner_id, tenant_id=world.es.tenant_id
    )
    return world, {"citas": citas["agent_id"], "ventas": ventas["agent_id"], "member": member}


async def _turn(world: MoneyWorld, agent_id: uuid.UUID | None, amount_usd: int) -> None:
    await charge_turn(
        partner_id=world.partner_id,
        tenant_id=world.es.tenant_id,
        agent_id=agent_id,
        amount_usd=amount_usd,
        usage_ref=f"channel:{uuid.uuid4().hex}",
    )


async def _get(client: Any, path: str, headers: dict[str, str]) -> dict[str, Any]:
    resp = await client.get(path, headers=headers)
    assert resp.status_code == 200, resp.text
    out: dict[str, Any] = resp.json()
    return out


async def test_the_client_reads_its_month_spend_from_the_bag_like_the_partner(
    client: Any, db_session: Any
) -> None:
    world, w = await _world(client, db_session)
    # Tres turnos de Citas (uno sin agente, de antes de los agentes: del
    # principal), uno de Ventas. En USD, la unidad del medidor; la bolsa cobra en EUR.
    for agent, amount in ((w["citas"], 54_000), (w["citas"], 21_600), (None, 5_400)):
        await _turn(world, agent, amount)
    await _turn(world, w["ventas"], 10_800)

    bag = await bag_of(db_session, world, world.es.tenant_id)
    total_cents = credits_to_cents(bag.month_spent_micros, nearest=True)
    assert total_cents > 0, "los turnos han bajado la bolsa"

    # La consola del partner: la bolsa, el mes y el reparto por agente cuadran.
    panel = await _get(client, f"/console/clients/{world.es.ref}/panel", world.headers())
    assert panel["bag"]["spent"] == {"amount_micros": total_cents * 1000, "currency": "EUR"}
    assert panel["month"]["spent"] == panel["bag"]["spent"]
    partner_by_agent = {
        x["agent_id"]: x["spent"]["amount_micros"] // 1000 for x in panel["spend_by_agent"]
    }
    assert {x["spent"]["currency"] for x in panel["spend_by_agent"]} == {"EUR"}
    assert sum(partner_by_agent.values()) == total_cents
    assert partner_by_agent[str(w["ventas"])] > 0
    assert partner_by_agent[str(w["citas"])] > partner_by_agent[str(w["ventas"])]

    # Un token de consola sirve para una sola petición: uno nuevo en cada una.
    headers = w["member"]["headers"]
    home = await _get(client, "/console/lite/home", headers())
    assert home["spend_month"]["total_cents"] == total_cents
    assert home["spend_month"]["currency"] == "EUR"
    assert home["balance"]["currency"] == "EUR"
    home_by_agent = {x["agent_id"]: x["cents"] for x in home["spend_month"]["by_agent"]}
    assert home_by_agent == partner_by_agent

    summary = await _get(client, "/console/lite/usage/summary", headers())
    assert summary["month"]["spent_cents"] == total_cents
    assert summary["month"]["currency"] == "EUR"
    assert summary["month"]["projection_cents"] >= total_cents
    usage_by_agent = {x["agent_id"]: x["spent_cents"] for x in summary["by_agent"]}
    assert usage_by_agent == partner_by_agent

    chart = await _get(client, "/console/lite/usage/spend?days=30", headers())
    assert chart["currency"] == "EUR"
    assert chart["month_cents"] == total_cents
    assert sum(chart["series_cents"]) == total_cents
    one = await _get(client, f"/console/lite/usage/spend?days=30&agent={w['ventas']}", headers())
    assert one["currency"] == "EUR"
    assert one["month_cents"] == partner_by_agent[str(w["ventas"])]
    assert sum(one["series_cents"]) == partner_by_agent[str(w["ventas"])]


async def test_a_bag_untouched_this_month_has_spent_nothing_yet(
    client: Any, db_session: Any
) -> None:
    """``_roll`` solo corre al tocar la bolsa: hasta el primer cobro del mes,
    ``month_spent_micros`` es el del mes pasado."""
    world, w = await _world(client, db_session)
    await _turn(world, w["citas"], 54_000)
    last_month = (datetime.now(UTC).date().replace(day=1) - timedelta(days=1)).replace(day=1)
    async with db_session.begin():
        await apply_partner_to_session(db_session, world.partner_id)
        await as_client(db_session, world.es.tenant_id)
        await db_session.execute(
            sa.update(ClientWallet)
            .where(ClientWallet.tenant_id == world.es.tenant_id)
            .values(month=last_month)
        )
        # Y los cobros, del mes pasado también.
        await db_session.execute(
            sa.text(
                "UPDATE client_wallet_entries SET created_at = created_at - interval '40 days' "
                "WHERE tenant_id = :t"
            ),
            {"t": world.es.tenant_id},
        )

    panel = await _get(client, f"/console/clients/{world.es.ref}/panel", world.headers())
    assert panel["bag"]["spent"] == {"amount_micros": 0, "currency": "EUR"}
    assert panel["month"]["spent"] == panel["bag"]["spent"]
    home = await _get(client, "/console/lite/home", w["member"]["headers"]())
    assert home["spend_month"]["total_cents"] == 0
    summary = await _get(client, "/console/lite/usage/summary", w["member"]["headers"]())
    assert summary["month"]["spent_cents"] == 0
