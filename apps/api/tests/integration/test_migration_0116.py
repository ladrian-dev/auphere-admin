"""Spec 005 · el esquema de los niveles y de la suscripción (migración 0116).

Integración y no unidad porque lo que se comprueba es el esquema real: los
CHECK, la RLS y las filas sembradas sólo existen en Postgres. Un test de
unidad sobre el modelo SQLAlchemy diría que todo está bien con una base que
no tiene ninguna de las tres cosas.

Lo que más se vigila aquí no es que las columnas existan, sino **que
``stripe_price_id`` NO sea clave de nada** (research D5.1). Una restricción
UNIQUE o una FK sobre un identificador del proveedor convertiría el cambio de
cuenta de Stripe —que va a ocurrir— en una reconstrucción.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from nexus_api.db.base import get_sessionmaker

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_TIERS = ("free", "pro", "team", "business")


async def _columns(conn: sa.ext.asyncio.AsyncConnection, table: str) -> dict[str, dict]:
    rows = (
        await conn.execute(
            sa.text(
                """
                SELECT column_name, data_type, is_nullable,
                       character_maximum_length AS maxlen
                  FROM information_schema.columns
                 WHERE table_name = :t
                """
            ),
            {"t": table},
        )
    ).mappings()
    return {r["column_name"]: dict(r) for r in rows}


async def test_membership_tiers_has_its_columns_and_checks() -> None:
    async with get_sessionmaker()() as s:
        conn = await s.connection()
        cols = await _columns(conn, "membership_tiers")

        assert cols, "la tabla membership_tiers no existe"
        for name in (
            "code",
            "display_name",
            "monthly_price_cents",
            "weekly_pool_tokens",
            "max_teammates",
            "max_members",
            "stripe_price_id",
            "sort_order",
            "is_public",
        ):
            assert name in cols, f"falta la columna {name}"

        assert cols["stripe_price_id"]["is_nullable"] == "YES", (
            "stripe_price_id tiene que ser anulable: al migrar de cuenta se pone "
            "a NULL y el sistema debe quedar en un estado válido (research D5.1)"
        )
        assert cols["stripe_price_id"]["maxlen"] == 64

        checks = {
            r[0]
            for r in (
                await conn.execute(
                    sa.text(
                        """
                        SELECT conname FROM pg_constraint
                         WHERE conrelid = 'membership_tiers'::regclass
                           AND contype = 'c'
                        """
                    )
                )
            ).all()
        }
        assert any("code" in c for c in checks), "el CHECK sobre code no está"


async def test_no_provider_identifier_is_a_key_of_ours() -> None:
    """research D5.1. La regla, comprobada en vez de prometida."""
    async with get_sessionmaker()() as s:
        conn = await s.connection()
        rows = (
            (
                await conn.execute(
                    sa.text(
                        """
                    SELECT c.conname, c.contype, t.relname AS tbl,
                           pg_get_constraintdef(c.oid) AS def
                      FROM pg_constraint c
                      JOIN pg_class t ON t.oid = c.conrelid
                     WHERE t.relname IN ('membership_tiers', 'partner_subscriptions')
                       AND c.contype IN ('u', 'p', 'f')
                    """
                    )
                )
            )
            .mappings()
            .all()
        )
        # Sin esto el test pasaría para siempre si las tablas dejaran de tener
        # restricciones, o si el nombre de una cambiara: un bucle sobre cero
        # filas no comprueba nada y nadie se entera.
        assert rows, (
            "no se encontró ninguna PK/UNIQUE/FK en membership_tiers ni en "
            "partner_subscriptions: la consulta dejó de mirar donde debía"
        )
        for r in rows:
            assert "stripe_" not in r["def"], (
                f"la restricción {r['conname']} sobre {r['tbl']} usa un identificador "
                f"del proveedor: {r['def']}. Ningún id de Stripe puede ser clave de "
                "nada nuestro — el día de la migración de cuenta eso es lo que "
                "convierte un UPDATE en una reconstrucción (research D5.1)"
            )


async def test_the_four_tiers_are_seeded() -> None:
    async with get_sessionmaker()() as s:
        rows = (
            (
                await s.execute(
                    sa.text(
                        "SELECT code, monthly_price_cents, weekly_pool_tokens, "
                        "max_teammates, max_members FROM membership_tiers ORDER BY sort_order"
                    )
                )
            )
            .mappings()
            .all()
        )
        by_code = {r["code"]: r for r in rows}
        assert set(by_code) == set(_TIERS), f"niveles sembrados: {sorted(by_code)}"

        assert by_code["free"]["monthly_price_cents"] == 0
        assert by_code["pro"]["monthly_price_cents"] == 2000
        assert by_code["team"]["monthly_price_cents"] == 6000
        assert by_code["business"]["monthly_price_cents"] == 15000

        for code, row in by_code.items():
            assert row["weekly_pool_tokens"] > 0, f"{code} nace sin pool"
            assert row["max_members"] >= 1, f"{code} no admite ni una persona"

        assert by_code["free"]["max_teammates"] == 0
        # El múltiplo publicado sale de dividir por el nivel de pago más bajo
        # (research D9). Si estas proporciones dejan de ser enteras, la pantalla
        # de planes empieza a decir «3,7x» y hay que decidir qué hacer.
        base = by_code["pro"]["weekly_pool_tokens"]
        assert by_code["team"]["weekly_pool_tokens"] % base == 0
        assert by_code["business"]["weekly_pool_tokens"] % base == 0


async def test_partner_subscriptions_is_rls_enabled_and_forced() -> None:
    async with get_sessionmaker()() as s:
        conn = await s.connection()
        row = (
            await conn.execute(
                sa.text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                    "WHERE relname = 'partner_subscriptions'"
                )
            )
        ).first()
        assert row is not None, "la tabla partner_subscriptions no existe"
        assert row[0] is True, "RLS no está ENABLE"
        assert row[1] is True, "RLS no está FORCE — el dueño de la tabla la saltaría"


async def test_subscription_state_check_rejects_a_fifth_state() -> None:
    """Los cuatro estados de ADR-037 D6, y sólo esos."""
    async with get_sessionmaker()() as s:
        pid = uuid.uuid4()
        await s.execute(
            sa.text("INSERT INTO partners (id, name, slug, status) VALUES (:i, 'x', :s, 'active')"),
            {"i": str(pid), "s": f"p-{pid.hex[:8]}"},
        )
        with pytest.raises(IntegrityError):
            await s.execute(
                sa.text(
                    "INSERT INTO partner_subscriptions (partner_id, tier_code, state) "
                    "VALUES (:i, 'pro', 'almost_paid')"
                ),
                {"i": str(pid)},
            )
        await s.rollback()
