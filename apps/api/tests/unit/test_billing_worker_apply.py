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

    async def fake_add(*, partner_id: uuid.UUID, qty: int) -> None:
        added.append((partner_id, qty))

    monkeypatch.setattr("nexus_api.billing.events.already_fulfilled", fake_already)
    monkeypatch.setattr("nexus_api.metering.wallet.add_purchased", fake_add)
    units = await apply_credit_purchase(FakeSession(), partner_id=_PID, checkout=checkout)
    assert added == [(_PID, units)]
    return units


async def test_a_paid_session_credits_at_the_sold_rate(monkeypatch) -> None:
    checkout = SimpleNamespace(id="cs_1", payment_status="paid", amount_total=5_000)
    assert await _run(monkeypatch, checkout) == 5_000_000


async def test_an_unpaid_session_credits_nothing(monkeypatch) -> None:
    """Una sesión completada con el pago pendiente **no es una compra**."""
    checkout = SimpleNamespace(id="cs_2", payment_status="unpaid", amount_total=5_000)
    with pytest.raises(Skip, match="pendiente"):
        await _run(monkeypatch, checkout)


async def test_a_session_already_fulfilled_credits_nothing(monkeypatch) -> None:
    """La segunda ancla de idempotencia.

    ``completed`` y ``async_payment_succeeded`` son eventos DISTINTOS y llegan
    los dos para la misma compra; el UNIQUE por id de evento no los detiene.
    """
    checkout = SimpleNamespace(id="cs_3", payment_status="paid", amount_total=5_000)
    with pytest.raises(Skip, match="ya se acreditó"):
        await _run(monkeypatch, checkout, fulfilled=True)


async def test_a_zero_amount_credits_nothing(monkeypatch) -> None:
    checkout = SimpleNamespace(id="cs_4", payment_status="paid", amount_total=0)
    with pytest.raises(Skip):
        await _run(monkeypatch, checkout)
