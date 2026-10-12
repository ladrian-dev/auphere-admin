"""Bug ``doble-cobro-del-tope`` — un turno de canal baja el tope del cliente UNA
vez, por lo que de verdad se cobró, y el gasto que se enseña es ese.

Contra la base real, por el camino real del medidor
(``consumer._debit_channel_wallet``). Lo único simulado es la aritmética del
peso del turno (``_turn_quota``), para que el turno pese una cifra conocida.

**Por qué este fichero existe.** ``test_allocation_debit_wiring.py`` fijaba
con dobles que el consumidor llamara a ``debit_wallet`` **y** a
``debit_allocation``. Cada doble era independiente, así que nadie vio que el
primero ya baja el tope: desde el 2026-09-02 cada turno lo bajaba dos veces,
el cliente se quedaba mudo a mitad de su tope y el gasto salía doble.
Diagnóstico: ``.specify/bugs/doble-cobro-del-tope/assessment.md``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from nexus_api.db.models import PartnerAllocation, PartnerWallet, UsageLedger

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

TURN_QTY = 2_000
#: What the consumer receives for one channel turn; the weight is simulated.
ROWS: list[dict[str, Any]] = [{"meter": "llm.input_tokens", "source": "channel", "agent_id": None}]


@pytest.fixture
def consumer(monkeypatch: pytest.MonkeyPatch):
    from nexus_worker.metering import consumer as module

    turn = f"turn-{uuid.uuid4().hex[:8]}"

    async def _no_catalog() -> list[Any]:
        return []

    monkeypatch.setattr(module, "_turn_quota", lambda rows, weights: {turn: TURN_QTY})
    monkeypatch.setattr(module, "get_catalog", _no_catalog)
    monkeypatch.setattr(module, "lane_weights_from", lambda catalog: {})
    module._partner_of.clear()
    module.TURN = turn  # type: ignore[attr-defined]
    yield module
    module._partner_of.clear()


async def _setup(
    db_session, w: dict[str, Any], *, purchased: int, included: int = 0, cap: int
) -> None:
    # The world already gives the partner a wallet: set it to known figures.
    values = {
        "included_remaining": included,
        "included_expires_at": datetime.now(UTC) + timedelta(days=20) if included else None,
        "purchased_remaining": purchased,
    }
    await db_session.execute(
        pg_insert(PartnerWallet)
        .values(partner_id=w["partner_id"], **values)
        .on_conflict_do_update(index_elements=[PartnerWallet.partner_id], set_=values)
    )
    await db_session.execute(
        sa.update(PartnerAllocation)
        .where(PartnerAllocation.tenant_id == w["tenant_id"])
        .values(cap=cap, remaining=cap)
    )
    await db_session.commit()


async def _remaining(db_session, w: dict[str, Any]) -> int:
    return int(
        await db_session.scalar(
            sa.select(PartnerAllocation.remaining).where(
                PartnerAllocation.tenant_id == w["tenant_id"]
            )
        )
    )


async def _purchased(db_session, w: dict[str, Any]) -> int:
    return int(
        await db_session.scalar(
            sa.select(PartnerWallet.purchased_remaining).where(
                PartnerWallet.partner_id == w["partner_id"]
            )
        )
    )


async def _ledger(db_session, w: dict[str, Any]) -> dict[str, int]:
    rows = await db_session.execute(
        sa.select(UsageLedger.idempotency_key, UsageLedger.qty).where(
            UsageLedger.tenant_id == w["tenant_id"]
        )
    )
    return {key: int(qty) for key, qty in rows.all()}


async def test_a_channel_turn_lowers_the_client_cap_once(
    db_session, console_world, consumer
) -> None:
    w = console_world["a"]
    await _setup(db_session, w, purchased=100_000, cap=10_000)

    await consumer._debit_channel_wallet(w["tenant_id"], ROWS)

    assert await _purchased(db_session, w) == 100_000 - TURN_QTY
    # The bug: 10 000 - 2 * 2 000 = 6 000.
    assert await _remaining(db_session, w) == 10_000 - TURN_QTY
    # One entry for what was charged; none that a report would count twice.
    assert await _ledger(db_session, w) == {f"channel:{consumer.TURN}:purchased": TURN_QTY}


async def test_nothing_charged_means_nothing_off_the_cap(
    db_session, console_world, consumer
) -> None:
    """With no purchased credits the channel cannot be charged (it never spends
    the included pool). Then the cap does not move and no spend is written —
    the bug wrote a phantom spend and lowered the cap anyway."""
    w = console_world["a"]
    await _setup(db_session, w, purchased=0, included=50_000, cap=10_000)

    await consumer._debit_channel_wallet(w["tenant_id"], ROWS)

    assert await _remaining(db_session, w) == 10_000
    assert await _ledger(db_session, w) == {}


async def test_half_the_cap_spent_still_answers(db_session, console_world, consumer) -> None:
    """The user-facing face of the bug: the agent went silent with half its
    cap spent, because the gate closes at ``remaining <= 0``."""
    from nexus_api.metering.wallet import allow_channel_turn

    w = console_world["a"]
    await _setup(db_session, w, purchased=100_000, cap=2 * TURN_QTY)

    await consumer._debit_channel_wallet(w["tenant_id"], ROWS)

    assert await _remaining(db_session, w) == TURN_QTY
    assert await allow_channel_turn(w["tenant_id"]) is True


async def test_old_allocation_entries_are_not_spend(db_session, console_world) -> None:
    """Entries the bug wrote (``…:allocation``) stay in the ledger as history,
    but no spend report counts them: the money spent is what was charged."""
    from nexus_api.metering.wallet import credit_burn, credit_burn_by_agent, credit_burn_by_day

    w = console_world["a"]
    key = f"channel:old-{uuid.uuid4().hex[:6]}"
    db_session.add_all(
        [
            UsageLedger(
                partner_id=w["partner_id"],
                tenant_id=w["tenant_id"],
                qty=TURN_QTY,
                bucket="purchased",
                idempotency_key=f"{key}:purchased",
            ),
            UsageLedger(
                partner_id=w["partner_id"],
                tenant_id=w["tenant_id"],
                qty=TURN_QTY,
                bucket="included",
                idempotency_key=f"{key}:allocation",
            ),
        ]
    )
    await db_session.commit()
    since = datetime.now(UTC) - timedelta(days=1)

    assert await credit_burn(w["partner_id"], [w["tenant_id"]], since) == {w["tenant_id"]: TURN_QTY}
    assert await credit_burn_by_agent(w["partner_id"], w["tenant_id"], since) == {None: TURN_QTY}
    daily = await credit_burn_by_day(
        w["partner_id"], [w["tenant_id"]], since, include_outside=False
    )
    assert sum(daily.values()) == TURN_QTY
