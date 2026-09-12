"""Spec 005 · el recorrido de humo, encadenado (T114).

Los diez pasos del quickstart sobre **un solo partner**, en orden. Cada paso
existe por separado en otro fichero; lo que este añade es el encadenamiento —
que es donde aparecen los fallos que ningún test aislado ve, porque cada uno
empieza de un estado limpio que la vida real no ofrece.

El paso 7 es el que decide si la feature está terminada: **si una confirmación
pendiente se pierde al llegar a impagada, no lo está**, por muy verdes que
estén las suites.

> Sin cuenta conectada en local (decisión de 2026-09-12), los avisos del
> proveedor se simulan aplicando el estado que enviaría. Lo que se recorre es
> nuestro comportamiento de punta a punta.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from nexus_api.billing.ladder import cancel_subscription, grant_tier, move_to
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models.membership import STATE_PAYMENT_FAILED, STATE_UNPAID
from nexus_api.metering.wallet import apply_tier_change, renew_included_if_expired
from nexus_api.services.membership_limits import TierLimitReached, assert_can_add_teammate

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _q(sql: str, **params):
    async with get_sessionmaker()() as s:
        return (await s.execute(sa.text(sql), params)).first()


async def test_the_ten_steps_in_order() -> None:
    pid = uuid.uuid4()
    slug = f"smoke-{pid.hex[:8]}"

    # 1 · Un partner nuevo es Free, sin teammates.
    async with get_sessionmaker()() as s:
        await s.execute(
            sa.text("INSERT INTO partners (id, name, slug, status) VALUES (:i, :n, :s, 'active')"),
            {"i": str(pid), "n": slug, "s": slug},
        )
        await s.commit()
        with pytest.raises(TierLimitReached) as exc:
            await assert_can_add_teammate(s, pid)
        assert exc.value.tier_code == "free" and exc.value.limit == 0

    # 2 · Contratar Pro: nivel y pool en el mismo acto.
    async with get_sessionmaker()() as s:
        await grant_tier(s, partner_id=pid, tier_code="pro")
        await s.commit()
    row = await _q(
        "SELECT s.tier_code, p.weekly_pool_tokens FROM partner_subscriptions s "
        "JOIN partners p ON p.id = s.partner_id WHERE s.partner_id = :p",
        p=str(pid),
    )
    assert row[0] == "pro" and row[1] == 500_000

    # 3 · Dos teammates entran; el tercero no, y no se archiva ninguno.
    async with get_sessionmaker()() as s:
        for i in range(2):
            await assert_can_add_teammate(s, pid)
            await s.execute(
                sa.text(
                    "INSERT INTO teammates "
                    "(id, partner_id, name, job, model, tool_names, permissions, "
                    " local_exec, status, created_by) "
                    "VALUES (:i, :p, :n, 'j', 'openai/gpt-5.6-luna', '{}', '{}'::jsonb, "
                    "false, 'active', 'smoke')"
                ),
                {"i": str(uuid.uuid4()), "p": str(pid), "n": f"tm{i}"},
            )
            await s.commit()
        with pytest.raises(TierLimitReached):
            await assert_can_add_teammate(s, pid)
    alive = await _q(
        "SELECT count(*) FROM teammates WHERE partner_id = :p AND status <> 'archived'",
        p=str(pid),
    )
    assert alive[0] == 2

    # 4 · Comprar 50 USD de crédito. Un reenvío no lo dobla.
    from types import SimpleNamespace

    from nexus_worker.billing.process_event import Skip, apply_credit_purchase

    checkout = SimpleNamespace(
        id=f"cs_{uuid.uuid4().hex[:10]}", payment_status="paid", amount_total=5_000
    )
    async with get_sessionmaker()() as s:
        await apply_credit_purchase(s, partner_id=pid, checkout=checkout)
        await s.execute(
            sa.text(
                "INSERT INTO billing_events (id, provider_event_id, event_type, "
                "checkout_session_id, status, payload) "
                "VALUES (:i, :e, 'checkout.session.completed', :c, 'processed', '{}'::jsonb)"
            ),
            {"i": str(uuid.uuid4()), "e": f"evt_{uuid.uuid4().hex[:10]}", "c": checkout.id},
        )
        await s.commit()
        with pytest.raises(Skip):
            await apply_credit_purchase(s, partner_id=pid, checkout=checkout)
    assert (
        await _q(
            "SELECT purchased_remaining FROM partner_wallets WHERE partner_id = :p", p=str(pid)
        )
    )[0] == 5_000_000

    # 5 · Gastar medio pool y subir a Team: se completa, no se reinicia.
    async with get_sessionmaker()() as s:
        await s.execute(
            sa.text("UPDATE partner_wallets SET included_remaining = 250000 WHERE partner_id = :p"),
            {"p": str(pid)},
        )
        await s.commit()
        await apply_tier_change(s, partner_id=pid, new_tier="team")
        await s.commit()
    wallet = await _q(
        "SELECT included_remaining, purchased_remaining FROM partner_wallets WHERE partner_id = :p",
        p=str(pid),
    )
    assert wallet[0] == 1_750_000, f"el pool quedó en {wallet[0]}"
    assert wallet[1] == 5_000_000, "subir de plan tocó el saldo comprado"

    # 6 · Falla el cobro. Nada desaparece.
    inventory_before = await _q(
        "SELECT (SELECT count(*) FROM teammates WHERE partner_id = :p AND status <> 'archived'), "
        "       (SELECT purchased_remaining FROM partner_wallets WHERE partner_id = :p)",
        p=str(pid),
    )
    async with get_sessionmaker()() as s:
        await move_to(s, partner_id=pid, state=STATE_PAYMENT_FAILED, notify=True)
        await s.commit()
    assert (
        await _q(
            "SELECT (SELECT count(*) FROM teammates WHERE partner_id = :p AND status <> 'archived'), "
            "       (SELECT purchased_remaining FROM partner_wallets WHERE partner_id = :p)",
            p=str(pid),
        )
    ) == inventory_before

    # 7 · Impagada. EL PASO QUE DECIDE.
    async with get_sessionmaker()() as s:
        await move_to(s, partner_id=pid, state=STATE_UNPAID, notify=True)
        await s.commit()

    # El pool deja de reponerse…
    async with get_sessionmaker()() as s:
        await s.execute(
            sa.text(
                "UPDATE partner_wallets SET included_remaining = 0, included_expires_at = :past "
                "WHERE partner_id = :p"
            ),
            {"past": datetime.now(UTC) - timedelta(days=1), "p": str(pid)},
        )
        await s.commit()
        assert await renew_included_if_expired(s, partner_id=pid) is False
        await s.commit()

    # …y todo lo demás sigue exactamente igual.
    assert (
        await _q(
            "SELECT (SELECT count(*) FROM teammates WHERE partner_id = :p AND status <> 'archived'), "
            "       (SELECT purchased_remaining FROM partner_wallets WHERE partner_id = :p)",
            p=str(pid),
        )
    ) == inventory_before, "al llegar a impagada se perdió algo. La feature NO está terminada"

    # 8 · Pagar: vuelve solo.
    async with get_sessionmaker()() as s:
        await grant_tier(s, partner_id=pid, tier_code="team")
        await s.commit()
    assert (await _q("SELECT state FROM partner_subscriptions WHERE partner_id = :p", p=str(pid)))[
        0
    ] == "current"
    async with get_sessionmaker()() as s:
        assert await renew_included_if_expired(s, partner_id=pid) is True
        await s.commit()

    # 9 · Cancelar: Free, y el saldo se conserva doce meses.
    async with get_sessionmaker()() as s:
        expires = await cancel_subscription(s, partner_id=pid)
        await s.commit()
    final = await _q(
        "SELECT purchased_remaining, purchased_expires_at FROM partner_wallets WHERE partner_id = :p",
        p=str(pid),
    )
    assert final[0] == 5_000_000, "cancelar se llevó el saldo comprado"
    assert 360 <= (expires - datetime.now(UTC)).days <= 370

    # 10 · El recibo es un extracto, no una factura.
    from nexus_api.services.partner_receipt import LINE_MODELS, receipt_kind

    assert receipt_kind() == "statement"
    assert {"membership", "consumption"} <= LINE_MODELS
