"""Spec 047, T152 — el tope de cada agente y los avisos de la bolsa (requisitos
44.1 a 44.8, 27.4 y 27.5).

El tope es mensual (UTC) y va en la moneda de la bolsa: al 80 % avisa una vez al
mes; al 100 % pausa a ese agente («Pausado · tope del agente») y los demás siguen,
hasta el mes siguiente o hasta que se sube. Los avisos de la bolsa («Queda poco»,
«No llega a fin de mes», «Agotada») salen una vez y se rearman al subir el saldo.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import Agent, AgentMonthlySpend, ClientWallet, ClientWalletEntry
from nexus_api.services import channel_config
from nexus_api.services.wallet import alerts
from nexus_api.services.wallet.turns import charge_turn
from tests.integration.clients._client_world import add_agent

from ._wallet_world import UNIT, MoneyWorld, as_client, money, money_world

pytestmark = [pytest.mark.integration]


@pytest.fixture
def told(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Lo que se avisa (campana, correo y push salen de ``announce``)."""
    out: list[dict[str, Any]] = []

    async def _announce(**kw: Any) -> None:
        out.append(kw)

    monkeypatch.setattr(channel_config, "announce", _announce)
    return out


async def _funded(client: Any, db_session: Any, amount: int = 10 * UNIT) -> MoneyWorld:
    world = await money_world(db_session, roles=())
    resp = await client.post(
        f"/console/clients/{world.us.ref}/bag/assign",
        json={"amount": money(amount, "USD")},
        headers=world.headers(),
    )
    assert resp.status_code == 200, resp.text
    return world


async def _agent(db_session: Any, world: MoneyWorld, name: str) -> uuid.UUID:
    agent = await add_agent(db_session, world.us.tenant_id, name)
    await db_session.commit()
    agent_id = agent["agent_id"]
    assert agent_id is not None
    # ``add_agent`` deja la versión activa; publicar también marca el agente.
    async with tenant_scoped_session(db_session, world.us.tenant_id):
        await db_session.execute(
            sa.update(Agent).where(Agent.id == agent_id).values(lifecycle="published")
        )
    await db_session.commit()
    return agent_id


async def _lifecycle(db_session: Any, world: MoneyWorld, agent_id: uuid.UUID) -> tuple[str, Any]:
    async with tenant_scoped_session(db_session, world.us.tenant_id):
        agent = await db_session.get(Agent, agent_id, populate_existing=True)
        assert agent is not None
        out = (agent.lifecycle, agent.pause_reason)
    await db_session.commit()
    return out


async def _turn(world: MoneyWorld, agent_id: uuid.UUID, amount: int) -> None:
    await charge_turn(
        partner_id=world.partner_id,
        tenant_id=world.us.tenant_id,
        agent_id=agent_id,
        amount_usd=amount,
        usage_ref=f"channel:{uuid.uuid4().hex}",
    )


# ── el tope del agente ─────────────────────────────────────────────────────


async def test_the_cap_warns_at_80_once_and_pauses_only_that_agent_at_100(
    client: Any, db_session: Any, told: list[dict[str, Any]]
) -> None:
    world = await _funded(client, db_session)
    ventas = await _agent(db_session, world, "Ventas")
    citas = await _agent(db_session, world, "Citas")
    cap = await client.put(
        f"/console/clients/{world.us.ref}/agents/{ventas}/cap",
        json={"monthly_cap": money(UNIT, "USD")},
        headers=world.headers(),
    )
    assert cap.status_code == 200, cap.text

    await _turn(world, ventas, 85_000)
    await _turn(world, ventas, 5_000)
    warnings = [t for t in told if t["kind"] == "agent.cap.warning"]
    assert len(warnings) == 1, "al 80 %, un aviso al mes"
    assert warnings[0]["data"]["currency"] == "USD"
    assert await _lifecycle(db_session, world, ventas) == ("published", None)

    await _turn(world, ventas, 20_000)
    assert [t["kind"] for t in told].count("agent.cap.reached") == 1
    assert await _lifecycle(db_session, world, ventas) == ("paused", "agent_cap")
    assert await _lifecycle(db_session, world, citas) == ("published", None), "los demás siguen"

    async with tenant_scoped_session(db_session, world.us.tenant_id):
        row = await db_session.get(
            AgentMonthlySpend,
            (world.us.tenant_id, ventas, datetime.now(UTC).date().replace(day=1)),
        )
        assert row is not None and row.spent_micros == 110_000
    await db_session.commit()


