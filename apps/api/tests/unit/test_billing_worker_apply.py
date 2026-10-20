"""Spec 005 · lo que el trabajo de fondo hace con un aviso, y lo que rechaza.

Unidad porque lo que se prueba son las **puertas**, no la base de datos: qué
acredita y qué no. Las tres que importan salen de la guía de cumplimiento de
Stripe (verificada 2026-09-12) y de ADR-037 D3.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from nexus_worker.billing.process_event import Skip, apply_credit_purchase

pytestmark = [pytest.mark.asyncio]

_PID = uuid.uuid4()


class FakeSession:
    """No toca base de datos: sólo responde a lo que el código pregunta."""

    def __init__(self, *, fulfilled: bool = False) -> None:
        self.fulfilled = fulfilled


async def _run(monkeypatch: pytest.MonkeyPatch, checkout: Any, *, fulfilled: bool = False) -> int:
    added: list[tuple[uuid.UUID, int]] = []

    async def fake_already(_session: Any, _sid: str) -> bool:
        return fulfilled

    async def fake_add(*, partner_id: uuid.UUID, qty: int, kind: str, idempotency_key: str) -> Any:
        # Spec 033: a Stripe credit is its own kind, keyed by the session.
        assert kind == "credit_stripe"
        assert idempotency_key.startswith("stripe_credit:")
        added.append((partner_id, qty))
        return SimpleNamespace(duplicate=False)

    monkeypatch.setattr("nexus_api.billing.events.already_fulfilled", fake_already)
    monkeypatch.setattr("nexus_api.metering.wallet.add_purchased", fake_add)
    units = await apply_credit_purchase(FakeSession(), partner_id=_PID, checkout=checkout)
    assert added == [(_PID, units)]
    return units


async def test_a_paid_session_credits_at_the_sold_rate(monkeypatch) -> None:
    checkout = SimpleNamespace(
        mode="payment",
        metadata={"kind": "credit"},
        id="cs_1",
        payment_status="paid",
        amount_total=5_000,
    )
    assert await _run(monkeypatch, checkout) == 5_000_000


async def test_an_unpaid_session_credits_nothing(monkeypatch) -> None:
    """Una sesión completada con el pago pendiente **no es una compra**."""
    checkout = SimpleNamespace(
        mode="payment",
        metadata={"kind": "credit"},
        id="cs_2",
        payment_status="unpaid",
        amount_total=5_000,
    )
    with pytest.raises(Skip, match="pendiente"):
        await _run(monkeypatch, checkout)


async def test_a_session_already_fulfilled_credits_nothing(monkeypatch) -> None:
    """La segunda ancla de idempotencia.

    ``completed`` y ``async_payment_succeeded`` son eventos DISTINTOS y llegan
    los dos para la misma compra; el UNIQUE por id de evento no los detiene.
    """
    checkout = SimpleNamespace(
        mode="payment",
        metadata={"kind": "credit"},
        id="cs_3",
        payment_status="paid",
        amount_total=5_000,
    )
    with pytest.raises(Skip, match="ya se acreditó"):
        await _run(monkeypatch, checkout, fulfilled=True)


async def test_a_zero_amount_credits_nothing(monkeypatch) -> None:
    checkout = SimpleNamespace(
        mode="payment",
        metadata={"kind": "credit"},
        id="cs_4",
        payment_status="paid",
        amount_total=0,
    )
    with pytest.raises(Skip):
        await _run(monkeypatch, checkout)


async def test_a_subscription_checkout_never_buys_balance(monkeypatch) -> None:
    """Spec 034 (R4.1): a tier checkout completes with the same event and the
    same partner reference. Its money is a subscription, not balance."""
    checkout = SimpleNamespace(
        mode="subscription", metadata={}, id="cs_sub", payment_status="paid", amount_total=2_000
    )
    with pytest.raises(Skip, match="no es una compra de crédito"):
        await _run(monkeypatch, checkout)


async def test_a_payment_without_the_credit_kind_buys_nothing(monkeypatch) -> None:
    checkout = SimpleNamespace(
        mode="payment",
        metadata={"kind": "other"},
        id="cs_x",
        payment_status="paid",
        amount_total=2_000,
    )
    with pytest.raises(Skip, match="no es una compra de crédito"):
        await _run(monkeypatch, checkout)


# ── Los objetos de verdad del SDK (2026-10-20) ───────────────────────────────
#
# Desde stripe-python 13 un objeto de Stripe no es un dict: ``.get`` lanza y
# ``hasattr(obj, "get")`` es False. Leer ``metadata`` así daba «sin tipo» y en
# staging se descartaron una compra de saldo y una recarga pagada. Los tests de
# arriba usan dicts y no lo veían: estos usan el objeto que devuelve el SDK.


def _stripe_object(values: dict[str, Any]) -> Any:
    from stripe import StripeObject

    return StripeObject.construct_from(values, "sk_test_x")


async def test_a_real_sdk_credit_session_credits(monkeypatch) -> None:
    checkout = _stripe_object(
        {
            "id": "cs_real",
            "mode": "payment",
            "metadata": {"kind": "credit", "partner_id": str(_PID)},
            "payment_status": "paid",
            "amount_total": 2_000,
        }
    )
    assert await _run(monkeypatch, checkout) == 2_000_000


async def test_a_real_sdk_paid_card_invoice_settles(monkeypatch) -> None:
    from nexus_worker.billing.process_event import handle_entry

    invoice = _stripe_object(
        {
            "id": "in_real",
            "amount_paid": 2_000,
            "status": "paid",
            "metadata": {"kind": "auto_recharge", "charge_id": str(uuid.uuid4())},
        }
    )
    client = SimpleNamespace(invoices=SimpleNamespace(retrieve=lambda _id: invoice))
    settled: list[Any] = []

    async def fake_settle(partner_id: uuid.UUID, inv: Any) -> bool:
        settled.append((partner_id, inv))
        return True

    monkeypatch.setattr("nexus_api.services.partner_billing.settle_paid_invoice", fake_settle)
    status = await handle_entry(
        FakeSession(),
        client,
        {"event_type": "invoice.paid", "partner_id": str(_PID), "object_id": "in_real"},
    )
    assert status == "processed"
    assert settled == [(_PID, invoice)]


def test_field_reads_sdk_objects_and_dicts_alike() -> None:
    from nexus_api.billing.provider import field

    obj = _stripe_object({"metadata": {"kind": "auto_recharge"}, "missing": None})
    assert field(field(obj, "metadata"), "kind") == "auto_recharge"
    assert field({"metadata": {"kind": "credit"}}, "metadata") == {"kind": "credit"}
    assert field(obj, "nope", "x") == "x"
    assert field(obj, "missing", "x") == "x"
    assert field(None, "kind") is None
