"""Spec 047, T153 — asignar saldo y «Pedir saldo» (requisitos 45.1 a 45.9).

La parte de la API: el recibo que el modal enseña (con la línea del BCE, el
relleno y la casilla del 20 %), lo que falta cuando no llega, el aviso ámbar de la
cuenta y «Pedir saldo» para quien no puede asignar: una vez al día por cliente,
avisando a owners y admins, y nunca en la consola lite ni en la app. Lo que se ve
(el modal en 6 sitios, el formato ``es-ES``) lo cubre ``e2e/money.spec.ts``.
"""

from __future__ import annotations

from typing import Any

import pytest

from nexus_api.main import app
from nexus_api.services import channel_config

from ._wallet_world import EUR_USD, UNIT, bag_of, money, money_world

pytestmark = [pytest.mark.integration]


@pytest.fixture
def told(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    async def _announce(**kw: Any) -> None:
        out.append(kw)

    monkeypatch.setattr(channel_config, "announce", _announce)
    return out


async def test_the_receipt_says_before_assigned_debited_fx_after_and_whats_left(
    client: Any, db_session: Any
) -> None:
    world = await money_world(db_session, roles=())
    resp = await client.post(
        f"/console/clients/{world.es.ref}/bag/assign",
        json={
            "amount": money(25 * UNIT, "EUR"),
            "refill_up_to": money(25 * UNIT, "EUR"),
        },
        headers={**world.headers(), "Idempotency-Key": "modal-1"},
    )
    assert resp.status_code == 200, resp.text
    receipt = resp.json()
    debited = int(25 * UNIT * EUR_USD)
    assert receipt["client_balance_before"] == money(0, "EUR")
    assert receipt["assigned"] == money(25 * UNIT, "EUR")
    assert receipt["debited_from_account"] == money(debited, "USD")
    assert receipt["client_balance_after"] == money(25 * UNIT, "EUR")
    assert receipt["account_left"] == money(100 * UNIT - debited, "USD"), "el aviso final"
    assert receipt["fx"]["source"] == "ECB" and receipt["fx"]["date"]
    assert receipt["warn_low_account"] is False
    bag = await bag_of(db_session, world, world.es.tenant_id)
    assert bag.refill_up_to_micros == 25 * UNIT, "el relleno se guarda con la asignación"
    assert bag.alert_low_enabled is True, "la casilla del 20 % viene marcada"


async def test_when_the_account_falls_short_it_says_how_much_is_missing(
    client: Any, db_session: Any
) -> None:
    world = await money_world(db_session, purchased=5 * UNIT, roles=())
    resp = await client.post(
        f"/console/clients/{world.us.ref}/bag/assign",
        json={"amount": money(8 * UNIT, "USD")},
        headers=world.headers(),
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == {
        "code": "insufficient_account",
        "available_micros": 5 * UNIT,
        "currency": "USD",
        "missing_micros": 3 * UNIT,
    }
    amber = await client.post(
        f"/console/clients/{world.us.ref}/bag/assign",
        json={"amount": money(4 * UNIT + UNIT // 2, "USD")},
        headers=world.headers(),
    )
    assert amber.json()["warn_low_account"] is True, "queda menos del 20 % de la cuenta"


async def test_asking_for_balance_is_for_who_cannot_assign_once_a_day(
    client: Any, db_session: Any, told: list[dict[str, Any]]
) -> None:
    world = await money_world(db_session)
    url = f"/console/clients/{world.us.ref}/bag/request"
    owner = await client.post(url, json={}, headers=world.headers())
    assert owner.status_code == 409 and owner.json()["detail"]["code"] == "can_assign"
    too_long = await client.post(url, json={"note": "x" * 281}, headers=world.as_role("builder"))
    assert too_long.status_code == 422
    asked = await client.post(
        url, json={"note": "Se le acaba el viernes"}, headers=world.as_role("builder")
    )
    assert asked.status_code == 201, asked.text
    (notice,) = told
    assert notice["kind"] == "client.balance_request"
    assert notice["data"]["by_name"], "quién lo pidió, con su nombre"
    assert notice["tenant_id"] == world.us.tenant_id
    assert notice["data"]["note"] == "Se le acaba el viernes"
    again = await client.post(url, json={}, headers=world.as_role("analyst"))
    assert again.status_code == 429
    assert again.json()["detail"] == {
        "code": "request_already_sent_today",
        "retry_after": "tomorrow",
    }
    other_client = await client.post(
        f"/console/clients/{world.es.ref}/bag/request", json={}, headers=world.as_role("billing")
    )
    assert other_client.status_code == 201, "una al día por cliente, no por partner"


def test_asking_for_balance_does_not_exist_in_the_lite_console_nor_the_app() -> None:
    paths = {getattr(r, "path", "") for r in app.routes}
    lite_or_app = [p for p in paths if p.startswith(("/console/lite", "/app"))]
    assert lite_or_app, "control: las rutas lite y de la app están montadas"
    assert not [p for p in lite_or_app if "bag" in p or ("balance" in p and "request" in p)]


async def test_the_bag_list_says_balance_was_asked_today(client: Any, db_session: Any) -> None:
    world = await money_world(db_session, roles=("builder",))
    await client.post(
        f"/console/clients/{world.es.ref}/bag/assign",
        json={"amount": money(UNIT, "EUR")},
        headers=world.headers(),
    )
    before = (await client.get("/console/wallet/bags", headers=world.as_role("builder"))).json()
    assert next(b for b in before if b["ref"] == world.es.ref)["requested_at"] is None
    await client.post(
        f"/console/clients/{world.es.ref}/bag/request", json={}, headers=world.as_role("builder")
    )
    after = (await client.get("/console/wallet/bags", headers=world.as_role("builder"))).json()
    assert next(b for b in after if b["ref"] == world.es.ref)["requested_at"], "«Pedido hace…»"


async def test_the_account_figures_come_with_the_wallet(client: Any, db_session: Any) -> None:
    world = await money_world(db_session, roles=())
    await client.post(
        f"/console/clients/{world.us.ref}/bag/assign",
        json={"amount": money(10 * UNIT, "USD")},
        headers=world.headers(),
    )
    wallet = (await client.get("/console/wallet", headers=world.headers())).json()
    assert wallet["bags_active"] is True and wallet["account_currency"] == "USD"
    assert wallet["assignable_micros"] == 90 * UNIT, "sin el pool incluido"
    assert wallet["in_bags_micros"] == 10 * UNIT and wallet["in_bags_approx"] is False
