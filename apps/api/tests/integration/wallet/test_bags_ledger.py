"""Spec 047, T151 — las bolsas y su libro (requisitos 43.1 a 43.14 y 6.7).

La bolsa es dinero apartado para un cliente, en EUR o USD según su país. Cada
traspaso es una fila con su clave y su cambio del BCE, un asiento en el libro de la
cuenta y su gemelo en la bolsa; el cuadre diario lo comprueba al céntimo.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
import sqlalchemy as sa
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.db.models import (
    ClientWallet,
    ClientWalletEntry,
    UsageLedger,
    WalletTransfer,
)
from nexus_api.services.wallet import bags, fx
from nexus_api.services.wallet.ledger import reconcile

from ._wallet_world import (
    EUR_USD,
    UNIT,
    MoneyWorld,
    account_of,
    as_client,
    bag_of,
    money,
    money_world,
)

pytestmark = [pytest.mark.integration]


def _bag_url(world: MoneyWorld, ref: str, action: str) -> str:
    return f"/console/clients/{ref}/bag/{action}"


async def _assign(
    client: Any, world: MoneyWorld, ref: str, amount: int, currency: str, key: str | None = None
) -> Any:
    headers = world.headers()
    if key:
        headers["Idempotency-Key"] = key
    return await client.post(
        _bag_url(world, ref, "assign"), json={"amount": money(amount, currency)}, headers=headers
    )


async def _reconciled(db_session: Any, world: MoneyWorld) -> list[dict[str, Any]]:
    async with db_session.begin():
        await apply_partner_to_session(db_session, world.partner_id)
        result = await reconcile(db_session, world.partner_id)
    return result.differences


# ── monedas ────────────────────────────────────────────────────────────────


async def test_the_bag_is_in_the_clients_currency_and_the_account_in_usd(
    client: Any, db_session: Any
) -> None:
    world = await money_world(db_session)
    es = await _assign(client, world, world.es.ref, 10 * UNIT, "EUR")
    us = await _assign(client, world, world.us.ref, 10 * UNIT, "USD")
    assert es.status_code == 200, es.text
    assert us.status_code == 200, us.text
    assert es.json()["assigned"] == money(10 * UNIT, "EUR"), "España: la bolsa en euros"
    assert us.json()["assigned"] == money(10 * UNIT, "USD")
    assert (await account_of(db_session, world)).currency == "USD"
    wrong = await _assign(client, world, world.es.ref, UNIT, "USD")
    assert wrong.status_code == 422 and wrong.json()["detail"]["code"] == "currency_mismatch"


async def test_changing_a_bag_currency_converts_after_confirming(
    client: Any, db_session: Any
) -> None:
    world = await money_world(db_session)
    await _assign(client, world, world.es.ref, 10 * UNIT, "EUR")
    url = _bag_url(world, world.es.ref, "currency")
    ask = await client.put(url, json={"currency": "USD"}, headers=world.headers())
    assert ask.status_code == 409, ask.text
    detail = ask.json()["detail"]
    assert detail["code"] == "confirm_required"
    assert detail["would_be"] == money(int(10 * UNIT * EUR_USD), "USD")
    assert detail["fx"]["source"] == "ECB"
    done = await client.put(url, json={"currency": "USD", "confirm": True}, headers=world.headers())
    assert done.status_code == 200, done.text
    assert done.json()["balance"] == money(int(10 * UNIT * EUR_USD), "USD")
    assert await _reconciled(db_session, world) == []


async def test_only_auphere_changes_the_account_currency_converting_with_an_entry(
    client: Any, db_session: Any, admin_headers: dict[str, str]
) -> None:
    from nexus_api.services import operator_identity

    world = await money_world(db_session)
    op = await operator_identity.create_account(
        db_session, email=f"op-{uuid.uuid4().hex[:6]}@auphere.test", password="x" * 16, role="admin"
    )
    await db_session.commit()
    resp = await client.put(
        f"/admin/partners/{world.partner_id}/account-currency",
        json={"currency": "EUR", "reason": "Factura en euros"},
        headers={**admin_headers, "X-Operator-Id": str(op.id)},
    )
    assert resp.status_code == 200, resp.text
    account = await account_of(db_session, world)
    assert account.currency == "EUR"
    assert account.purchased_remaining == fx.convert(100 * UNIT, Decimal(1) / EUR_USD)
    async with db_session.begin():
        await apply_partner_to_session(db_session, world.partner_id)
        kinds = (
            await db_session.scalars(
                sa.select(WalletTransfer.kind).where(WalletTransfer.partner_id == world.partner_id)
            )
        ).all()
    assert kinds == ["currency_change"], "el cambio deja su asiento"
    # El partner no tiene ninguna ruta para cambiarla.
    from nexus_api.main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    assert not any("account-currency" in p for p in paths if p.startswith("/console"))


# ── asignar ────────────────────────────────────────────────────────────────


async def test_assign_is_one_transfer_with_the_days_ecb_rate_and_its_key(
    client: Any, db_session: Any
) -> None:
    world = await money_world(db_session)
    first = await _assign(client, world, world.es.ref, 10 * UNIT, "EUR", key="k-1")
    again = await _assign(client, world, world.es.ref, 10 * UNIT, "EUR", key="k-1")
    assert first.status_code == again.status_code == 200, first.text
    receipt = first.json()
    assert receipt["client_balance_before"] == money(0, "EUR")
    assert receipt["debited_from_account"] == money(int(10 * UNIT * EUR_USD), "USD")
    # El cambio guardado es el de la cuenta a la bolsa (USD → EUR) del BCE del día.
    assert receipt["fx"]["date"] == datetime.now(UTC).date().isoformat()
    assert receipt["fx"]["source"] == "ECB"
    assert abs(Decimal(receipt["fx"]["rate"]) - Decimal(1) / EUR_USD) < Decimal("1e-8")
    account = await account_of(db_session, world)
    assert account.purchased_remaining == 100 * UNIT - int(10 * UNIT * EUR_USD), "una sola vez"
    async with db_session.begin():
        await apply_partner_to_session(db_session, world.partner_id)
        transfers = (
            await db_session.scalars(
                sa.select(WalletTransfer).where(WalletTransfer.partner_id == world.partner_id)
            )
        ).all()
        ledger = (
            await db_session.scalars(
                sa.select(UsageLedger).where(
                    UsageLedger.partner_id == world.partner_id, UsageLedger.kind == "bag_assign"
                )
            )
        ).all()
        await as_client(db_session, world.es.tenant_id)
        entries = (
            await db_session.scalars(
                sa.select(ClientWalletEntry).where(
                    ClientWalletEntry.tenant_id == world.es.tenant_id
                )
            )
        ).all()
    (transfer,) = transfers
    assert transfer.idempotency_key == "k-1" and transfer.fx_date == datetime.now(UTC).date()
    assert transfer.client_amount_micros == 10 * UNIT and transfer.client_currency == "EUR"
    (row,) = ledger
    assert row.qty == transfer.partner_amount_micros and row.bucket == "purchased"
    (entry,) = entries
    assert (entry.kind, entry.amount_micros, entry.balance_after_micros, entry.currency) == (
        "assign",
        10 * UNIT,
        10 * UNIT,
        "EUR",
    )
    assert entry.transfer_id == transfer.id


async def test_assign_never_goes_below_the_limit_and_never_takes_the_pool(
    client: Any, db_session: Any
) -> None:
    world = await money_world(db_session, purchased=50 * UNIT, pool=30 * UNIT)
    over = await _assign(client, world, world.us.ref, 60 * UNIT, "USD")
    assert over.status_code == 409, over.text
    detail = over.json()["detail"]
    assert detail["code"] == "insufficient_account"
    assert detail["available_micros"] == 50 * UNIT, "el pool incluido no cuenta"
    assert detail["missing_micros"] == 10 * UNIT
    exact = await _assign(client, world, world.us.ref, 50 * UNIT, "USD")
    assert exact.status_code == 200
    account = await account_of(db_session, world)
    assert account.purchased_remaining == 0 and account.included_remaining == 30 * UNIT
    assert exact.json()["warn_low_account"] is True


# ── lo no gastado, bajar y mover ───────────────────────────────────────────


async def test_lower_returns_at_most_what_is_left(client: Any, db_session: Any) -> None:
    world = await money_world(db_session)
    await _assign(client, world, world.us.ref, 20 * UNIT, "USD")
    url = _bag_url(world, world.us.ref, "lower")
    too_much = await client.post(
        url, json={"amount": money(21 * UNIT, "USD")}, headers=world.headers()
    )
    assert too_much.status_code == 409
    assert too_much.json()["detail"] == {"code": "bag_below_spent", "available_micros": 20 * UNIT}
    ok = await client.post(url, json={"amount": money(5 * UNIT, "USD")}, headers=world.headers())
    assert ok.status_code == 200, ok.text
    assert ok.json()["balance"] == money(15 * UNIT, "USD")
    assert (await account_of(db_session, world)).purchased_remaining == 85 * UNIT
    assert await _reconciled(db_session, world) == []


async def test_move_is_one_transfer_with_the_conversion_in_view(
    client: Any, db_session: Any
) -> None:
    world = await money_world(db_session)
    await _assign(client, world, world.us.ref, 20 * UNIT, "USD")
    body = {"from_ref": world.us.ref, "to_ref": world.es.ref, "amount": money(10 * UNIT, "USD")}
    moved = await client.post("/console/wallet/bags/move", json=body, headers=world.headers())
    assert moved.status_code == 200, moved.text
    source, target = moved.json()
    assert source["balance"] == money(10 * UNIT, "USD")
    assert target["balance"] == money(fx.convert(10 * UNIT, Decimal(1) / EUR_USD), "EUR")
    # Más de lo que queda: nada se mueve.
    body["amount"] = money(11 * UNIT, "USD")
    refused = await client.post("/console/wallet/bags/move", json=body, headers=world.headers())
    assert refused.status_code == 409
    assert (await bag_of(db_session, world, world.us.tenant_id)).balance_micros == 10 * UNIT
    # Mover no toca la cuenta.
    assert (await account_of(db_session, world)).purchased_remaining == 80 * UNIT
    assert await _reconciled(db_session, world) == []


# ── rellenar ───────────────────────────────────────────────────────────────


async def test_refill_on_day_one_goes_first_to_who_runs_out_first_and_reports_the_rest(
    client: Any, db_session: Any
) -> None:
    world = await money_world(db_session, purchased=30 * UNIT)
    await _assign(client, world, world.us.ref, 10 * UNIT, "USD")
    await _assign(client, world, world.es.ref, 10 * UNIT, "EUR")
    async with db_session.begin():
        await apply_partner_to_session(db_session, world.partner_id)
        for tenant_id, spent in ((world.us.tenant_id, 9 * UNIT), (world.es.tenant_id, UNIT)):
            await as_client(db_session, tenant_id)
            bag = await db_session.get(ClientWallet, tenant_id)
            assert bag is not None
            bag.refill_up_to_micros = 20 * UNIT
            bag.balance_micros -= spent
            bag.month_spent_micros += spent
            db_session.add(
                ClientWalletEntry(
                    tenant_id=tenant_id,
                    partner_id=world.partner_id,
                    kind="debit_turn",
                    amount_micros=-spent,
                    balance_after_micros=bag.balance_micros,
                    currency=bag.currency,
                    usage_ref=f"channel:t-{tenant_id.hex[:6]}",
                )
            )
    # Quedan 30 - 10 - 10,8 = 9,2 USD en la cuenta. EE. UU. (1 USD, gasta 9 al
    # mes) se queda sin saldo antes que España (9 EUR, gasta 1): va primero y se
    # lleva los 9,2; a España no le llega nada.
    now = datetime.now(UTC)
    first_of_next = (now.replace(day=28) + timedelta(days=4)).replace(day=1)
    async with db_session.begin():
        await apply_partner_to_session(db_session, world.partner_id)
        short = await bags.refill_all(db_session, partner_id=world.partner_id, now=first_of_next)
    us = await bag_of(db_session, world, world.us.tenant_id)
    es = await bag_of(db_session, world, world.es.tenant_id)
    assert us.balance_micros == 1_020_000, "1 + los 9,2 que había en la cuenta"
    assert es.balance_micros == 9 * UNIT, "a España no le llegó nada"
    assert [s["tenant_id"] for s in short] == [str(world.us.tenant_id), str(world.es.tenant_id)]
    assert short[0]["missing_micros"] == 980_000 and short[1]["missing_micros"] == 11 * UNIT
    # Repetirlo el mismo mes no rellena dos veces.
    async with db_session.begin():
        await apply_partner_to_session(db_session, world.partner_id)
        await bags.refill_all(db_session, partner_id=world.partner_id, now=first_of_next)
    assert (await bag_of(db_session, world, world.us.tenant_id)).balance_micros == 1_020_000
    assert await _reconciled(db_session, world) == []


async def test_the_refill_cron_runs_only_on_day_one() -> None:
    from nexus_worker.streams.wallet_crons import refill_tick

    assert await refill_tick(now=datetime(2026, 10, 15, tzinfo=UTC)) == {}


# ── el libro ───────────────────────────────────────────────────────────────


async def test_the_daily_reconciliation_finds_a_cent_out_of_place(
    client: Any, db_session: Any
) -> None:
    from nexus_worker.streams.wallet_crons import reconciliation_tick

    world = await money_world(db_session)
    await _assign(client, world, world.us.ref, 10 * UNIT, "USD")
    assert await _reconciled(db_session, world) == []
    async with db_session.begin():
        await apply_partner_to_session(db_session, world.partner_id)
        await as_client(db_session, world.us.tenant_id)
        await db_session.execute(
            sa.update(ClientWallet)
            .where(ClientWallet.tenant_id == world.us.tenant_id)
            .values(balance_micros=ClientWallet.balance_micros + 1)
        )
    (diff,) = await _reconciled(db_session, world)
    assert diff["kind"] == "bag" and diff["balance"] == diff["entries"] + 1
    problems = await reconciliation_tick()
    assert any(p["partner_id"] == str(world.partner_id) for p in problems)


def test_amounts_are_integers_and_rounding_is_half_even() -> None:
    assert fx.convert(5, Decimal("0.5")) == 2, "2,5 → 2 (al par)"
    assert fx.convert(7, Decimal("0.5")) == 4, "3,5 → 4 (al par)"
    assert isinstance(fx.convert(123_456, EUR_USD), int)


# ── el turno ───────────────────────────────────────────────────────────────


async def test_a_turn_is_charged_to_the_bag_and_crossing_zero_takes_only_what_was_left(
    client: Any, db_session: Any
) -> None:
    world = await money_world(db_session)
    await _assign(client, world, world.us.ref, UNIT, "USD")
    async with db_session.begin():
        await apply_partner_to_session(db_session, world.partner_id)
        first = await bags.debit_turn(
            db_session,
            partner_id=world.partner_id,
            tenant_id=world.us.tenant_id,
            amount_usd=60_000,
            usage_ref="channel:a",
            agent_id=None,
        )
        second = await bags.debit_turn(
            db_session,
            partner_id=world.partner_id,
            tenant_id=world.us.tenant_id,
            amount_usd=60_000,
            usage_ref="channel:b",
            agent_id=None,
        )
        repeated = await bags.debit_turn(
            db_session,
            partner_id=world.partner_id,
            tenant_id=world.us.tenant_id,
            amount_usd=60_000,
            usage_ref="channel:b",
            agent_id=None,
        )
    assert (first.spent, first.balance_after, first.emptied) == (60_000, 40_000, False)
    assert (second.spent, second.balance_after, second.emptied) == (40_000, 0, True)
    assert repeated.duplicate and repeated.balance_after == 0, "la misma ref no cobra dos veces"
    assert await _reconciled(db_session, world) == []


async def test_a_new_client_has_an_empty_bag_the_playground_yes_the_channel_no(
    client: Any, db_session: Any
) -> None:
    from nexus_api.metering.wallet import allow_channel_turn, seed_default_allocation
    from nexus_api.services.wallet.build_budget import require_room_for_partner

    world = await money_world(db_session)
    async with db_session.begin():
        await apply_partner_to_session(db_session, world.partner_id)
        seeded = await seed_default_allocation(
            db_session, partner_id=world.partner_id, tenant_id=world.es.tenant_id, default_cap=500
        )
    assert seeded == 0, "con bolsas no se siembra una asignación de antes"
    assert await allow_channel_turn(world.es.tenant_id) is False, "sin saldo el canal no abre"
    await require_room_for_partner(world.partner_id)  # el playground sí
    async with db_session.begin():
        await apply_partner_to_session(db_session, world.partner_id)
        assert await bags.bags_active(db_session, world.partner_id)
    await _assign(client, world, world.es.ref, UNIT, "EUR")
    assert await allow_channel_turn(world.es.tenant_id) is True


async def test_archiving_offers_the_bag_and_deleting_returns_it_first(
    client: Any, db_session: Any
) -> None:
    world = await money_world(db_session)
    await _assign(client, world, world.us.ref, 7 * UNIT, "USD")
    archived = await client.post(
        f"/console/clients/{world.us.ref}/archive", headers=world.headers()
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["bag_left"] == money(7 * UNIT, "USD")
    returned = await bags.return_all(
        partner_id=world.partner_id, tenant_id=world.us.tenant_id, actor="test"
    )
    assert returned == 7 * UNIT
    assert (await account_of(db_session, world)).purchased_remaining == 100 * UNIT
    assert (
        await bags.return_all(
            partner_id=world.partner_id, tenant_id=world.us.tenant_id, actor="test"
        )
        == 0
    ), "dos veces no devuelve dos veces"


async def test_only_who_has_usage_write_assigns(client: Any, db_session: Any) -> None:
    world = await money_world(db_session)
    for role in ("builder", "analyst", "billing"):
        resp = await client.post(
            _bag_url(world, world.us.ref, "assign"),
            json={"amount": money(UNIT, "USD")},
            headers=world.as_role(role),
        )
        assert resp.status_code == 403, f"{role}: {resp.status_code}"
    admin = await client.post(
        _bag_url(world, world.us.ref, "assign"),
        json={"amount": money(UNIT, "USD")},
        headers=world.as_role("admin"),
    )
    assert admin.status_code == 200, admin.text


# ── la invariante ──────────────────────────────────────────────────────────

_OPS = st.lists(
    st.tuples(
        st.sampled_from(["assign", "lower", "turn", "move"]),
        st.integers(min_value=1, max_value=8 * UNIT),
    ),
    min_size=1,
    max_size=8,
)


@settings(
    max_examples=10,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
@given(ops=_OPS)
async def test_the_money_is_conserved_whatever_the_operations(
    db_session: Any, ops: list[tuple[str, int]]
) -> None:
    """Propiedad (43.9): en USD, lo comprado al empezar es siempre la cuenta más
    las bolsas más lo gastado en turnos; y el cuadre no encuentra diferencias."""
    world = await money_world(db_session, purchased=40 * UNIT, roles=())
    other = world.es.tenant_id
    async with db_session.begin():
        await apply_partner_to_session(db_session, world.partner_id)
        # Las dos bolsas en USD: la conservación es exacta, sin cambio.
        for tenant_id in (world.us.tenant_id, other):
            bag = await bags.bag_for_update(db_session, tenant_id, partner_id=world.partner_id)
            bag.currency = "USD"
    spent = 0
    for n, (op, amount) in enumerate(ops):
        async with db_session.begin():
            await apply_partner_to_session(db_session, world.partner_id)
            try:
                if op == "assign":
                    await bags.assign(
                        db_session,
                        partner_id=world.partner_id,
                        tenant_id=world.us.tenant_id,
                        amount=amount,
                        idempotency_key=f"p-{n}",
                        actor="prop",
                    )
                elif op == "lower":
                    await bags.lower(
                        db_session,
                        partner_id=world.partner_id,
                        tenant_id=world.us.tenant_id,
                        amount=amount,
                        idempotency_key=f"p-{n}",
                        actor="prop",
                    )
                elif op == "move":
                    await bags.move(
                        db_session,
                        partner_id=world.partner_id,
                        from_tenant_id=world.us.tenant_id,
                        to_tenant_id=other,
                        amount=amount,
                        idempotency_key=f"p-{n}",
                        actor="prop",
                    )
                else:
                    debit = await bags.debit_turn(
                        db_session,
                        partner_id=world.partner_id,
                        tenant_id=world.us.tenant_id,
                        amount_usd=amount,
                        usage_ref=f"channel:{world.partner_id.hex[:6]}:{n}",
                        agent_id=None,
                    )
                    spent += debit.spent
            except bags.WalletError:
                pass
    account = await account_of(db_session, world)
    async with db_session.begin():
        await apply_partner_to_session(db_session, world.partner_id)
        in_bags = 0
        for tenant_id in (world.us.tenant_id, other):
            await as_client(db_session, tenant_id)
            in_bags += int(
                await db_session.scalar(
                    sa.select(ClientWallet.balance_micros).where(
                        ClientWallet.tenant_id == tenant_id
                    )
                )
                or 0
            )
    assert account.purchased_remaining + int(in_bags or 0) + spent == 40 * UNIT
    assert account.purchased_remaining >= 0 and int(in_bags or 0) >= 0
    assert await _reconciled(db_session, world) == []


async def test_the_split_into_bags_can_be_adjusted_before_confirming(
    client: Any, db_session: Any
) -> None:
    from nexus_api.db.models import PartnerAllocation

    world = await money_world(db_session, roles=())
    async with db_session.begin():
        await apply_partner_to_session(db_session, world.partner_id)
        for tenant_id, left in ((world.us.tenant_id, 5 * UNIT), (world.es.tenant_id, 3 * UNIT)):
            db_session.add(
                PartnerAllocation(
                    partner_id=world.partner_id, tenant_id=tenant_id, cap=10 * UNIT, remaining=left
                )
            )
    async with db_session.begin():
        await apply_partner_to_session(db_session, world.partner_id)
        assert not await bags.bags_active(db_session, world.partner_id), (
            "hasta confirmar, lo de hoy"
        )
    proposal = (await client.get("/console/wallet/migration", headers=world.headers())).json()
    assert {c["ref"]: c["amount"]["amount_micros"] for c in proposal["clients"]} == {
        world.us.ref: 5 * UNIT,
        world.es.ref: 3 * UNIT,
    }
    bad = await client.post(
        "/console/wallet/migration/confirm",
        json={"adjust": {"no-existe": UNIT}},
        headers=world.headers(),
    )
    assert bad.status_code == 422
    done = await client.post(
        "/console/wallet/migration/confirm",
        json={"adjust": {world.us.ref: 7 * UNIT}},
        headers=world.headers(),
    )
    assert done.status_code == 200, done.text
    assert (await bag_of(db_session, world, world.us.tenant_id)).balance_micros == 7 * UNIT
    es = await bag_of(db_session, world, world.es.tenant_id)
    assert es.currency == "EUR"
    assert es.balance_micros == fx.convert(3 * UNIT, Decimal(1) / EUR_USD)
    async with db_session.begin():
        await apply_partner_to_session(db_session, world.partner_id)
        assert await bags.bags_active(db_session, world.partner_id)
    assert await _reconciled(db_session, world) == []
