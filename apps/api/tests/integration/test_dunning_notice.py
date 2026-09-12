"""Spec 005 · R5.6 — se avisa ANTES de que el servicio se degrade.

El orden importa más que el aviso. Enterarse de que la tarjeta falló **después**
de que los agentes dejen de reponerse convierte un problema administrativo en
una sorpresa operativa: el partner descubre el impago porque algo dejó de
funcionar, no porque se lo dijimos.

Por eso el primer escalón —«pago fallido»— **no degrada nada**. Existe
exactamente para eso: para que haya una ventana entre el aviso y el efecto.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from nexus_api.billing.ladder import move_to
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models.membership import STATE_PAYMENT_FAILED, STATE_UNPAID
from nexus_api.metering.wallet import renew_included_if_expired

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _partner() -> uuid.UUID:
    pid = uuid.uuid4()
    slug = f"not-{pid.hex[:10]}"
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
        await s.commit()
    return pid


async def _notices(pid: uuid.UUID) -> list[dict]:
    async with get_sessionmaker()() as s:
        rows = (
            (
                await s.execute(
                    sa.text(
                        "SELECT kind, severity, payload, created_at FROM console_notifications "
                        "WHERE partner_id = :p ORDER BY created_at"
                    ),
                    {"p": str(pid)},
                )
            )
            .mappings()
            .all()
        )
    return [dict(r) for r in rows]


async def test_a_failed_payment_notifies_the_partner() -> None:
    pid = await _partner()
    async with get_sessionmaker()() as s:
        await move_to(s, partner_id=pid, state=STATE_PAYMENT_FAILED, notify=True)
        await s.commit()
    kinds = {n["kind"] for n in await _notices(pid)}
    assert "billing.payment_failed" in kinds, f"no se avisó: {kinds}"


async def test_the_notice_lands_before_anything_degrades() -> None:
    """El orden, que es lo que el criterio pide.

    En «pago fallido» el aviso ya está y el pool **todavía se repondría** si
    caducara — porque en ese escalón no se ha degradado nada. Sólo el escalón
    siguiente pausa.
    """
    pid = await _partner()
    async with get_sessionmaker()() as s:
        await move_to(s, partner_id=pid, state=STATE_PAYMENT_FAILED, notify=True)
        await s.commit()

    assert await _notices(pid), "el aviso no salió en el primer escalón"

    # Y aquí está la ventana: el partner ya lo sabe, y todavía no le pasa nada.
    async with get_sessionmaker()() as s:
        await s.execute(
            sa.text(
                "UPDATE partner_wallets SET included_remaining = 0, "
                "included_expires_at = :past WHERE partner_id = :p"
            ),
            {"past": datetime.now(UTC) - timedelta(days=1), "p": str(pid)},
        )
        await s.commit()

    async with get_sessionmaker()() as s:
        paused = await renew_included_if_expired(s, partner_id=pid)
        await s.commit()
    assert paused is False, "el primer escalón ya degradaba: no hay ventana de aviso"


async def test_the_notice_says_what_fixes_it() -> None:
    """Un aviso que no dice qué hacer es una alarma, no una ayuda."""
    pid = await _partner()
    async with get_sessionmaker()() as s:
        await move_to(s, partner_id=pid, state=STATE_PAYMENT_FAILED, notify=True)
        await s.commit()
    notice = (await _notices(pid))[0]
    assert notice["severity"] in {"warning", "critical"}
    assert "state" in (notice["payload"] or {})


async def test_the_same_step_does_not_notify_twice() -> None:
    """Stripe reintenta varias veces; el partner recibe un aviso, no cinco."""
    pid = await _partner()
    for _ in range(3):
        async with get_sessionmaker()() as s:
            await move_to(s, partner_id=pid, state=STATE_PAYMENT_FAILED, notify=True)
            await s.commit()
    assert len(await _notices(pid)) == 1


async def test_reaching_the_unpaid_step_notifies_again() -> None:
    """Un escalón nuevo sí es noticia: ahora sí cambia algo."""
    pid = await _partner()
    async with get_sessionmaker()() as s:
        await move_to(s, partner_id=pid, state=STATE_PAYMENT_FAILED, notify=True)
        await s.commit()
    async with get_sessionmaker()() as s:
        await move_to(s, partner_id=pid, state=STATE_UNPAID, notify=True)
        await s.commit()
    kinds = [n["kind"] for n in await _notices(pid)]
    assert kinds == ["billing.payment_failed", "billing.unpaid"], kinds
