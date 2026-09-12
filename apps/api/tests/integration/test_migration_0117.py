"""Spec 005 · el registro de avisos y la caducidad del saldo (migración 0117).

Dos piezas que parecen administrativas y no lo son:

* ``billing_events.provider_event_id`` es **UNIQUE**, y esa restricción *es* la
  idempotencia. El quinto reenvío del mismo pago choca contra ella y no
  acredita nada. Sin UNIQUE, la idempotencia se convierte en un ``SELECT``
  seguido de un ``INSERT``, que dos entregas simultáneas se saltan.
* ``billing_events.partner_id`` **no tiene FK**, también a propósito: un aviso
  de dinero de una cuenta que no reconocemos tiene que poder registrarse igual.
  Perder el rastro de un pago por una restricción de integridad es peor que
  tener una fila huérfana.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from nexus_api.db.base import get_sessionmaker

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_billing_events_exists_with_its_shape() -> None:
    async with get_sessionmaker()() as s:
        conn = await s.connection()
        cols = {
            r[0]: (r[1], r[2])
            for r in (
                await conn.execute(
                    sa.text(
                        "SELECT column_name, data_type, is_nullable "
                        "FROM information_schema.columns WHERE table_name = 'billing_events'"
                    )
                )
            ).all()
        }
        assert cols, "la tabla billing_events no existe"
        for name in (
            "id",
            "provider_event_id",
            "event_type",
            "checkout_session_id",
            "partner_id",
            "status",
            "payload",
            "error",
            "received_at",
            "processed_at",
        ):
            assert name in cols, f"falta la columna {name}"
        assert cols["payload"][0] == "jsonb"
        assert cols["partner_id"][1] == "YES", "partner_id debe admitir NULL"


async def test_provider_event_id_is_unique() -> None:
    """La idempotencia es esta restricción, no un SELECT previo."""
    async with get_sessionmaker()() as s:
        await s.execute(
            sa.text(
                "INSERT INTO billing_events (id, provider_event_id, event_type, status, payload) "
                "VALUES (:i, 'evt_dup', 'invoice.paid', 'received', '{}'::jsonb)"
            ),
            {"i": str(uuid.uuid4())},
        )
        with pytest.raises(IntegrityError):
            await s.execute(
                sa.text(
                    "INSERT INTO billing_events (id, provider_event_id, event_type, status, payload) "
                    "VALUES (:i, 'evt_dup', 'invoice.paid', 'received', '{}'::jsonb)"
                ),
                {"i": str(uuid.uuid4())},
            )
        await s.rollback()


async def test_an_event_from_an_unknown_account_can_still_be_recorded() -> None:
    """``partner_id`` sin FK: el rastro de un aviso de dinero no se pierde."""
    async with get_sessionmaker()() as s:
        await s.execute(
            sa.text(
                "INSERT INTO billing_events "
                "(id, provider_event_id, event_type, status, payload, partner_id) "
                "VALUES (:i, :e, 'invoice.paid', 'received', '{}'::jsonb, :p)"
            ),
            {"i": str(uuid.uuid4()), "e": f"evt_{uuid.uuid4().hex[:8]}", "p": str(uuid.uuid4())},
        )
        await s.rollback()


async def test_purchased_expires_at_exists_and_is_null_by_default() -> None:
    """La invariante de research D8, en el esquema.

    ``NULL`` mientras la cuenta viva. Expresada así **no se puede violar por
    accidente**: no hay fecha que comparar. Un DEFAULT con fecha convertiría
    «no caduca» en «caduca pronto» para todo el mundo a la vez.
    """
    async with get_sessionmaker()() as s:
        conn = await s.connection()
        row = (
            await conn.execute(
                sa.text(
                    "SELECT data_type, is_nullable, column_default "
                    "FROM information_schema.columns "
                    "WHERE table_name = 'partner_wallets' "
                    "AND column_name = 'purchased_expires_at'"
                )
            )
        ).first()
        assert row is not None, "falta partner_wallets.purchased_expires_at"
        assert row[0] == "timestamp with time zone"
        assert row[1] == "YES"
        assert row[2] is None, (
            "la columna tiene un DEFAULT: el crédito comprado no caduca mientras "
            "la cuenta viva, y un valor de fábrica pondría fecha a todo el mundo"
        )


async def test_checkout_session_index_exists() -> None:
    """La segunda ancla de idempotencia: dos eventos distintos, una compra."""
    async with get_sessionmaker()() as s:
        conn = await s.connection()
        names = {
            r[0]
            for r in (
                await conn.execute(
                    sa.text("SELECT indexname FROM pg_indexes WHERE tablename = 'billing_events'")
                )
            ).all()
        }
        assert any("checkout_session" in n for n in names), (
            f"no hay índice sobre checkout_session_id; índices: {sorted(names)}"
        )
