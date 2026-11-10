"""INC-70: el script de recálculo, sobre filas sintéticas de la base de tests.

Contra la tabla de verdad, porque ``usage_records`` está particionada y con RLS
forzada, y cualquiera de las dos puede dejar un UPDATE en cero filas sin error. Tres
cosas cuestan dinero si se rompen: sin ``--apply`` no se escribe, repetirlo no vuelve
a descontar, y la partida no sube nunca.
"""

from __future__ import annotations

import importlib.util
import sys
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import PartnerBuildBudget, UsageRecord
from nexus_api.services.wallet import build_budget

from ._wallet_world import UNIT, MoneyWorld, money_world

pytestmark = [pytest.mark.integration]

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "reprice_cached_input_inc70.py"
SOL = "openai/gpt-5.6-sol"
#: «Construcción y pruebas» agotada: lo que el fallo le hizo a la partida en staging.
CAP = 50 * UNIT


def _script() -> Any:
    spec = importlib.util.spec_from_file_location("reprice_inc70", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # ``dataclass`` busca el módulo aquí para resolver las anotaciones.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _call(
    tenant_id: uuid.UUID,
    *,
    input_cost: str,
    source: str = "tests",
    line: str = "build",
    prompt: int = 1000,
    cached: int = 900,
    at: datetime | None = None,
) -> tuple[str, list[UsageRecord]]:
    turn = f"job:{uuid.uuid4().hex}:1"
    at = at or datetime.now(UTC) - timedelta(minutes=1)

    def row(meter: str, quantity: int, cost: str, moment: datetime) -> UsageRecord:
        return UsageRecord(
            tenant_id=tenant_id,
            occurred_at=moment,
            meter=meter,
            quantity=Decimal(quantity),
            billable_qty=Decimal(quantity),
            cost_usd=Decimal(cost),
            model=SOL,
            idempotency_key=f"{turn}:{meter}",
            source=source,
            line=line,
        )

    rows = [row("llm.input_tokens", prompt, input_cost, at)]
    if cached:
        rows.append(row("llm.cache_read", cached, "0.00036", at + timedelta(milliseconds=1)))
    return turn, rows


async def _seed(db_session: Any) -> tuple[MoneyWorld, dict[str, str]]:
    world = await money_world(db_session, pool=30 * UNIT, roles=())
    calls = {
        "inflated": _call(world.us.tenant_id, input_cost="0.00400000"),
        "no_cache": _call(world.us.tenant_id, input_cost="0.00800000", prompt=2000, cached=0),
        "right": _call(world.us.tenant_id, input_cost="0.00040000"),
        "other_rate": _call(world.us.tenant_id, input_cost="0.00200000"),
        "channel": _call(
            world.es.tenant_id, input_cost="0.00400000", source="channel", line="conversations"
        ),
    }
    async with tenant_scoped_session(db_session, world.us.tenant_id):
        for name in ("inflated", "no_cache", "right", "other_rate"):
            db_session.add_all(calls[name][1])
    async with tenant_scoped_session(db_session, world.es.tenant_id):
        db_session.add_all(calls["channel"][1])
    await db_session.commit()
    async with db_session.begin():
        await apply_partner_to_session(db_session, world.partner_id)
        await build_budget.record(db_session, world.partner_id, CAP)
    await db_session.commit()
    return world, {name: call[0] for name, call in calls.items()}


async def _costs(tenant_id: uuid.UUID, turn: str) -> dict[str, Decimal]:
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        rows = (
            await session.execute(
                sa.text(
                    "SELECT meter, cost_usd FROM usage_records "
                    "WHERE idempotency_key LIKE :turn || ':%'"
                ),
                {"turn": turn},
            )
        ).all()
    return {str(meter): cost for meter, cost in rows}


async def _budget(partner_id: uuid.UUID) -> PartnerBuildBudget:
    async with get_sessionmaker()() as session, session.begin():
        await apply_partner_to_session(session, partner_id)
        row = (
            await session.scalars(
                sa.select(PartnerBuildBudget).where(PartnerBuildBudget.partner_id == partner_id)
            )
        ).one()
        session.expunge(row)
        return row


async def test_by_default_it_reads_and_writes_nothing(db_session: Any, capsys: Any) -> None:
    world, turns = await _seed(db_session)
    script = _script()

    report = await script.run(partner=world.partner_id)

    counts: dict[str, int] = {}
    for tenant in report.tenants:
        for verdict, count in tenant.counts.items():
            counts[verdict] = counts.get(verdict, 0) + count
    assert counts == {script.INFLATED: 2, script.RIGHT: 1, script.UNKNOWN_RATE: 1}
    # Las dos infladas: 0,0036 de más cada una.
    assert sum(t.excess for t in report.tenants) == Decimal("0.00720000")

    costs = await _costs(world.us.tenant_id, turns["inflated"])
    assert costs["llm.input_tokens"] == Decimal("0.00400000")
    budget = await _budget(world.partner_id)
    assert budget.spent_micros == CAP
    assert budget.exhausted_at is not None
    # 0,01188 medidos x 2,2 en cien milésimas.
    assert [(c.new_spent, c.unblocks, c.written) for c in report.budgets] == [(2613, True, None)]

    script.print_report(report, apply=False)
    printed = capsys.readouterr().out
    assert "Solo lectura" in printed
    assert "se desbloquea" in printed


