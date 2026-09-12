"""Spec 004 · puerta de aislamiento, garantía 1 (Postgres RLS).

El camino de lectura del presupuesto cambió: antes recorría ``companion.runs``
membresía a membresía reapuntando ``app.principal_id``; ahora lee una fila de
``partner_wallets``, que lleva RLS ENABLE + FORCE por ``partner_id``.

Es **menos** superficie, no más — y aun así lleva su test, porque el principio I
no distingue entre abrir una puerta y mover una: lo que se comprueba es que el
presupuesto de un partner no se puede leer desde otro, y que la ausencia del
GUC devuelve cero filas en vez de un 500.

En rojo bloquea el merge.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from tests.conftest import make_partner_with_wallet, spend_from_wallet

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]


async def test_a_partner_never_reads_another_partners_budget(db_session) -> None:
    from nexus_api.api.console.companion import partner_budget_in_tx

    a = await make_partner_with_wallet(db_session, included=100_000)
    b = await make_partner_with_wallet(db_session, included=7)
    await spend_from_wallet(partner_id=a["partner_id"], qty=40_000, lane="companion")

    budget_a = await partner_budget_in_tx(db_session, a["partner_id"])
    budget_b = await partner_budget_in_tx(db_session, b["partner_id"])

    assert budget_a.remaining == 60_000
    assert budget_b.remaining == 7, "el saldo de B se contaminó con el de A"
    assert budget_a.cap != budget_b.cap


async def test_without_the_partner_guc_the_wallet_reads_as_zero_rows(db_session) -> None:
    """Fail-closed, y **no un 500**.

    El patrón ``NULLIF`` de la RLS de este repositorio existe justo para esto:
    un cast pelado convierte un GUC ausente en un error de servidor en vez de
    en cero filas, y un 500 en el camino del presupuesto deja al partner sin
    poder trabajar por un motivo que la pantalla no sabe explicar.
    """
    a = await make_partner_with_wallet(db_session, included=5_000)

    async with db_session.begin_nested():
        await db_session.execute(sa.text("SET LOCAL ROLE nexus_app"))
        await db_session.execute(sa.text("SELECT set_config('app.partner_id', '', true)"))
        rows = (
            await db_session.execute(
                sa.text("SELECT partner_id FROM partner_wallets WHERE partner_id = :p"),
                {"p": str(a["partner_id"])},
            )
        ).all()
        assert rows == []


async def test_the_ledger_of_one_partner_is_invisible_to_the_other(db_session) -> None:
    """Los asientos son del partner, y el reparto por cliente también."""
    from nexus_api.core.partner_context import apply_partner_to_session

    a = await make_partner_with_wallet(db_session, included=50_000)
    b = await make_partner_with_wallet(db_session, included=50_000)
    await spend_from_wallet(partner_id=a["partner_id"], qty=1_000, lane="companion")

    async with db_session.begin_nested():
        await apply_partner_to_session(db_session, b["partner_id"])
        count = await db_session.scalar(
            sa.text("SELECT count(*) FROM usage_ledger WHERE partner_id = :p"),
            {"p": str(a["partner_id"])},
        )
        assert int(count or 0) == 0


async def test_a_random_partner_id_reads_an_empty_budget_not_someone_elses(db_session) -> None:
    from nexus_api.api.console.companion import partner_budget_in_tx

    await make_partner_with_wallet(db_session, included=999_999)

    budget = await partner_budget_in_tx(db_session, uuid.uuid4())

    assert budget.remaining == 0
    assert budget.cap == 0
    assert budget.exhausted is True