async def test_raising_the_cap_resumes_the_agent_and_so_does_the_new_month(
    client: Any, db_session: Any, told: list[dict[str, Any]]
) -> None:
    from nexus_worker.streams.wallet_crons import _resume_capped

    world = await _funded(client, db_session)
    ventas = await _agent(db_session, world, "Ventas")
    url = f"/console/clients/{world.us.ref}/agents/{ventas}/cap"
    await client.put(url, json={"monthly_cap": money(UNIT, "USD")}, headers=world.headers())
    await _turn(world, ventas, 100_000)
    assert await _lifecycle(db_session, world, ventas) == ("paused", "agent_cap")

    raised = await client.put(
        url, json={"monthly_cap": money(2 * UNIT, "USD")}, headers=world.headers()
    )
    assert raised.status_code == 200 and raised.json()["lifecycle"] == "published"
    await _turn(world, ventas, 100_000)
    assert await _lifecycle(db_session, world, ventas) == ("paused", "agent_cap")

    next_month = (datetime.now(UTC).replace(day=28) + timedelta(days=4)).replace(day=1)
    await _resume_capped(world.partner_id, next_month)
    assert await _lifecycle(db_session, world, ventas) == ("published", None)


async def test_a_cap_above_the_bag_is_allowed(client: Any, db_session: Any) -> None:
    world = await _funded(client, db_session, amount=UNIT)
    ventas = await _agent(db_session, world, "Ventas")
    resp = await client.put(
        f"/console/clients/{world.us.ref}/agents/{ventas}/cap",
        json={"monthly_cap": money(1_000 * UNIT, "USD")},
        headers=world.headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["monthly_cap_micros"] == 1_000 * UNIT


async def test_an_empty_bag_pauses_for_balance_and_only_those_come_back(
    client: Any, db_session: Any, told: list[dict[str, Any]]
) -> None:
    world = await _funded(client, db_session, amount=UNIT)
    ventas = await _agent(db_session, world, "Ventas")
    citas = await _agent(db_session, world, "Citas")
    async with tenant_scoped_session(db_session, world.us.tenant_id):
        agent = await db_session.get(Agent, citas)
        assert agent is not None
        from nexus_api.services import agent_states

        await agent_states.pause(
            db_session,
            agent,
            reason="manual",
            by_kind="partner_member",
            by_id="x",
            origin="console",
            actor="x",
        )
    await db_session.commit()
    await _turn(world, ventas, 2 * UNIT)
    assert await _lifecycle(db_session, world, ventas) == ("paused", "no_balance")
    resp = await client.post(
        f"/console/clients/{world.us.ref}/bag/assign",
        json={"amount": money(UNIT, "USD")},
        headers=world.headers(),
    )
    assert resp.status_code == 200
    assert await _lifecycle(db_session, world, ventas) == ("published", None)
    assert await _lifecycle(db_session, world, citas) == ("paused", "manual"), (
        "lo que pausó una persona no vuelve solo"
    )


# ── los avisos de la bolsa ─────────────────────────────────────────────────


async def _evaluate(db_session: Any, world: MoneyWorld, today: Any = None) -> list[str]:
    async with db_session.begin():
        await apply_partner_to_session(db_session, world.partner_id)
        await as_client(db_session, world.us.tenant_id)
        bag = await db_session.scalar(
            sa.select(ClientWallet)
            .where(ClientWallet.tenant_id == world.us.tenant_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        assert bag is not None
        notices = await alerts.evaluate_bag(db_session, bag, today)
    return [n.kind for n in notices]


async def _spend(world: MoneyWorld, amount: int) -> None:
    await charge_turn(
        partner_id=world.partner_id,
        tenant_id=world.us.tenant_id,
        agent_id=None,
        amount_usd=amount,
        usage_ref=f"channel:{uuid.uuid4().hex}",
    )


async def test_low_fires_once_with_its_base_and_rearms_when_the_balance_goes_up(
    client: Any, db_session: Any
) -> None:
    world = await _funded(client, db_session)
    await _spend(world, 850_000)
    async with db_session.begin():
        await apply_partner_to_session(db_session, world.partner_id)
        await as_client(db_session, world.us.tenant_id)
        bag = await db_session.get(ClientWallet, world.us.tenant_id)
        assert bag is not None
        notices = await alerts.evaluate_bag(db_session, bag)
    assert [(n.kind, n.data["base_micros"]) for n in notices] == [("client.wallet.low", 10 * UNIT)]
    assert await _evaluate(db_session, world) == [], "una vez al mes"
    await client.post(
        f"/console/clients/{world.us.ref}/bag/assign",
        json={"amount": money(5 * UNIT, "USD")},
        headers=world.headers(),
    )
    assert await _evaluate(db_session, world) == [], "con saldo, nada que avisar"
    await _spend(world, 600_000)  # quedan 0,5 de una base de 15
    assert await _evaluate(db_session, world) == ["client.wallet.low"], "rearmado"


async def test_the_20_percent_box_turns_low_off(client: Any, db_session: Any) -> None:
    world = await money_world(db_session, roles=())
    resp = await client.post(
        f"/console/clients/{world.us.ref}/bag/assign",
        json={"amount": money(10 * UNIT, "USD"), "alert_low": False},
        headers=world.headers(),
    )
    assert resp.status_code == 200
    await _spend(world, 950_000)
    assert await _evaluate(db_session, world) == []


async def test_empty_fires_every_day_while_it_lasts(client: Any, db_session: Any) -> None:
    world = await _funded(client, db_session, amount=UNIT)
    await _spend(world, UNIT)
    today = datetime.now(UTC).date()
    assert await _evaluate(db_session, world, today) == ["client.wallet.empty"]
    assert await _evaluate(db_session, world, today) == []
    assert await _evaluate(db_session, world, today + timedelta(days=1)) == ["client.wallet.empty"]


async def test_not_enough_reads_the_last_seven_days_and_needs_three(
    client: Any, db_session: Any
) -> None:
    world = await _funded(client, db_session, amount=UNIT)
    # El día 10 del mes en curso: «no llega» compara con lo que falta para fin de
    # mes, y los últimos días de cada mes la prueba fallaba (CI del 2026-10-30).
    today = datetime.now(UTC).date().replace(day=10)
    async with db_session.begin():
        await apply_partner_to_session(db_session, world.partner_id)
        await as_client(db_session, world.us.tenant_id)
        bag = await db_session.get(ClientWallet, world.us.tenant_id)
        assert bag is not None
        # Sin base (no salta «Queda poco») y con un saldo que no llega a un día.
        bag.month_base_micros = 0
        for days_ago in (1, 2):
            db_session.add(
                ClientWalletEntry(
                    tenant_id=world.us.tenant_id,
                    partner_id=world.partner_id,
                    kind="debit_turn",
                    amount_micros=-UNIT,
                    balance_after_micros=bag.balance_micros,
                    currency="USD",
                    usage_ref=f"channel:old-{days_ago}-{uuid.uuid4().hex[:6]}",
                    created_at=datetime.combine(today, datetime.min.time(), UTC)
                    - timedelta(days=days_ago, hours=-1),
                )
            )
    assert await _evaluate(db_session, world, today) == [], "con 2 días no se estima"
    async with db_session.begin():
        await apply_partner_to_session(db_session, world.partner_id)
        await as_client(db_session, world.us.tenant_id)
        db_session.add(
            ClientWalletEntry(
                tenant_id=world.us.tenant_id,
                partner_id=world.partner_id,
                kind="debit_turn",
                amount_micros=-UNIT,
                balance_after_micros=UNIT,
                currency="USD",
                usage_ref=f"channel:old-3-{uuid.uuid4().hex[:6]}",
                created_at=datetime.combine(today, datetime.min.time(), UTC)
                - timedelta(days=3, hours=-1),
            )
        )
    assert await _evaluate(db_session, world, today) == ["client.wallet.not_enough"]
    assert await _evaluate(db_session, world, today) == [], "una vez al mes"


async def test_the_alerts_cron_tells_the_partner(
    client: Any, db_session: Any, told: list[dict[str, Any]]
) -> None:
    from nexus_worker.streams.wallet_crons import alerts_tick

    world = await _funded(client, db_session, amount=UNIT)
    await _spend(world, UNIT)
    told.clear()
    await alerts_tick()
    mine = [t for t in told if t["tenant_id"] == world.us.tenant_id]
    assert [t["kind"] for t in mine] == ["client.wallet.empty"]
    assert mine[0]["severity"] == "critical"
    await alerts_tick()
    assert len([t for t in told if t["tenant_id"] == world.us.tenant_id]) == 1


async def test_the_gate_adds_under_15ms_p95(
    client: Any, db_session: Any, console_world: dict[str, Any]
) -> None:
    """Objetivo de ``plan.md`` (T157): lo que la puerta con bolsas **añade** al turno,
    frente a la puerta de hoy (asignaciones), con las muestras intercaladas para
    que la carga de la máquina pese igual en las dos."""
    import statistics
    import time

    from nexus_api.metering.wallet import allow_channel_turn

    world = await _funded(client, db_session)
    legacy = console_world["a"]["tenant_id"]
    await allow_channel_turn(world.us.tenant_id)  # la primera abre el pool
    await allow_channel_turn(legacy)
    bags_ms: list[float] = []
    legacy_ms: list[float] = []
    for _ in range(60):
        for tenant_id, samples in ((world.us.tenant_id, bags_ms), (legacy, legacy_ms)):
            start = time.perf_counter()
            await allow_channel_turn(tenant_id)
            samples.append((time.perf_counter() - start) * 1000)
    added = statistics.quantiles(bags_ms, n=20)[18] - statistics.quantiles(legacy_ms, n=20)[18]
    assert added < 15, f"la puerta con bolsas añade {added:.1f} ms p95"


async def test_the_agent_says_its_cap_and_what_it_spent(client: Any, db_session: Any) -> None:
    world = await _funded(client, db_session)
    ventas = await _agent(db_session, world, "Ventas")
    await client.put(
        f"/console/clients/{world.us.ref}/agents/{ventas}/cap",
        json={"monthly_cap": money(2 * UNIT, "USD")},
        headers=world.headers(),
    )
    await _turn(world, ventas, 30_000)
    header = await client.get(
        f"/console/clients/{world.us.ref}/agents/{ventas}", headers=world.headers()
    )
    assert header.status_code == 200, header.text
    out = header.json()
    assert (out["monthly_cap_micros"], out["month_spent_micros"], out["cap_currency"]) == (
        2 * UNIT,
        30_000,
        "USD",
    )
