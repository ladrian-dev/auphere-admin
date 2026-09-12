"""Spec 005 · garantía 1 — la suscripción de un partner es suya (RLS).

El estado de suscripción dice cuánto paga alguien y en qué punto de la escalera
de impago está. Que un partner pueda leer el de otro es una fuga comercial, y
que pueda escribirlo es peor: se regalaría un nivel.

FORCE y no solo ENABLE: sin FORCE, el dueño de la tabla —que es el rol con el
que corren las migraciones— se salta la política sin enterarse.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from nexus_api.db.base import get_sessionmaker

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]


async def _as_app(session, partner_id: uuid.UUID | None) -> None:
    await session.execute(
        sa.text("SELECT set_config('app.partner_id', :p, false)"),
        {"p": "" if partner_id is None else str(partner_id)},
    )
    await session.execute(sa.text("SET ROLE nexus_app"))


async def _seed(session, partner_id: uuid.UUID, tier: str = "pro") -> None:
    slug = f"sub-{partner_id.hex[:10]}"
    await session.execute(
        sa.text(
            "INSERT INTO partners (id, name, slug, status) "
            "VALUES (:id, :n, :s, 'active') ON CONFLICT (id) DO NOTHING"
        ),
        {"id": str(partner_id), "n": slug, "s": slug},
    )
    await session.execute(
        sa.text(
            "INSERT INTO partner_subscriptions (partner_id, tier_code, state) "
            "VALUES (:p, :t, 'current') ON CONFLICT (partner_id) DO NOTHING"
        ),
        {"p": str(partner_id), "t": tier},
    )


async def test_a_partner_cannot_read_another_partners_subscription() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    sm = get_sessionmaker()
    async with sm() as s:
        await _seed(s, a, "pro")
        await _seed(s, b, "business")
        await s.commit()

    async with sm() as s:
        await _as_app(s, a)
        rows = (
            await s.execute(sa.text("SELECT partner_id, tier_code FROM partner_subscriptions"))
        ).all()
        seen = {str(r[0]) for r in rows}
        assert str(b) not in seen, (
            "el partner A ve la suscripción de B: la política de RLS no filtra"
        )
        assert seen <= {str(a)}


async def test_no_partner_context_means_no_rows() -> None:
    """Fail-closed: sin GUC no se ve nada, en vez de verse todo."""
    pid = uuid.uuid4()
    sm = get_sessionmaker()
    async with sm() as s:
        await _seed(s, pid)
        await s.commit()
    async with sm() as s:
        await _as_app(s, None)
        count = await s.scalar(sa.text("SELECT count(*) FROM partner_subscriptions"))
        assert count == 0, "sin app.partner_id se leen filas: la política no es fail-closed"


async def test_a_partner_cannot_grant_itself_a_tier_on_another_row() -> None:
    """WITH CHECK: escribir la fila de otro tiene que ser imposible, no difícil."""
    a, b = uuid.uuid4(), uuid.uuid4()
    sm = get_sessionmaker()
    async with sm() as s:
        await _seed(s, a, "free")
        await _seed(s, b, "free")
        await s.commit()

    async with sm() as s:
        await _as_app(s, a)
        await s.execute(
            sa.text(
                "UPDATE partner_subscriptions SET tier_code = 'business' WHERE partner_id = :b"
            ),
            {"b": str(b)},
        )
        await s.commit()

    # La verificación se hace CON el contexto de B, no sin contexto: la RLS
    # está en FORCE, así que también filtra al dueño de la tabla y una lectura
    # sin ``app.partner_id`` devuelve ``None`` — que se confundiría con «la
    # fila desapareció» y haría pasar el test por la razón equivocada.
    async with sm() as s:
        await _as_app(s, b)
        tier = await s.scalar(
            sa.text("SELECT tier_code FROM partner_subscriptions WHERE partner_id = :b"),
            {"b": str(b)},
        )
        assert tier == "free", f"el partner A cambió el nivel de B a «{tier}»"


async def test_the_table_is_in_the_structural_rls_catalogue() -> None:
    """Que no se quede fuera del test que recorre todas las tablas del partner.

    Una tabla nueva con RLS que nadie añade al catálogo deja de estar
    vigilada por el barrido estructural, y el día que alguien quite la
    política nadie se entera.
    """
    from tests.isolation.test_21_rls_covers_every_tenant_table import PARTNER_FORCE_TABLES

    assert "partner_subscriptions" in PARTNER_FORCE_TABLES
