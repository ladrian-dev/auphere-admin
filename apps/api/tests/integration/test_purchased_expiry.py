"""Spec 005 · R7 — el crédito comprado sobrevive doce meses a la baja.

La invariante está escrita en el esquema y no en una condición: mientras la
cuenta vive, ``purchased_expires_at`` es **NULL**. Expresarla como ausencia de
fecha la hace imposible de violar por accidente — no hay nada que comparar, y
ningún cron puede equivocarse al decidir a quién le toca.

Y la caducidad, cuando llega, **deja asiento** — con una ``idempotency_key``
que la nombra, lo que además hace que el cron pueda correr cada día sin
duplicar nada: el segundo intento choca contra el UNIQUE que ya existía. Esto resta saldo, que es lo que
ADR-037 D3 prohíbe a los avisos externos; no lo contradice porque lo decide una
regla nuestra, con fecha nuestra, y queda apuntada. La diferencia es quién
decide, no si baja.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from nexus_api.billing.ladder import cancel_subscription, grant_tier
from nexus_api.db.base import get_sessionmaker

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _partner(purchased: int = 25_000) -> uuid.UUID:
    pid = uuid.uuid4()
    slug = f"exp-{pid.hex[:10]}"
    async with get_sessionmaker()() as s:
        await s.execute(
            sa.text("INSERT INTO partners (id, name, slug, status) VALUES (:i, :n, :s, 'active')"),
            {"i": str(pid), "n": slug, "s": slug},
        )
        await s.execute(
            sa.text(
                "INSERT INTO partner_subscriptions (partner_id, tier_code, state) "
                "VALUES (:p, 'pro', 'current')"
            ),
            {"p": str(pid)},
        )
        await s.execute(
            sa.text("UPDATE partner_wallets SET purchased_remaining = :q WHERE partner_id = :p"),
            {"q": purchased, "p": str(pid)},
        )
        await s.commit()
    return pid


async def _wallet(pid: uuid.UUID) -> tuple[int, datetime | None]:
    async with get_sessionmaker()() as s:
        row = (
            await s.execute(
                sa.text(
                    "SELECT purchased_remaining, purchased_expires_at "
                    "FROM partner_wallets WHERE partner_id = :p"
                ),
                {"p": str(pid)},
            )
        ).first()
    return int(row[0]), row[1]


# ── R7.1 · mientras la cuenta viva, no caduca ────────────────────────────────


async def test_a_live_account_has_no_expiry_at_all() -> None:
    """V43. Ni fecha lejana: ninguna."""
    pid = await _partner()
    balance, expires = await _wallet(pid)
    assert balance == 25_000
    assert expires is None, (
        "el crédito de una cuenta viva tiene fecha de caducidad. La invariante "
        "se expresa como ausencia precisamente para que no haya nada que "
        "comparar mal"
    )


async def test_a_year_passing_does_not_expire_a_live_account() -> None:
    from nexus_worker.billing.expire_credit_cron import expire_due_credit

    pid = await _partner()
    async with get_sessionmaker()() as s:
        expired = await expire_due_credit(s, now=datetime.now(UTC) + timedelta(days=400))
        await s.commit()
    assert pid not in {row["partner_id"] for row in expired}
    assert (await _wallet(pid))[0] == 25_000


# ── R7.2 · al cancelar, doce meses ───────────────────────────────────────────


async def test_cancelling_sets_the_expiry_twelve_months_out() -> None:
    """V44."""
    pid = await _partner()
    async with get_sessionmaker()() as s:
        await cancel_subscription(s, partner_id=pid)
        await s.commit()

    balance, expires = await _wallet(pid)
    assert balance == 25_000, "cancelar se llevó el saldo. Es dinero que el partner pagó"
    assert expires is not None
    days = (expires - datetime.now(UTC)).days
    assert 360 <= days <= 370, f"la caducidad quedó a {days} días, no a doce meses"


# ── R7.3 · volver dentro del plazo ───────────────────────────────────────────


async def test_coming_back_clears_the_expiry_with_nobody_restoring_anything() -> None:
    """V45. El partner que se va y vuelve a los ocho meses."""
    pid = await _partner()
    async with get_sessionmaker()() as s:
        await cancel_subscription(s, partner_id=pid)
        await s.commit()
    assert (await _wallet(pid))[1] is not None

    async with get_sessionmaker()() as s:
        await grant_tier(s, partner_id=pid, tier_code="pro")
        await s.commit()

    balance, expires = await _wallet(pid)
    assert expires is None, "reactivar dejó la fecha de caducidad puesta"
    assert balance == 25_000


# ── R7.5 · caducar deja rastro ───────────────────────────────────────────────


async def test_expiring_leaves_a_ledger_entry_saying_how_much_and_when() -> None:
    """V47. Una resta sin apunte es dinero que se movió sin explicación."""
    from nexus_worker.billing.expire_credit_cron import expire_due_credit

    pid = await _partner()
    async with get_sessionmaker()() as s:
        await cancel_subscription(s, partner_id=pid)
        await s.commit()

    later = datetime.now(UTC) + timedelta(days=400)
    async with get_sessionmaker()() as s:
        expired = await expire_due_credit(s, now=later)
        await s.commit()

    assert any(row["partner_id"] == pid for row in expired), f"no caducó: {expired}"
    assert (await _wallet(pid))[0] == 0

    async with get_sessionmaker()() as s:
        rows = (
            (
                await s.execute(
                    sa.text(
                        "SELECT qty, bucket, idempotency_key FROM usage_ledger "
                        "WHERE partner_id = :p AND idempotency_key LIKE 'credit_expired:%'"
                    ),
                    {"p": str(pid)},
                )
            )
            .mappings()
            .all()
        )
    assert rows, "la caducidad no dejó asiento en el libro"
    assert int(rows[0]["qty"]) == 25_000
    assert rows[0]["bucket"] == "purchased"


async def test_expiring_twice_does_not_double_the_entry() -> None:
    """El cron corre cada día; caducar es una vez."""
    from nexus_worker.billing.expire_credit_cron import expire_due_credit

    pid = await _partner()
    async with get_sessionmaker()() as s:
        await cancel_subscription(s, partner_id=pid)
        await s.commit()

    later = datetime.now(UTC) + timedelta(days=400)
    for _ in range(3):
        async with get_sessionmaker()() as s:
            await expire_due_credit(s, now=later)
            await s.commit()

    async with get_sessionmaker()() as s:
        count = await s.scalar(
            sa.text(
                "SELECT count(*) FROM usage_ledger "
                "WHERE partner_id = :p AND idempotency_key LIKE 'credit_expired:%'"
            ),
            {"p": str(pid)},
        )
    assert count == 1, f"el cron dejó {count} asientos de caducidad"


async def test_an_account_whose_time_has_not_come_is_left_alone() -> None:
    from nexus_worker.billing.expire_credit_cron import expire_due_credit

    pid = await _partner()
    async with get_sessionmaker()() as s:
        await cancel_subscription(s, partner_id=pid)
        await s.commit()

    async with get_sessionmaker()() as s:
        await expire_due_credit(s, now=datetime.now(UTC) + timedelta(days=200))
        await s.commit()
    assert (await _wallet(pid))[0] == 25_000
