"""Requisito 68: una pasada a cargo de la bolsa cobra la bolsa, y nada más.

Y el bug ``un-lote-cobra-por-su-primera-fila``: el consumidor junta en un lote las
filas de un cliente, y miraba el origen y el agente de la primera. Un turno de canal
leído junto a una prueba se quedaba sin cobrar, o la prueba se cobraba como turno.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.db.models import ClientWalletEntry, PartnerBuildBudget
from nexus_api.services.wallet.bags import as_client, month_of

from ._wallet_world import UNIT, MoneyWorld, bag_of, money, money_world

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

MODEL = "openai/gpt-5.6-sol"


def _rows(source: str, turn: str, *, agent_id: uuid.UUID | None = None) -> list[dict[str, Any]]:
    """Las filas de una llamada al modelo de una pasada, como las deja el colector."""
    return [
        {
            "meter": meter,
            "quantity": quantity,
            "billable_qty": float(quantity),
            "model": MODEL,
            "source": source,
            "agent_id": agent_id,
            "idempotency_key": f"{turn}:1:{meter}",
        }
        for meter, quantity in (("llm.input_tokens", 1_000), ("llm.output_tokens", 100))
    ]


@pytest.fixture
async def world(client: Any, db_session: Any) -> MoneyWorld:
    world = await money_world(db_session, pool=30 * UNIT, roles=())
    resp = await client.post(
        f"/console/clients/{world.us.ref}/bag/assign",
        json={"amount": money(10 * UNIT, "USD")},
        headers=world.headers(),
    )
    assert resp.status_code == 200, resp.text
    return world


@pytest.fixture
def consumer() -> Any:
    from nexus_worker.metering import consumer as module

    module._partner_of.clear()
    yield module
    module._partner_of.clear()


async def _entries(db_session: Any, world: MoneyWorld) -> list[tuple[str, str | None, int]]:
    async with db_session.begin():
        await apply_partner_to_session(db_session, world.partner_id)
        await as_client(db_session, world.us.tenant_id)
        rows = await db_session.execute(
            sa.select(
                ClientWalletEntry.kind,
                ClientWalletEntry.usage_ref,
                ClientWalletEntry.amount_micros,
            ).where(
                ClientWalletEntry.tenant_id == world.us.tenant_id,
                ClientWalletEntry.kind.like("debit_%"),
            )
        )
        return [(str(k), r, int(a)) for k, r, a in rows.all()]


async def test_a_bag_pass_is_charged_to_the_bag_with_its_own_entry(
    db_session: Any, world: MoneyWorld, consumer: Any
) -> None:
    await consumer._debit_channel_wallet(world.us.tenant_id, _rows("tests_client", "job:a:b:1"))

    ((kind, ref, amount),) = await _entries(db_session, world)
    assert kind == "debit_tests"
    assert ref == "tests_client:job:a:b:1"
    assert amount < 0
    bag = await bag_of(db_session, world, world.us.tenant_id)
    assert bag.balance_micros == 10 * UNIT + amount


async def test_charging_a_bag_pass_twice_charges_it_once(
    db_session: Any, world: MoneyWorld, consumer: Any
) -> None:
    rows = _rows("tests_client", "job:a:b:1")
    await consumer._debit_channel_wallet(world.us.tenant_id, rows)
    await consumer._debit_channel_wallet(world.us.tenant_id, rows)
    assert len(await _entries(db_session, world)) == 1


async def test_a_bag_pass_does_not_count_against_the_agent_cap(
    db_session: Any, world: MoneyWorld, consumer: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus_api.services.wallet import alerts

    seen: list[Any] = []

    async def record(*_: Any, **kw: Any) -> list[Any]:
        seen.append(kw)
        return []

    monkeypatch.setattr(alerts, "record_agent_spend", record)
    await consumer._debit_channel_wallet(
        world.us.tenant_id, _rows("tests_client", "job:a:b:1", agent_id=uuid.uuid4())
    )
    assert seen == [], "el tope del agente es de lo que gasta atendiendo"


async def test_a_bag_pass_does_not_reach_the_build_budget(
    db_session: Any, world: MoneyWorld, consumer: Any
) -> None:
    rows = [
        {**row, "line": "client_tests", "cost_usd": "0.01"}
        for row in _rows("tests_client", "job:a:b:1")
    ]
    await consumer._record_build_line(world.us.tenant_id, rows)
    async with db_session.begin():
        await apply_partner_to_session(db_session, world.partner_id)
        row = await db_session.get(PartnerBuildBudget, (world.partner_id, month_of()))
    assert row is None or row.spent_micros == 0


async def test_a_batch_with_a_test_first_still_charges_the_channel_turn(
    db_session: Any, world: MoneyWorld, consumer: Any
) -> None:
    """Lo paga Auphere: la prueba no se cobra, y el turno de al lado, sí."""
    rows = [*_rows("tests", "job:a:b:1"), *_rows("channel", "turn-1")]
    await consumer._debit_channel_wallet(world.us.tenant_id, rows)

    assert [(k, r) for k, r, _a in await _entries(db_session, world)] == [
        ("debit_turn", "channel:turn-1")
    ]


async def test_a_batch_with_a_channel_turn_first_does_not_charge_the_test(
    db_session: Any, world: MoneyWorld, consumer: Any
) -> None:
    rows = [*_rows("channel", "turn-1"), *_rows("tests", "job:a:b:1")]
    await consumer._debit_channel_wallet(world.us.tenant_id, rows)

    assert [r for _k, r, _a in await _entries(db_session, world)] == ["channel:turn-1"]


async def test_each_turn_of_a_batch_keeps_its_own_agent(
    db_session: Any, world: MoneyWorld, consumer: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nexus_api.services.wallet import alerts

    async def nothing(*_: Any, **_kw: Any) -> list[Any]:
        return []

    # Estos agentes no existen: lo que se mira es a quién se apunta cada cobro.
    monkeypatch.setattr(alerts, "record_agent_spend", nothing)
    first, second = uuid.uuid4(), uuid.uuid4()
    rows = [
        *_rows("channel", "turn-1", agent_id=first),
        *_rows("channel", "turn-2", agent_id=second),
    ]
    await consumer._debit_channel_wallet(world.us.tenant_id, rows)

    async with db_session.begin():
        await apply_partner_to_session(db_session, world.partner_id)
        await as_client(db_session, world.us.tenant_id)
        found = await db_session.execute(
            sa.select(ClientWalletEntry.usage_ref, ClientWalletEntry.agent_id).where(
                ClientWalletEntry.kind == "debit_turn"
            )
        )
        by_ref = {r: a for r, a in found.all()}
    assert by_ref == {"channel:turn-1": first, "channel:turn-2": second}


async def test_consumo_shows_it_on_its_own_line_and_not_as_conversations(
    client: Any, world: MoneyWorld, consumer: Any
) -> None:
    await consumer._debit_channel_wallet(world.us.tenant_id, _rows("tests_client", "job:a:b:1"))

    resp = await client.get("/console/usage/summary", headers=world.headers())
    assert resp.status_code == 200, resp.text
    lines = {line["line"]: line for line in resp.json()["lines"]}
    assert lines["client_tests"]["payer"] == "client_bag"
    assert lines["client_tests"]["amount"]["amount_micros"] > 0
    assert lines["conversations"]["amount"]["amount_micros"] == 0


async def test_a_bag_pass_goes_through_the_real_ingestion(
    db_session: Any, world: MoneyWorld, consumer: Any
) -> None:
    """De la entrada del stream a la fila, con los CHECK de la 0220 y el cobro."""
    import json
    from datetime import UTC, datetime

    from nexus_api.core.tenant_context import tenant_scoped_session
    from nexus_api.db.models import UsageRecord

    turn = f"job:{uuid.uuid4().hex}:t:1"
    now = datetime.now(UTC).isoformat()
    fields = {
        "tenant_id": str(world.us.tenant_id),
        "source": "tests_client",
        "events": json.dumps(
            [
                {
                    "occurred_at": now,
                    "meter": meter,
                    "quantity": quantity,
                    "provider": "openai",
                    "model": MODEL,
                    "idempotency_key": f"{turn}:1:{meter}",
                    "task": "answer",
                }
                for meter, quantity in (("llm.input_tokens", 1_000), ("llm.output_tokens", 100))
            ]
        ),
    }
    tenant_id, rows = consumer.rows_from_entry(fields)
    assert {r["line"] for r in rows} == {"client_tests"}
    await consumer.persist_rows({tenant_id: rows})

    async with tenant_scoped_session(db_session, tenant_id):
        stored = (
            await db_session.execute(
                sa.select(UsageRecord.source, UsageRecord.line, UsageRecord.cost_usd).where(
                    UsageRecord.tenant_id == tenant_id
                )
            )
        ).all()
    assert {(s, line) for s, line, _c in stored} == {("tests_client", "client_tests")}
    assert all(c is not None for _s, _l, c in stored), "con su coste, del catálogo"
    assert [k for k, _r, _a in await _entries(db_session, world)] == ["debit_tests"]
    async with db_session.begin():
        await apply_partner_to_session(db_session, world.partner_id)
        budget = await db_session.get(PartnerBuildBudget, (world.partner_id, month_of()))
    assert budget is None or budget.spent_micros == 0, "no es de «Construcción y pruebas»"


async def test_a_bag_pass_without_a_catalog_is_retried_not_forgotten(
    world: MoneyWorld, consumer: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def empty() -> dict[str, Any]:
        return {}

    monkeypatch.setattr(consumer, "get_catalog", empty)
    with pytest.raises(RuntimeError, match="catalog"):
        await consumer._debit_channel_wallet(world.us.tenant_id, _rows("tests_client", "job:a:b:1"))
