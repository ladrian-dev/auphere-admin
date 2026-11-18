"""El vaciado entre pruebas hace lo que hacía el ``TRUNCATE`` al que sustituye.

Toda la suite descansa en él: una fila que sobrevive a una prueba es un rojo en
otra, o peor, un verde que no prueba nada. Por eso no se da por bueno que siga los
mismos caminos: se le pregunta a Postgres qué alcanza el ``TRUNCATE`` de verdad.
"""

from __future__ import annotations

import asyncio
import collections
import re
import uuid
from typing import Any

import psycopg2
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexus_api.db.models import Tenant, TenantPlan
from tests import conftest
from tests.conftest import _TRUNCATE_TABLES, TEST_DB_URL, _empty_database, _parse_dsn, make_inbox

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _plan() -> conftest._CleanupPlan:
    assert conftest._cleanup_plan is not None
    return conftest._cleanup_plan


def _relname(table: str) -> str:
    return table.rsplit(".", 1)[-1]


def _what_truncate_says_it_reaches() -> set[str]:
    """Los nombres que ``TRUNCATE … CASCADE`` anuncia, deshecho con ROLLBACK."""
    conn = psycopg2.connect(**_parse_dsn(TEST_DB_URL))
    conn.notices = collections.deque()  # psycopg2 keeps only the last 50 otherwise
    try:
        with conn.cursor() as cur:
            cur.execute(
                "TRUNCATE TABLE " + ", ".join(_TRUNCATE_TABLES) + " RESTART IDENTITY CASCADE"
            )
        cascaded = {
            match.group(1)
            for notice in conn.notices
            if (match := re.search(r'truncate cascades to table "([^"]+)"', notice))
        }
    finally:
        conn.rollback()
        conn.close()
    return cascaded | {_relname(t) for t in _TRUNCATE_TABLES}


def _partitions() -> set[str]:
    conn = psycopg2.connect(**_parse_dsn(TEST_DB_URL))
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT relname FROM pg_class WHERE relispartition AND relkind = 'r'")
            return {row[0] for row in cur.fetchall()}
    finally:
        conn.close()


async def _rows_per_table(session: AsyncSession) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in _plan().tables:
        counts[table] = (await session.execute(sa.text(f"SELECT count(*) FROM {table}"))).scalar()
    return counts


async def test_the_plan_reaches_exactly_what_truncate_cascade_reaches() -> None:
    """Ni una tabla de menos (sobrevivirían filas) ni una de más (se borraría una
    semilla de plataforma). Postgres no anuncia las particiones, que entran con su
    tabla madre, así que esas se descuentan de los dos lados."""
    partitions = _partitions()
    reached = _what_truncate_says_it_reaches() - partitions
    planned = {_relname(t) for t in _plan().tables} - partitions
    assert planned == reached


async def test_it_leaves_every_table_empty(
    db_session: AsyncSession, test_engine: Any, console_world: Any
) -> None:
    world = console_world["a"]
    await make_inbox(db_session, partner_id=world["partner_id"], tenant_id=world["tenant_id"])
    before = await _rows_per_table(db_session)
    assert sum(1 for rows in before.values() if rows) >= 5, "la prueba no ha sembrado casi nada"
    await db_session.rollback()

    await _empty_database(test_engine)

    after = await _rows_per_table(db_session)
    assert {table: rows for table, rows in after.items() if rows} == {}


async def test_platform_seeds_stay(db_session: AsyncSession, test_engine: Any) -> None:
    """``tool_catalog`` no está al alcance del ``CASCADE``: su semilla se queda."""
    catalog = sa.text("SELECT count(*) FROM tool_catalog")
    before = (await db_session.execute(catalog)).scalar()
    assert before, "tool_catalog viene sembrado por las migraciones"
    await db_session.rollback()

    await _empty_database(test_engine)

    assert (await db_session.execute(catalog)).scalar() == before


async def test_sequences_restart_even_if_their_table_is_empty(
    db_session: AsyncSession, test_engine: Any
) -> None:
    sequences = _plan().sequences
    assert sequences, "RESTART IDENTITY no tendría nada que hacer: revisa el plan"
    for name, _start in sequences:
        await db_session.execute(sa.text(f"SELECT nextval('{name}')"))
    await db_session.commit()

    await _empty_database(test_engine)

    for name, start in sequences:
        assert (await db_session.execute(sa.text(f"SELECT nextval('{name}')"))).scalar() == start


async def test_it_waits_for_a_transaction_still_open(
    db_session: AsyncSession, test_engine: Any
) -> None:
    """Una tarea de la prueba que aún no ha confirmado: sus filas no se ven todavía.
    ``TRUNCATE`` la esperaba por sus locks; sin esa espera, sus filas aparecerían en
    la prueba siguiente."""
    tenant_id = uuid.uuid4()
    async with async_sessionmaker(bind=test_engine, expire_on_commit=False)() as straggler:
        straggler.add(
            Tenant(
                id=tenant_id, name="Rezagado", slug=f"r-{tenant_id.hex[:8]}", plan=TenantPlan.PRO
            )
        )
        await straggler.flush()

        emptying = asyncio.create_task(_empty_database(test_engine))
        await asyncio.sleep(0.3)
        assert not emptying.done(), "el vaciado no esperó a la transacción abierta"

        await straggler.commit()
        await asyncio.wait_for(emptying, timeout=10)

    assert (await db_session.execute(sa.text("SELECT count(*) FROM tenants"))).scalar() == 0
