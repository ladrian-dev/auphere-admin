"""Garantía 1 — los pagos de mensualidad de un cliente (``tenant_payments``).

La tabla da ``SELECT, INSERT, UPDATE`` a ``nexus_app``, el rol con el que
corren las sesiones de un cliente. Su política (0157, corregida en
``bb93cb3f``) es la de ``invoices``: RLS **activada sin FORCE**. Las guardas
``test_21`` y ``test_22`` comprueban que la tabla está declarada; esto
comprueba que la política **hace** lo que promete:

- la sesión de un cliente (``nexus_app`` con ``app.tenant_id``) solo ve y solo
  escribe sus pagos — lo que usan las rutas del admin de un cliente
  (``scoped_session_from_path``);
- el camino de plataforma (sin ``SET ROLE`` ni GUC) los ve todos — el listado
  del mes del admin (``GET /admin/tenant-payments``). Con FORCE saldría vacío
  sin dar error.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from nexus_api.db.base import get_sessionmaker

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]

# Every test asks for ``db_session`` only for its teardown: the harness empties
# the tables after it, so these payments never reach a test that lists a month.


async def _two_clients_with_a_payment() -> tuple[uuid.UUID, uuid.UUID]:
    a, b = uuid.uuid4(), uuid.uuid4()
    sm = get_sessionmaker()
    async with sm() as session:
        for tid, slug in ((a, "pay-a"), (b, "pay-b")):
            await session.execute(
                sa.text(
                    "INSERT INTO tenants (id, name, slug, plan) "
                    "VALUES (:id, :n, :s, 'pro') ON CONFLICT DO NOTHING"
                ),
                {"id": str(tid), "n": slug, "s": f"{slug}-{tid.hex[:8]}"},
            )
            await session.execute(
                sa.text(
                    "INSERT INTO tenant_payments "
                    "(tenant_id, period_year, period_month, amount_cents, method, paid_on, recorded_by) "
                    "VALUES (:t, 2026, 10, 9900, 'transfer', '2026-10-01', 'operator:test')"
                ),
                {"t": str(tid)},
            )
        await session.commit()
    return a, b


async def test_a_clients_session_cannot_read_another_clients_payment(db_session) -> None:
    a, b = await _two_clients_with_a_payment()
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await session.execute(
            sa.text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(a)}
        )
        await session.execute(sa.text("SET LOCAL ROLE nexus_app"))
        visible = (
            (
                await session.execute(
                    sa.text("SELECT tenant_id FROM tenant_payments WHERE tenant_id IN (:a, :b)"),
                    {"a": str(a), "b": str(b)},
                )
            )
            .scalars()
            .all()
        )
    assert visible == [a], "la sesión de un cliente vio el pago de otro"


async def test_a_clients_session_cannot_write_a_payment_for_another(db_session) -> None:
    a, b = await _two_clients_with_a_payment()
    sm = get_sessionmaker()
    async with sm() as session:
        await session.begin()
        await session.execute(
            sa.text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(a)}
        )
        await session.execute(sa.text("SET LOCAL ROLE nexus_app"))
        with pytest.raises(sa.exc.DBAPIError):
            await session.execute(
                sa.text(
                    "INSERT INTO tenant_payments "
                    "(tenant_id, period_year, period_month, amount_cents, method, paid_on, recorded_by) "
                    "VALUES (:t, 2026, 11, 9900, 'cash', '2026-11-01', 'operator:test')"
                ),
                {"t": str(b)},
            )
        await session.rollback()


async def test_the_platform_path_still_sees_every_payment(db_session) -> None:
    a, b = await _two_clients_with_a_payment()
    sm = get_sessionmaker()
    async with sm() as session:
        # Sin SET ROLE y sin GUC: el listado del mes del admin.
        seen = set(
            (
                await session.execute(
                    sa.text("SELECT tenant_id FROM tenant_payments WHERE tenant_id IN (:a, :b)"),
                    {"a": str(a), "b": str(b)},
                )
            )
            .scalars()
            .all()
        )
    assert seen == {a, b}
