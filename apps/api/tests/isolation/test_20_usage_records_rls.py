"""Aislamiento de ``usage_records`` (WP-16) y RLS en las PARTICIONES (0069).

Dos cosas distintas, en el mismo sitio porque la segunda es la que hace
verdad a la primera:

1. La tabla nueva de consumo tiene ENABLE + FORCE RLS con policy por
   tenant. Es una tabla de facturación: una fuga aquí no es un dato de
   más, es el consumo de un cliente en la factura de otro.
2. **Una partición NO hereda la row security de su padre.** Hasta 0069,
   ``messages`` tenía RLS forzada y ``messages_y2026m08`` no: cualquier
   consulta directa a la partición leía todos los tenants sin filtrar y
   sin error. El arreglo vive en ``ensure_month_partition()``, así que se
   comprueba creando una partición NUEVA por el mismo camino que usa el
   cron de mantenimiento en producción.

Bloqueante como el resto de la suite.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa

from nexus_api.db.base import get_sessionmaker

pytestmark = pytest.mark.asyncio


async def _as_app_role(session, tenant_id: uuid.UUID | None) -> None:
    await session.execute(
        sa.text("SELECT set_config('app.tenant_id', :t, false)"),
        {"t": "" if tenant_id is None else str(tenant_id)},
    )
    await session.execute(sa.text("SET ROLE nexus_app"))


async def _ensure_tenant(session, tenant_id: uuid.UUID) -> None:
    """El tenant tiene que existir de verdad desde la 0077: ``usage_records``
    ya no acepta un ``tenant_id`` inventado. Antes sí, y eso significaba
    que la tabla de facturación podía acumular consumo de clientes que no
    existen — el test se apoyaba en esa laxitud sin saberlo."""
    await session.execute(
        sa.text(
            "INSERT INTO tenants (id, name, slug, plan, status) "
            "VALUES (:t, 'usage rls', :s, 'essential', 'active') "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {"t": str(tenant_id), "s": f"usage-{tenant_id.hex[:10]}"},
    )


async def _insert_usage(session, tenant_id: uuid.UUID, *, meter: str = "llm.input_tokens") -> str:
    key = f"test:{uuid.uuid4()}"
    await session.execute(
        sa.text(
            "INSERT INTO usage_records "
            "(tenant_id, occurred_at, meter, quantity, cost_usd, billable_qty, idempotency_key) "
            "VALUES (:t, now(), :m, 1000, 0.003, 1000, :k)"
        ),
        {"t": str(tenant_id), "m": meter, "k": key},
    )
    return key


async def test_tenant_sees_only_its_own_usage(db_session) -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    sm = get_sessionmaker()

    async with sm() as session:
        await _ensure_tenant(session, a)
        await _ensure_tenant(session, b)
        await session.execute(
            sa.text("SELECT set_config('app.tenant_id', :t, false)"), {"t": str(a)}
        )
        key_a = await _insert_usage(session, a)
        await session.execute(
            sa.text("SELECT set_config('app.tenant_id', :t, false)"), {"t": str(b)}
        )
        await _insert_usage(session, b)
        await session.commit()

    async with sm() as session:
        await _as_app_role(session, a)
        rows = (
            await session.execute(
                sa.text(
                    "SELECT idempotency_key, tenant_id FROM usage_records "
                    "WHERE tenant_id IN (:a, :b)"
                ),
                {"a": str(a), "b": str(b)},
            )
        ).all()
        assert [r[0] for r in rows] == [key_a]


async def test_unscoped_session_sees_no_usage(db_session) -> None:
    a = uuid.uuid4()
    sm = get_sessionmaker()

    async with sm() as session:
        await _ensure_tenant(session, a)
        await session.execute(
            sa.text("SELECT set_config('app.tenant_id', :t, false)"), {"t": str(a)}
        )
        await _insert_usage(session, a)
        await session.commit()

    async with sm() as session:
        await _as_app_role(session, None)  # sin GUC: fail-closed, no error
        visible = await session.scalar(
            sa.text("SELECT count(*) FROM usage_records WHERE tenant_id = :a"),
            {"a": str(a)},
        )
        assert visible == 0


async def test_cross_tenant_usage_write_is_rejected(db_session) -> None:
    """Facturarle a otro es lo que impide el WITH CHECK implícito de la
    policy (comando ALL sin WITH CHECK explícito reutiliza el USING)."""
    a, b = uuid.uuid4(), uuid.uuid4()
    sm = get_sessionmaker()

    async with sm() as session:
        await _as_app_role(session, a)
        with pytest.raises(Exception, match=r"row-level security|violates"):
            await _insert_usage(session, b)


async def test_new_partitions_inherit_row_security(db_session) -> None:
    """0069: el camino real del cron de mantenimiento (WP-13).

    Se pide un mes lejano para forzar la CREACIÓN de la partición, y se
    comprueba que nace con RLS activa y forzada. Sin esto, cada mes que
    pasa añade una tabla con los datos de todos los tenants legible sin
    filtro por cualquier consulta directa.
    """
    sm = get_sessionmaker()
    far_month = datetime(2031, 7, 1, tzinfo=UTC).date()

    async with sm() as session:
        for parent in ("messages", "usage_records"):
            name = await session.scalar(
                sa.text("SELECT ensure_month_partition(:p, :m)"),
                {"p": parent, "m": far_month},
            )
            flags = (
                await session.execute(
                    sa.text(
                        "SELECT relrowsecurity, relforcerowsecurity "
                        "FROM pg_class WHERE relname = :n"
                    ),
                    {"n": name},
                )
            ).one()
            assert flags == (True, True), f"{name} nació sin RLS heredada del padre"
            await session.execute(sa.text(f"DROP TABLE {name}"))
        await session.commit()


async def test_existing_partitions_were_backfilled(db_session) -> None:
    """La otra mitad de 0069: las particiones que ya existían cuando se
    descubrió el agujero también quedaron protegidas."""
    sm = get_sessionmaker()
    async with sm() as session:
        unprotected = (
            (
                await session.execute(
                    sa.text(
                        "SELECT child.relname FROM pg_inherits i "
                        "JOIN pg_class child ON child.oid = i.inhrelid "
                        "JOIN pg_class parent ON parent.oid = i.inhparent "
                        "JOIN pg_namespace n ON n.oid = child.relnamespace "
                        "WHERE n.nspname = 'public' AND parent.relkind = 'p' "
                        "AND parent.relrowsecurity AND NOT child.relrowsecurity"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert unprotected == [], f"particiones sin RLS pese al padre: {unprotected}"
