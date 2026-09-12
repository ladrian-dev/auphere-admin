"""Spec 005 · `DELETE /console/billing/subscription` — cancelar sin perder nada.

Lo que una cancelación **dice** importa tanto como lo que hace. Un partner que
cancela quiere saber dos cosas ahora mismo: qué pasa con el dinero que ya
puso, y hasta cuándo. Si la pantalla no lo dice, lo pregunta por soporte — y
mientras tanto cree que lo ha perdido.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from nexus_api.db.base import get_sessionmaker

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_PATH = "/console/billing/subscription"


async def _seed_credit(partner_id, qty: int = 30_000) -> None:
    async with get_sessionmaker()() as s:
        await s.execute(
            sa.text("UPDATE partner_wallets SET purchased_remaining = :q WHERE partner_id = :p"),
            {"q": qty, "p": str(partner_id)},
        )
        await s.commit()


async def test_cancelling_says_how_much_credit_is_kept_and_until_when(
    client, console_world
) -> None:
    """V46. Los dos datos que el partner necesita en ese momento."""
    a = console_world["a"]
    await _seed_credit(a["partner_id"])

    resp = await client.delete(_PATH, headers=a["headers"]())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["purchased_remaining"] == 30_000
    assert body["purchased_expires_at"], "no dice hasta cuándo conserva el saldo"


async def test_cancelling_archives_nothing(client, console_world) -> None:
    a = console_world["a"]
    async with get_sessionmaker()() as s:
        before = await s.scalar(
            sa.text(
                "SELECT count(*) FROM teammates WHERE partner_id = :p AND status <> 'archived'"
            ),
            {"p": str(a["partner_id"])},
        )
    await client.delete(_PATH, headers=a["headers"]())
    async with get_sessionmaker()() as s:
        after = await s.scalar(
            sa.text(
                "SELECT count(*) FROM teammates WHERE partner_id = :p AND status <> 'archived'"
            ),
            {"p": str(a["partner_id"])},
        )
    assert after == before


async def test_cancelling_twice_is_not_an_error(client, console_world) -> None:
    """Alguien que pulsa dos veces no merece un error rojo."""
    a = console_world["a"]
    first = await client.delete(_PATH, headers=a["headers"]())
    second = await client.delete(_PATH, headers=a["headers"]())
    assert first.status_code == 200
    assert second.status_code == 200


async def test_cancelling_leaves_an_audit_row_naming_the_person(client, console_world) -> None:
    """§IV. Cancelar es una acción consecuente de alguien."""
    a = console_world["a"]
    await client.delete(_PATH, headers=a["headers"]())
    async with get_sessionmaker()() as s:
        rows = (
            await s.execute(
                sa.text(
                    "SELECT actor FROM audit_log WHERE action = 'console.billing.canceled' "
                    "AND target = :t"
                ),
                {"t": f"partner:{a['partner_id']}"},
            )
        ).all()
    assert rows, "cancelar no dejó rastro"
    assert rows[0][0] and rows[0][0] not in {"system", "webhook", "stripe"}


async def test_without_a_token_nobody_cancels(client) -> None:
    resp = await client.delete(_PATH)
    assert resp.status_code == 401
