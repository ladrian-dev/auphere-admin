"""Spec 005 · R3 — comprar crédito, y que solo cuente lo confirmado.

El saldo comprado es lo que mantiene atendiendo a los clientes finales de un
partner: ellos gastan **solo** ese cubo (Spec A). Que suba cuando no debe es
regalar servicio; que suba dos veces por un pago es doblar un ingreso; que no
suba tras un pago es un incidente con un cliente en producción.

Se ejercita el camino del worker —donde se aplica— y no el del webhook, que
solo registra y encola.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.db.base import get_sessionmaker

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_WORKER_SRC = Path(__file__).resolve().parents[3] / "worker" / "src"
if str(_WORKER_SRC) not in sys.path:
    sys.path.insert(0, str(_WORKER_SRC))

from nexus_worker.billing.process_event import Skip, apply_credit_purchase  # noqa: E402


async def _partner(purchased: int = 0) -> uuid.UUID:
    pid = uuid.uuid4()
    slug = f"buy-{pid.hex[:10]}"
    async with get_sessionmaker()() as s:
        await s.execute(
            sa.text("INSERT INTO partners (id, name, slug, status) VALUES (:i, :n, :s, 'active')"),
            {"i": str(pid), "n": slug, "s": slug},
        )
        await s.execute(
            sa.text("UPDATE partner_wallets SET purchased_remaining = :q WHERE partner_id = :p"),
            {"q": purchased, "p": str(pid)},
        )
        await s.commit()
    return pid


async def _purchased(pid: uuid.UUID) -> int:
    async with get_sessionmaker()() as s:
        value = await s.scalar(
            sa.text("SELECT purchased_remaining FROM partner_wallets WHERE partner_id = :p"),
            {"p": str(pid)},
        )
    return int(value or 0)


def _checkout(**over: Any) -> SimpleNamespace:
    fields: dict[str, Any] = {
        "id": f"cs_{uuid.uuid4().hex[:12]}",
        "payment_status": "paid",
        "amount_total": 5_000,
    }
    fields.update(over)
    return SimpleNamespace(**fields)


async def _record(session: Any, checkout: Any, *, status: str, event_type: str) -> None:
    """Deja el rastro que la idempotencia por sesión consulta."""
    await session.execute(
        sa.text(
            "INSERT INTO billing_events "
            "(id, provider_event_id, event_type, checkout_session_id, status, payload) "
            "VALUES (:i, :e, :t, :c, :s, '{}'::jsonb)"
        ),
        {
            "i": str(uuid.uuid4()),
            "e": f"evt_{uuid.uuid4().hex[:12]}",
            "t": event_type,
            "c": checkout.id,
            "s": status,
        },
    )


async def test_a_confirmed_payment_raises_the_balance() -> None:
    """V14. 50 USD a 10 USD por millón son 5 millones de unidades."""
    pid = await _partner()
    async with get_sessionmaker()() as s:
        units = await apply_credit_purchase(s, partner_id=pid, checkout=_checkout())
        await s.commit()
    assert units == 5_000_000
    assert await _purchased(pid) == 5_000_000


async def test_it_adds_to_what_was_already_there() -> None:
    pid = await _partner(purchased=1_000)
    async with get_sessionmaker()() as s:
        await apply_credit_purchase(s, partner_id=pid, checkout=_checkout(amount_total=1_000))
        await s.commit()
    assert await _purchased(pid) == 1_001_000


async def test_an_open_session_credits_nothing() -> None:
    """V15. Se acredita con la confirmación, nunca con la intención."""
    pid = await _partner()
    async with get_sessionmaker()() as s:
        with pytest.raises(Skip):
            await apply_credit_purchase(
                s, partner_id=pid, checkout=_checkout(payment_status="unpaid")
            )
    assert await _purchased(pid) == 0


async def test_the_same_session_notified_twice_credits_once() -> None:
    """V17. ``completed`` y ``async_payment_succeeded`` son eventos DISTINTOS.

    El UNIQUE sobre el id de evento no los detiene; lo que los detiene es la
    segunda ancla — preguntar si esa sesión ya se cumplió.
    """
    pid = await _partner()
    checkout = _checkout()

    async with get_sessionmaker()() as s:
        await apply_credit_purchase(s, partner_id=pid, checkout=checkout)
        await _record(s, checkout, status="processed", event_type="checkout.session.completed")
        await s.commit()

    after_first = await _purchased(pid)
    assert after_first == 5_000_000

    async with get_sessionmaker()() as s:
        with pytest.raises(Skip, match="ya se acreditó"):
            await apply_credit_purchase(s, partner_id=pid, checkout=checkout)

    assert await _purchased(pid) == after_first, "la misma compra acreditó dos veces"


async def test_two_different_purchases_both_credit() -> None:
    """La otra mitad del caso límite «dos pestañas compran a la vez».

    Dos avisos del mismo pago son uno; **dos pagos distintos son dos ingresos**.
    Una idempotencia demasiado ancha —por partner e importe, por ejemplo— se
    comería el segundo.
    """
    pid = await _partner()
    async with get_sessionmaker()() as s:
        first = _checkout(amount_total=1_000)
        await apply_credit_purchase(s, partner_id=pid, checkout=first)
        await _record(s, first, status="processed", event_type="checkout.session.completed")
        second = _checkout(amount_total=1_000)
        await apply_credit_purchase(s, partner_id=pid, checkout=second)
        await s.commit()
    assert await _purchased(pid) == 2_000_000


async def test_a_failed_event_does_not_block_a_later_retry() -> None:
    """Sólo un cumplimiento ``processed`` cuenta como ya acreditado.

    Si un intento fallido bloqueara el reintento, un fallo transitorio nuestro
    se convertiría en una compra que el partner pagó y nunca recibió.
    """
    pid = await _partner()
    checkout = _checkout()
    async with get_sessionmaker()() as s:
        await _record(s, checkout, status="failed", event_type="checkout.session.completed")
        await s.commit()
    async with get_sessionmaker()() as s:
        await apply_credit_purchase(s, partner_id=pid, checkout=checkout)
        await s.commit()
    assert await _purchased(pid) == 5_000_000
