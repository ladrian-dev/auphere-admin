"""Spec 005 · R1 — los topes limitan de verdad, y no archivan nada.

La mitad que cuesta más es la segunda. Impedir crear el teammate número tres
es fácil; lo que la constitución pide (§IV, «borrar no existe») es que bajar a
un nivel con menos plazas **no archive ninguno de los que ya hay**. Un partner
que baja de plan conserva lo suyo y pierde la capacidad de crear más — liberar
una plaza es su decisión, no nuestra.

Y R1.5: los topes son **datos**. Cambiarlos es un ``UPDATE``, sin desplegar.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from nexus_api.db.base import get_sessionmaker
from nexus_api.services.membership_limits import (
    TierLimitReached,
    assert_can_add_member,
    assert_can_add_teammate,
    effective_caps,
    over_cap_by,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _partner(session, *, tier: str | None = None) -> uuid.UUID:
    pid = uuid.uuid4()
    slug = f"lim-{pid.hex[:10]}"
    await session.execute(
        sa.text("INSERT INTO partners (id, name, slug, status) VALUES (:i, :n, :s, 'active')"),
        {"i": str(pid), "n": slug, "s": slug},
    )
    if tier is not None:
        await session.execute(
            sa.text(
                "INSERT INTO partner_subscriptions (partner_id, tier_code, state) "
                "VALUES (:p, :t, 'current')"
            ),
            {"p": str(pid), "t": tier},
        )
    await session.commit()
    return pid


async def _add_teammates(session, partner_id: uuid.UUID, count: int) -> None:
    for i in range(count):
        await session.execute(
            sa.text(
                "INSERT INTO teammates "
                "(id, partner_id, name, job, model, tool_names, permissions, "
                " local_exec, status, created_by) "
                "VALUES (:i, :p, :n, 'trabajo', 'openai/gpt-5.6-luna', '{}', "
                "'{}'::jsonb, false, 'active', 'test')"
            ),
            {"i": str(uuid.uuid4()), "p": str(partner_id), "n": f"tm{i}"},
        )
    await session.commit()


# ── R1.1 y R1.5 · los niveles son datos ──────────────────────────────────────


async def test_a_partner_without_a_subscription_row_is_free() -> None:
    """La ausencia es un estado válido y no hay que sembrar nada (§V)."""
    async with get_sessionmaker()() as s:
        pid = await _partner(s)
        caps = await effective_caps(s, pid)
        assert caps.tier_code == "free"
        assert caps.max_teammates == 0
        assert caps.max_members == 1


async def test_a_canceled_subscription_falls_back_to_free() -> None:
    async with get_sessionmaker()() as s:
        pid = await _partner(s, tier="business")
        await s.execute(
            sa.text("UPDATE partner_subscriptions SET state = 'canceled' WHERE partner_id = :p"),
            {"p": str(pid)},
        )
        await s.commit()
        caps = await effective_caps(s, pid)
        assert caps.tier_code == "free", "una cuenta cancelada conserva su nivel"


async def test_changing_a_cap_is_an_update_and_needs_no_deploy() -> None:
    """R1.5. Se cambia el dato y el efecto es inmediato."""
    async with get_sessionmaker()() as s:
        pid = await _partner(s, tier="pro")
        assert (await effective_caps(s, pid)).max_teammates == 2
        await s.execute(sa.text("UPDATE membership_tiers SET max_teammates = 5 WHERE code = 'pro'"))
        await s.commit()
        try:
            assert (await effective_caps(s, pid)).max_teammates == 5
        finally:
            await s.execute(
                sa.text("UPDATE membership_tiers SET max_teammates = 2 WHERE code = 'pro'")
            )
            await s.commit()


# ── R1.2 y R1.3 · el tope refuse, y dice cómo se sube ────────────────────────


async def test_the_teammate_above_the_cap_is_refused() -> None:
    async with get_sessionmaker()() as s:
        pid = await _partner(s, tier="pro")
        await _add_teammates(s, pid, 2)
        with pytest.raises(TierLimitReached) as exc:
            await assert_can_add_teammate(s, pid)
        assert exc.value.limit == 2
        assert exc.value.current == 2
        assert exc.value.tier_code == "pro"


async def test_refusing_archives_nothing() -> None:
    """Lo que de verdad se prueba aquí (§IV)."""
    async with get_sessionmaker()() as s:
        pid = await _partner(s, tier="pro")
        await _add_teammates(s, pid, 2)
        with pytest.raises(TierLimitReached):
            await assert_can_add_teammate(s, pid)
        alive = await s.scalar(
            sa.text(
                "SELECT count(*) FROM teammates WHERE partner_id = :p AND status <> 'archived'"
            ),
            {"p": str(pid)},
        )
        assert alive == 2, "se archivó un teammate para hacer sitio"


async def test_the_free_tier_admits_no_teammates_at_all() -> None:
    async with get_sessionmaker()() as s:
        pid = await _partner(s)
        with pytest.raises(TierLimitReached):
            await assert_can_add_teammate(s, pid)


async def test_a_member_above_the_cap_is_refused() -> None:
    async with get_sessionmaker()() as s:
        pid = await _partner(s, tier="pro")
        await s.execute(
            sa.text(
                "INSERT INTO partner_memberships "
                "(id, partner_id, user_id, email, role, status) "
                "VALUES (:i, :p, :u, :e, 'owner', 'active')"
            ),
            {
                "i": str(uuid.uuid4()),
                "p": str(pid),
                "u": str(uuid.uuid4()),
                "e": f"a-{pid.hex[:6]}@x.com",
            },
        )
        await s.commit()
        with pytest.raises(TierLimitReached) as exc:
            await assert_can_add_member(s, pid)
        assert exc.value.kind == "personas"


# ── R1.6 · bajar por debajo del uso ──────────────────────────────────────────


async def test_over_cap_reports_how_many_are_spare_without_touching_them() -> None:
    async with get_sessionmaker()() as s:
        pid = await _partner(s, tier="business")
        await _add_teammates(s, pid, 5)
        over = await over_cap_by(s, pid, "pro")
        assert over == {"teammates": 3}, over
        alive = await s.scalar(
            sa.text(
                "SELECT count(*) FROM teammates WHERE partner_id = :p AND status <> 'archived'"
            ),
            {"p": str(pid)},
        )
        assert alive == 5, "comprobar el tope archivó teammates"


async def test_a_tier_that_fits_reports_nothing() -> None:
    async with get_sessionmaker()() as s:
        pid = await _partner(s, tier="business")
        await _add_teammates(s, pid, 2)
        assert await over_cap_by(s, pid, "pro") == {}


# ── R1.7 · max_clients es independiente del plan ─────────────────────────────


async def test_granting_a_tier_does_not_touch_max_clients() -> None:
    """Acuerdo comercial: el número de clientes no depende del nivel."""
    async with get_sessionmaker()() as s:
        pid = await _partner(s)
        await s.execute(
            sa.text("UPDATE partners SET max_clients = 9 WHERE id = :p"), {"p": str(pid)}
        )
        await s.execute(
            sa.text(
                "INSERT INTO partner_subscriptions (partner_id, tier_code, state) "
                "VALUES (:p, 'business', 'current')"
            ),
            {"p": str(pid)},
        )
        await s.commit()
        value = await s.scalar(
            sa.text("SELECT max_clients FROM partners WHERE id = :p"), {"p": str(pid)}
        )
        assert value == 9, f"conceder un nivel cambió max_clients a {value}"
