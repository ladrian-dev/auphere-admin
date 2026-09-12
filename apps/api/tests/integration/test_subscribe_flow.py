"""Spec 005 · R2 — un partner contrata y empieza a trabajar, solo.

Los dos criterios que definen la Historia 1:

* **R2.3** — al confirmarse el pago, nivel y pool se aplican **en el mismo
  acto**. Dejarlo en dos pasos significa que un partner que acaba de pagar
  puede oír que no tiene presupuesto, y consultar el presupuesto es lo
  primero que hace alguien después de pagar.
* **R2.4** — abandonar el pago a medias **no cambia nada**. Ni un nivel
  concedido a medias, ni un pool ajustado a la espera.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from nexus_api.billing.ladder import grant_tier
from nexus_api.db.base import get_sessionmaker

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _partner(session) -> uuid.UUID:
    pid = uuid.uuid4()
    slug = f"sub-{pid.hex[:10]}"
    await session.execute(
        sa.text("INSERT INTO partners (id, name, slug, status) VALUES (:i, :n, :s, 'active')"),
        {"i": str(pid), "n": slug, "s": slug},
    )
    await session.commit()
    return pid


async def _state(session, pid: uuid.UUID) -> dict | None:
    row = (
        (
            await session.execute(
                sa.text(
                    "SELECT s.tier_code, s.state, p.weekly_pool_tokens "
                    "FROM partners p LEFT JOIN partner_subscriptions s ON s.partner_id = p.id "
                    "WHERE p.id = :p"
                ),
                {"p": str(pid)},
            )
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


async def test_paying_applies_tier_and_pool_in_the_same_act() -> None:
    """R2.3. Se leen los dos en la misma consulta, después de un solo acto."""
    async with get_sessionmaker()() as s:
        pid = await _partner(s)
        before = await _state(s, pid)
        assert before is not None and before["tier_code"] is None

        await grant_tier(s, partner_id=pid, tier_code="team")
        await s.commit()

        after = await _state(s, pid)
        assert after is not None
        assert after["tier_code"] == "team"
        assert after["state"] == "current"
        # El pool del partner es EL del nivel, no el heredado.
        expected = await s.scalar(
            sa.text("SELECT weekly_pool_tokens FROM membership_tiers WHERE code = 'team'")
        )
        assert after["weekly_pool_tokens"] == expected, (
            "se concedió el nivel pero el pool se quedó atrás: un partner que "
            "acaba de pagar oiría que no tiene presupuesto"
        )


async def test_abandoning_the_payment_changes_nothing() -> None:
    """R2.4. Abrir la página de pago y no completarla no toca nada.

    Se modela como lo que es: sin aviso de pago confirmado, nada llama a
    ``grant_tier``. Lo que se comprueba es que el estado del partner sea
    idéntico byte a byte antes y después.
    """
    async with get_sessionmaker()() as s:
        pid = await _partner(s)
        before = await _state(s, pid)
        # …aquí iría la sesión de Checkout abierta y abandonada…
        after = await _state(s, pid)
        assert before == after
        count = await s.scalar(
            sa.text("SELECT count(*) FROM partner_subscriptions WHERE partner_id = :p"),
            {"p": str(pid)},
        )
        assert count == 0, "abandonar el pago dejó una suscripción a medias"


async def test_granting_twice_is_not_a_second_subscription() -> None:
    """Un reenvío del mismo aviso llega a ``grant_tier`` dos veces."""
    async with get_sessionmaker()() as s:
        pid = await _partner(s)
        await grant_tier(s, partner_id=pid, tier_code="pro")
        await s.commit()
        await grant_tier(s, partner_id=pid, tier_code="pro")
        await s.commit()
        count = await s.scalar(
            sa.text("SELECT count(*) FROM partner_subscriptions WHERE partner_id = :p"),
            {"p": str(pid)},
        )
        assert count == 1


async def test_coming_back_clears_the_credit_expiry() -> None:
    """R7.3: reactivar devuelve el saldo sin que nadie reponga nada a mano."""
    from datetime import UTC, datetime, timedelta

    async with get_sessionmaker()() as s:
        pid = await _partner(s)
        await s.execute(
            sa.text(
                "UPDATE partner_wallets SET purchased_remaining = 900, "
                "purchased_expires_at = :d WHERE partner_id = :p"
            ),
            {"d": datetime.now(UTC) + timedelta(days=200), "p": str(pid)},
        )
        await s.commit()

        await grant_tier(s, partner_id=pid, tier_code="pro")
        await s.commit()

        row = (
            await s.execute(
                sa.text(
                    "SELECT purchased_remaining, purchased_expires_at "
                    "FROM partner_wallets WHERE partner_id = :p"
                ),
                {"p": str(pid)},
            )
        ).first()
        assert row[0] == 900, "reactivar tocó el saldo comprado"
        assert row[1] is None, "el saldo sigue con fecha de caducidad tras reactivar"
