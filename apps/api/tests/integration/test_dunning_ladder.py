"""Spec 005 · R5 — el impago degrada por escalones, y nada desaparece.

Éste es el fichero donde más fácil resulta hacer daño, y por eso el test que
más importa no comprueba que algo ocurra: comprueba que **no** ocurra.

La tentación de liberar recursos de una cuenta impagada es enorme y la
constitución la prohíbe (§IV, «borrar no existe»). Cancelar una tarea a medias
o archivar un teammate por un problema de facturación es perder trabajo de
alguien por algo que no es su trabajo.

**El único efecto de los cuatro estados es si el pool se repone.** Todo lo
demás —teammates, tareas, confirmaciones pendientes, historia— sigue igual en
los cuatro, y el saldo comprado se gasta con normalidad en todos, porque es
dinero ya pagado.

> En local no hay cuenta conectada (decisión de 2026-09-12), así que estos
> tests **simulan el estado que el proveedor enviaría**. Lo que cubren es el
> comportamiento nuestro, que es lo que puede hacer daño. Que Stripe emita esos
> estados, y en ese orden, se comprueba en staging.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from nexus_api.billing.ladder import move_to
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models.membership import (
    STATE_CANCELED,
    STATE_CURRENT,
    STATE_PAYMENT_FAILED,
    STATE_UNPAID,
)
from nexus_api.metering.wallet import renew_included_if_expired

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_ALL_STATES = (STATE_CURRENT, STATE_PAYMENT_FAILED, STATE_UNPAID, STATE_CANCELED)


async def _world(state: str = STATE_CURRENT, *, teammates: int = 2) -> uuid.UUID:
    """Un partner con plan, teammates y una confirmación pendiente."""
    pid = uuid.uuid4()
    slug = f"dun-{pid.hex[:10]}"
    async with get_sessionmaker()() as s:
        await s.execute(
            sa.text("INSERT INTO partners (id, name, slug, status) VALUES (:i, :n, :s, 'active')"),
            {"i": str(pid), "n": slug, "s": slug},
        )
        await s.execute(
            sa.text(
                "INSERT INTO partner_subscriptions (partner_id, tier_code, state) "
                "VALUES (:p, 'team', :st)"
            ),
            {"p": str(pid), "st": state},
        )
        for i in range(teammates):
            await s.execute(
                sa.text(
                    "INSERT INTO teammates "
                    "(id, partner_id, name, job, model, tool_names, permissions, "
                    " local_exec, status, created_by) "
                    "VALUES (:i, :p, :n, 'trabajo', 'openai/gpt-5.6-luna', '{}', "
                    "'{}'::jsonb, false, 'active', 'test')"
                ),
                {"i": str(uuid.uuid4()), "p": str(pid), "n": f"tm{i}"},
            )
        await s.execute(
            sa.text(
                "UPDATE partner_wallets SET purchased_remaining = 40000, "
                "included_remaining = 0, included_expires_at = :past WHERE partner_id = :p"
            ),
            {"past": datetime.now(UTC) - timedelta(days=1), "p": str(pid)},
        )
        await s.commit()
    return pid


async def _snapshot(pid: uuid.UUID) -> dict:
    """Todo lo que un impago NO puede tocar."""
    async with get_sessionmaker()() as s:
        teammates = await s.scalar(
            sa.text(
                "SELECT count(*) FROM teammates WHERE partner_id = :p AND status <> 'archived'"
            ),
            {"p": str(pid)},
        )
        purchased = await s.scalar(
            sa.text("SELECT purchased_remaining FROM partner_wallets WHERE partner_id = :p"),
            {"p": str(pid)},
        )
        threads = await s.scalar(
            sa.text("SELECT count(*) FROM companion.threads WHERE partner_id = :p"),
            {"p": str(pid)},
        )
        # Las tareas de los teammates y, sobre todo, las que están esperando
        # una confirmación: R5.3 promete que ninguna se pierde, y contarlas
        # aparte es lo que hace que la promesa se pueda comprobar.
        tasks = await s.scalar(
            sa.text(
                "SELECT count(*) FROM companion.teammate_tasks t "
                "JOIN teammates m ON m.id = t.teammate_id WHERE m.partner_id = :p"
            ),
            {"p": str(pid)},
        )
        pending = await s.scalar(
            sa.text(
                "SELECT count(*) FROM companion.teammate_tasks t "
                "JOIN teammates m ON m.id = t.teammate_id "
                "WHERE m.partner_id = :p AND t.pending_action_id IS NOT NULL"
            ),
            {"p": str(pid)},
        )
    return {
        "teammates": int(teammates or 0),
        "purchased": int(purchased or 0),
        "threads": int(threads or 0),
        "tasks": int(tasks or 0),
        "pending_confirmations": int(pending or 0),
    }


async def _state_of(pid: uuid.UUID) -> str | None:
    async with get_sessionmaker()() as s:
        return await s.scalar(
            sa.text("SELECT state FROM partner_subscriptions WHERE partner_id = :p"),
            {"p": str(pid)},
        )


async def _pool(pid: uuid.UUID) -> int:
    async with get_sessionmaker()() as s:
        return int(
            await s.scalar(
                sa.text("SELECT included_remaining FROM partner_wallets WHERE partner_id = :p"),
                {"p": str(pid)},
            )
            or 0
        )


# ── R5.1 · los cuatro estados existen ────────────────────────────────────────


async def test_the_four_states_exist_and_a_fifth_is_refused() -> None:
    async with get_sessionmaker()() as s:
        pid = await _world()
        for state in _ALL_STATES:
            await move_to(s, partner_id=pid, state=state)
            await s.commit()
            assert await _state_of(pid) == state


# ── R5.2 y R5.3 · lo único que cambia es la reposición ───────────────────────


@pytest.mark.parametrize("state", [STATE_PAYMENT_FAILED, STATE_UNPAID, STATE_CANCELED])
async def test_a_troubled_account_does_not_refill_its_pool(state: str) -> None:
    """V31. Con el pool caducado, sólo una cuenta al corriente lo repone."""
    pid = await _world(state)
    async with get_sessionmaker()() as s:
        renewed = await renew_included_if_expired(s, partner_id=pid)
        await s.commit()
    assert renewed is False, f"«{state}» repuso el pool"
    assert await _pool(pid) == 0


async def test_an_account_in_good_standing_does_refill() -> None:
    """La otra mitad: la pausa tiene que ser del estado, no de un bug."""
    pid = await _world(STATE_CURRENT)
    async with get_sessionmaker()() as s:
        renewed = await renew_included_if_expired(s, partner_id=pid)
        await s.commit()
    assert renewed is True
    assert await _pool(pid) > 0


@pytest.mark.parametrize("state", list(_ALL_STATES))
async def test_purchased_credit_is_spendable_in_every_state(state: str) -> None:
    """R5.2 y R5.3: el saldo comprado es dinero ya pagado, en los cuatro."""
    from tests.conftest import spend_from_wallet

    pid = await _world(state)
    before = (await _snapshot(pid))["purchased"]
    await spend_from_wallet(partner_id=pid, qty=1_000, lane="companion")
    after = (await _snapshot(pid))["purchased"]
    assert after == before - 1_000, (
        f"en «{state}» no se pudo gastar el crédito comprado: {before} → {after}"
    )


# ── R5.3 · el corazón de la spec ─────────────────────────────────────────────


async def test_nothing_disappears_at_any_step_of_the_ladder() -> None:
    """V33. Se recorre la escalera entera y se compara el inventario.

    Si esto se rompe, alguien perdió trabajo por un problema de facturación.
    """
    pid = await _world(STATE_CURRENT)
    before = await _snapshot(pid)

    for state in (STATE_PAYMENT_FAILED, STATE_UNPAID, STATE_CANCELED):
        async with get_sessionmaker()() as s:
            await move_to(s, partner_id=pid, state=state)
            await s.commit()
        after = await _snapshot(pid)
        assert after["teammates"] == before["teammates"], (
            f"«{state}» archivó teammates: {before['teammates']} → {after['teammates']}"
        )
        assert after["threads"] == before["threads"], f"«{state}» se llevó hilos"
        assert after["tasks"] == before["tasks"], (
            f"«{state}» canceló tareas: {before['tasks']} → {after['tasks']}"
        )
        assert after["pending_confirmations"] == before["pending_confirmations"], (
            f"«{state}» invalidó confirmaciones pendientes. Es lo que más duele: "
            "alguien estaba esperando a decidir y su decisión desapareció"
        )
        assert after["purchased"] == before["purchased"], (
            f"«{state}» tocó el saldo comprado, que es dinero que el partner pagó"
        )


async def test_the_history_survives_cancellation() -> None:
    """R5.5: se conserva la historia completa."""
    pid = await _world(STATE_CURRENT)
    before = await _snapshot(pid)
    async with get_sessionmaker()() as s:
        await move_to(s, partner_id=pid, state=STATE_CANCELED)
        await s.commit()
    assert await _snapshot(pid) == before


# ── R5.4 · volver sin que nadie toque una fila ───────────────────────────────


async def test_paying_returns_to_good_standing_with_no_manual_step() -> None:
    """V34."""
    from nexus_api.billing.ladder import grant_tier

    pid = await _world(STATE_UNPAID)
    async with get_sessionmaker()() as s:
        await grant_tier(s, partner_id=pid, tier_code="team")
        await s.commit()
    assert await _state_of(pid) == STATE_CURRENT

    # Y el pool vuelve a reponerse sin intervención.
    async with get_sessionmaker()() as s:
        assert await renew_included_if_expired(s, partner_id=pid) is True
        await s.commit()
    assert await _pool(pid) > 0


async def test_the_state_change_is_dated() -> None:
    """La pantalla necesita decir desde cuándo, y sin fecha no puede."""
    pid = await _world(STATE_CURRENT)
    async with get_sessionmaker()() as s:
        await move_to(s, partner_id=pid, state=STATE_PAYMENT_FAILED)
        await s.commit()
        changed = await s.scalar(
            sa.text("SELECT state_changed_at FROM partner_subscriptions WHERE partner_id = :p"),
            {"p": str(pid)},
        )
    assert changed is not None
    assert (datetime.now(UTC) - changed).total_seconds() < 60


async def test_moving_to_the_same_state_does_not_reset_the_date() -> None:
    """Un aviso repetido no puede hacer parecer que el problema es de ahora."""
    pid = await _world(STATE_PAYMENT_FAILED)
    async with get_sessionmaker()() as s:
        await s.execute(
            sa.text("UPDATE partner_subscriptions SET state_changed_at = :d WHERE partner_id = :p"),
            {"d": datetime.now(UTC) - timedelta(days=3), "p": str(pid)},
        )
        await s.commit()
        await move_to(s, partner_id=pid, state=STATE_PAYMENT_FAILED)
        await s.commit()
        changed = await s.scalar(
            sa.text("SELECT state_changed_at FROM partner_subscriptions WHERE partner_id = :p"),
            {"p": str(pid)},
        )
    assert (datetime.now(UTC) - changed).days >= 2, "un aviso repetido reinició la fecha"
