"""Spec 005 · R6 — cambiar de plan sin perder nada de lo ya pagado.

El reparto de trabajo con el proveedor es deliberado y conviene leerlo antes
que el código:

* **El prorrateo del dinero lo hace Stripe.** Subir modifica la suscripción con
  `proration_behavior='create_prorations'` y bajar programa el cambio con un
  *Subscription Schedule* y `proration_behavior='none'`. Calcular nosotros los
  días restantes de un ciclo sería reimplementar —peor— algo que el proveedor
  ya hace bien, y que además tiene que coincidir con lo que aparece en la
  factura del cliente.
* **El pool lo completamos nosotros**, porque es nuestro libro y el proveedor
  no sabe qué es.

Subir es inmediato porque el momento en que alguien sube de plan es
justamente cuando se ha quedado sin pool: hacerle esperar al siguiente ciclo
es cobrarle por algo que no puede usar todavía.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from nexus_api.billing.ladder import grant_tier
from nexus_api.db.base import get_sessionmaker
from nexus_api.metering.wallet import apply_tier_change

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _partner(tier: str = "pro", *, spent: int = 0, purchased: int = 7_000) -> uuid.UUID:
    pid = uuid.uuid4()
    slug = f"chg-{pid.hex[:10]}"
    async with get_sessionmaker()() as s:
        await s.execute(
            sa.text("INSERT INTO partners (id, name, slug, status) VALUES (:i, :n, :s, 'active')"),
            {"i": str(pid), "n": slug, "s": slug},
        )
        await s.commit()
        await grant_tier(s, partner_id=pid, tier_code=tier)
        await s.commit()
        size = await s.scalar(
            sa.text("SELECT weekly_pool_tokens FROM membership_tiers WHERE code = :c"),
            {"c": tier},
        )
        await s.execute(
            sa.text(
                "UPDATE partner_wallets SET included_remaining = :r, "
                "purchased_remaining = :p, included_expires_at = :e WHERE partner_id = :pid"
            ),
            {
                "r": int(size) - spent,
                "p": purchased,
                "e": datetime.now(UTC) + timedelta(days=4),
                "pid": str(pid),
            },
        )
        await s.commit()
    return pid


async def _wallet(pid: uuid.UUID) -> tuple[int, int]:
    async with get_sessionmaker()() as s:
        row = (
            await s.execute(
                sa.text(
                    "SELECT included_remaining, purchased_remaining "
                    "FROM partner_wallets WHERE partner_id = :p"
                ),
                {"p": str(pid)},
            )
        ).first()
    return int(row[0]), int(row[1])


async def _tier(pid: uuid.UUID) -> tuple[str, str | None]:
    async with get_sessionmaker()() as s:
        row = (
            await s.execute(
                sa.text(
                    "SELECT tier_code, pending_tier_code FROM partner_subscriptions "
                    "WHERE partner_id = :p"
                ),
                {"p": str(pid)},
            )
        ).first()
    return row[0], row[1]


# ── R6.1 y R6.2 · subir ──────────────────────────────────────────────────────


async def test_upgrading_tops_the_pool_up_in_the_same_act() -> None:
    """V38 y V39. Con 100 000 gastados de 500 000, subir a Team deja 1 900 000."""
    pid = await _partner("pro", spent=100_000)
    async with get_sessionmaker()() as s:
        await apply_tier_change(s, partner_id=pid, new_tier="team")
        await s.commit()

    included, _ = await _wallet(pid)
    # Pro 500 000 → Team 2 000 000. Gastados 100 000, así que 400 000 + 1 500 000.
    assert included == 1_900_000, (
        f"el pool quedó en {included}. Ni 2 000 000 (regalaría lo consumido) "
        "ni 400 000 (cobraría el nivel sin darlo)"
    )
    assert (await _tier(pid))[0] == "team"


async def test_the_new_pool_is_usable_right_away() -> None:
    """R6.1: inmediato. Quien sube lo hace porque se quedó sin pool."""
    pid = await _partner("pro", spent=500_000)
    assert (await _wallet(pid))[0] == 0
    async with get_sessionmaker()() as s:
        await apply_tier_change(s, partner_id=pid, new_tier="business")
        await s.commit()
    assert (await _wallet(pid))[0] > 0


# ── R6.3 · bajar ─────────────────────────────────────────────────────────────


async def test_downgrading_is_scheduled_and_does_not_reclaim_the_pool() -> None:
    """V40. Se anota como pendiente; el pool del ciclo en curso no se toca."""
    pid = await _partner("business", spent=1_000_000)
    before, _ = await _wallet(pid)
    async with get_sessionmaker()() as s:
        await apply_tier_change(s, partner_id=pid, new_tier="pro")
        await s.commit()

    current, pending = await _tier(pid)
    assert current == "business", "la bajada se aplicó de inmediato"
    assert pending == "pro", "la bajada no quedó anotada como pendiente"
    assert (await _wallet(pid))[0] == before, "se reclamó pool que el partner ya pagó"


async def test_a_second_downgrade_replaces_the_first() -> None:
    """Cambiar de opinión antes de que se aplique no deja dos pendientes."""
    pid = await _partner("business")
    async with get_sessionmaker()() as s:
        await apply_tier_change(s, partner_id=pid, new_tier="pro")
        await s.commit()
        await apply_tier_change(s, partner_id=pid, new_tier="team")
        await s.commit()
    assert (await _tier(pid))[1] == "team"


async def test_upgrading_clears_a_pending_downgrade() -> None:
    """Quien sube ya no quiere bajar."""
    pid = await _partner("team")
    async with get_sessionmaker()() as s:
        await apply_tier_change(s, partner_id=pid, new_tier="pro")
        await s.commit()
        await apply_tier_change(s, partner_id=pid, new_tier="business")
        await s.commit()
    current, pending = await _tier(pid)
    assert current == "business"
    assert pending is None


# ── R6.4 · el saldo comprado no se toca ──────────────────────────────────────


@pytest.mark.parametrize(
    ("start", "target"),
    [("pro", "team"), ("team", "pro"), ("pro", "business"), ("business", "pro")],
)
async def test_no_plan_change_touches_purchased_credit(start: str, target: str) -> None:
    """V41. Las cuatro transiciones. Es dinero pagado, no es del plan."""
    pid = await _partner(start, purchased=7_000)
    async with get_sessionmaker()() as s:
        await apply_tier_change(s, partner_id=pid, new_tier=target)
        await s.commit()
    assert (await _wallet(pid))[1] == 7_000, f"{start} → {target} tocó el saldo comprado"


# ── R6.5 · el caso límite ────────────────────────────────────────────────────


async def test_an_upgrade_landing_on_the_refill_leaves_the_new_size_exactly() -> None:
    """V42. Ni duplicado ni a cero.

    Se fuerza el peor orden: el ciclo caduca y se repone al tamaño VIEJO, y en
    ese mismo instante entra la subida.
    """
    from nexus_api.metering.wallet import renew_included_if_expired

    pid = await _partner("pro", spent=500_000)
    async with get_sessionmaker()() as s:
        await s.execute(
            sa.text("UPDATE partner_wallets SET included_expires_at = :past WHERE partner_id = :p"),
            {"past": datetime.now(UTC) - timedelta(seconds=1), "p": str(pid)},
        )
        await s.commit()
        await renew_included_if_expired(s, partner_id=pid)
        await s.commit()
        assert (await _wallet(pid))[0] == 500_000

        await apply_tier_change(s, partner_id=pid, new_tier="team")
        await s.commit()

    included, _ = await _wallet(pid)
    assert included == 2_000_000, f"el pool quedó en {included}, no en el tamaño nuevo"