async def test_applying_corrects_only_the_inflated_rows_and_the_budget(db_session: Any) -> None:
    world, turns = await _seed(db_session)

    report = await _script().run(apply=True, partner=world.partner_id)

    inflated = await _costs(world.us.tenant_id, turns["inflated"])
    assert inflated == {
        "llm.input_tokens": Decimal("0.00040000"),
        "llm.cache_read": Decimal("0.00036000"),
    }
    us = world.us.tenant_id
    assert (await _costs(us, turns["no_cache"]))["llm.input_tokens"] == Decimal("0.00800000")
    assert (await _costs(us, turns["right"]))["llm.input_tokens"] == Decimal("0.00040000")
    assert (await _costs(us, turns["other_rate"]))["llm.input_tokens"] == Decimal("0.00200000")
    channel = await _costs(world.es.tenant_id, turns["channel"])
    assert channel["llm.input_tokens"] == Decimal("0.00040000")

    budget = await _budget(world.partner_id)
    assert budget.spent_micros == 2613
    assert budget.exhausted_at is None
    assert budget.warned_at is None
    assert [c.written for c in report.budgets] == [True]
    # Lo que no toca, solo se informa: el exceso que sigue en Redis.
    es = next(t for t in report.tenants if t.tenant_id == world.es.tenant_id)
    assert list(es.channel_excess_by_month.values()) == [Decimal("0.00360000")]


async def test_running_it_twice_changes_nothing_more(db_session: Any) -> None:
    world, turns = await _seed(db_session)
    script = _script()
    await script.run(apply=True, partner=world.partner_id)

    again = await script.run(apply=True, partner=world.partner_id)

    assert sum(t.updated for t in again.tenants) == 0
    assert sum(t.excess for t in again.tenants) == Decimal(0)
    assert again.budgets == []
    costs = await _costs(world.us.tenant_id, turns["inflated"])
    assert costs["llm.input_tokens"] == Decimal("0.00040000")
    assert (await _budget(world.partner_id)).spent_micros == 2613


async def test_an_old_rate_given_by_hand_is_corrected_too(db_session: Any) -> None:
    world, turns = await _seed(db_session)
    # 0,002 por 1000 tokens: se valoró a 2 USD el millón, no a 4.
    await _script().run(apply=True, partner=world.partner_id, also_rates={SOL: [Decimal("2")]})
    costs = await _costs(world.us.tenant_id, turns["other_rate"])
    assert costs["llm.input_tokens"] == Decimal("0.00020000")


async def test_the_budget_never_goes_up(db_session: Any) -> None:
    """Medido por encima de lo sumado: el mes del despliegue, antes de la partida."""
    world, _turns = await _seed(db_session)
    async with db_session.begin():
        await apply_partner_to_session(db_session, world.partner_id)
        await db_session.execute(sa.update(PartnerBuildBudget).values(spent_micros=100))
    await db_session.commit()

    report = await _script().run(apply=True, partner=world.partner_id)

    assert report.budgets == []
    assert (await _budget(world.partner_id)).spent_micros == 100


async def test_another_currency_is_listed_and_left_alone(db_session: Any) -> None:
    world, _turns = await _seed(db_session)
    async with db_session.begin():
        await apply_partner_to_session(db_session, world.partner_id)
        await db_session.execute(
            sa.text("UPDATE partner_wallets SET currency = 'EUR' WHERE partner_id = :p"),
            {"p": str(world.partner_id)},
        )
    await db_session.commit()

    report = await _script().run(apply=True, partner=world.partner_id)

    assert report.budgets == []
    assert [c.currency for c in report.skipped_budgets] == ["EUR"]
    assert (await _budget(world.partner_id)).spent_micros == CAP


async def test_applying_needs_the_host_of_the_database(
    db_session: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Escribir exige nombrar la base, antes de tocar nada."""
    world, _turns = await _seed(db_session)
    script = _script()
    monkeypatch.setattr(sys, "argv", ["reprice", "--apply", "--partner", str(world.partner_id)])

    with pytest.raises(SystemExit):
        await script.main()

    assert (await _budget(world.partner_id)).spent_micros == CAP


def test_a_retried_job_is_two_calls_not_one() -> None:
    """Mismo ``turn_id`` y ``call_seq``, otro ``occurred_at``: la caché del segundo
    intento no puede descontar la entrada del primero."""
    script = _script()
    t0 = datetime(2026, 11, 2, 10, tzinfo=UTC)
    key = "job:1:1"

    def row(meter: str, at: datetime) -> dict[str, Any]:
        return {"meter": meter, "occurred_at": at, "idempotency_key": f"{key}:{meter}"}

    later = t0 + timedelta(minutes=5)
    calls = list(
        script.split_calls(
            [
                row("llm.input_tokens", t0),
                row("llm.input_tokens", later),
                row("llm.cache_read", later + timedelta(milliseconds=1)),
            ]
        )
    )
    assert [sorted(c) for c in calls] == [
        ["llm.input_tokens"],
        ["llm.cache_read", "llm.input_tokens"],
    ]
