"""``nexus_reporting`` lee entre tenants — y sólo lo que el panel enseña (0078).

Este archivo existe porque la 0078 hace algo que el resto del sistema
prohíbe: **un rol que ve filas de todos los tenants**. Es deliberado (sin
eso no hay panel de margen) y por eso mismo necesita un guardián propio.
El riesgo no es que el permiso exista, es que crezca sin que nadie lo
note: un ``GRANT SELECT`` de más sobre ``agent_configs`` convierte un
panel de costes en una filtración del prompt a medida de cada cliente,
que es el producto que se le vende.

Las pruebas van en dos direcciones, y la segunda importa más:

1. El rol **puede** leer coste agregado de más de un tenant a la vez.
   Si esto se rompe, el panel enseña cero y parece que no hay gasto.
2. El rol **no puede** leer lo que no se le concedió, no puede escribir,
   y —lo que de verdad se está protegiendo— **no ha aflojado la RLS de
   ``nexus_app``**. Una policy permisiva se suma con OR: escribirla mal
   (sin ``TO nexus_reporting``) la habría aplicado a todo el mundo y el
   aislamiento entero se habría caído en silencio, con todos los tests de
   negocio en verde.

Bloqueante como el resto de la suite.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa

from nexus_api.db.base import get_sessionmaker

from .conftest import set_tenant

pytestmark = pytest.mark.asyncio

REPORTING_ROLE = "nexus_reporting"

# Columnas que el rol NO debe poder leer, y por qué duele cada una.
FORBIDDEN_COLUMNS: list[tuple[str, str, str]] = [
    (
        "agent_configs",
        "system_prompt_rendered",
        "el prompt a medida del cliente — es el producto que se le vende",
    ),
    ("agent_configs", "tools", "la lista de herramientas revela la integración del cliente"),
    ("tenants", "owner_phone", "dato personal del dueño del negocio"),
    ("tenants", "owner_email", "dato personal del dueño del negocio"),
    (
        "usage_records",
        "idempotency_key",
        "identifica turnos concretos; el panel agrega, nunca señala una conversación",
    ),
]

# Tablas fuera del alcance del panel. Si alguna empieza a leerse, que sea
# porque alguien lo escribió aquí.
FORBIDDEN_TABLES: list[str] = [
    "messages",
    "conversations",
    "customers",
    "tenant_credentials",
    "tenant_connectors",
    "agent_memories",
    "audit_log",
]


async def _seed_usage(session, tenant_id: uuid.UUID, *, cost: str | None) -> None:
    await session.execute(
        sa.text("SELECT ensure_month_partition('usage_records', :d)"),
        {"d": datetime.now(UTC).date()},
    )
    await session.execute(
        sa.text(
            "INSERT INTO usage_records "
            "(tenant_id, occurred_at, meter, quantity, cost_usd, billable_qty, "
            " idempotency_key) "
            "VALUES (:t, now(), 'llm.input_tokens', 1000, :c, 1000, :k)"
        ),
        {"t": str(tenant_id), "c": cost, "k": f"rep:{uuid.uuid4()}"},
    )


async def test_reporting_role_reads_cost_across_tenants(tenants_ab) -> None:
    """El permiso existe de verdad: dos tenants, una consulta, dos filas."""
    sm = get_sessionmaker()
    async with sm() as session:
        await _seed_usage(session, tenants_ab["a"], cost="0.0025")
        await _seed_usage(session, tenants_ab["b"], cost="0.0025")
        await session.commit()

    async with sm() as session:
        await session.execute(sa.text(f"SET LOCAL ROLE {REPORTING_ROLE}"))
        rows = (
            await session.execute(
                sa.text(
                    "SELECT tenant_id, cost_usd_total FROM reporting_tenant_cost_monthly "
                    "WHERE tenant_id = ANY(:ids)"
                ),
                {"ids": [tenants_ab["a"], tenants_ab["b"]]},
            )
        ).all()

    seen = {r[0] for r in rows}
    assert seen == {tenants_ab["a"], tenants_ab["b"]}, (
        "el rol de reporting no ve los dos tenants — el panel de margen "
        f"enseñaría un total incompleto. Visto: {seen}"
    )


async def test_view_flags_unpriced_records(tenants_ab) -> None:
    """``SUM`` ignora los NULL, así que un mes a medio tarifar devuelve una
    cifra pequeña y creíble. La vista tiene que delatar ese hueco: es la
    diferencia entre un panel que informa y uno que miente con confianza."""
    sm = get_sessionmaker()
    async with sm() as session:
        await _seed_usage(session, tenants_ab["a"], cost="0.0025")
        await _seed_usage(session, tenants_ab["a"], cost=None)
        await session.commit()

    async with sm() as session:
        await session.execute(sa.text(f"SET LOCAL ROLE {REPORTING_ROLE}"))
        row = (
            await session.execute(
                sa.text(
                    "SELECT sum(records), sum(unpriced_records) "
                    "FROM reporting_tenant_cost_monthly WHERE tenant_id = :t"
                ),
                {"t": tenants_ab["a"]},
            )
        ).one()

    assert row[0] == 2
    assert row[1] == 1, "la vista no señala la fila sin precio — el total parecería completo"


@pytest.mark.parametrize(("table", "column", "why"), FORBIDDEN_COLUMNS)
async def test_reporting_role_cannot_read_sensitive_columns(
    table: str, column: str, why: str
) -> None:
    sm = get_sessionmaker()
    async with sm() as session:
        await session.execute(sa.text(f"SET LOCAL ROLE {REPORTING_ROLE}"))
        with pytest.raises(Exception, match="permission denied"):
            await session.execute(sa.text(f"SELECT {column} FROM {table} LIMIT 1"))


@pytest.mark.parametrize("table", FORBIDDEN_TABLES)
async def test_reporting_role_cannot_read_tables_outside_the_panel(table: str) -> None:
    sm = get_sessionmaker()
    async with sm() as session:
        await session.execute(sa.text(f"SET LOCAL ROLE {REPORTING_ROLE}"))
        with pytest.raises(Exception, match="permission denied"):
            await session.execute(sa.text(f"SELECT * FROM {table} LIMIT 1"))


async def test_reporting_role_cannot_write() -> None:
    sm = get_sessionmaker()
    async with sm() as session:
        await session.execute(sa.text(f"SET LOCAL ROLE {REPORTING_ROLE}"))
        for statement in (
            "DELETE FROM usage_records",
            "UPDATE usage_records SET cost_usd = 0",
            "INSERT INTO usage_records (tenant_id, occurred_at, meter, quantity, "
            "billable_qty, idempotency_key) VALUES "
            "('00000000-0000-0000-0000-000000000000', now(), 'x', 1, 1, 'x')",
        ):
            with pytest.raises(Exception, match="permission denied"):
                await session.execute(sa.text(statement))
            await session.rollback()
            await session.execute(sa.text(f"SET LOCAL ROLE {REPORTING_ROLE}"))


async def test_reporting_policy_did_not_loosen_nexus_app(tenants_ab) -> None:
    """El control negativo que justifica todo el archivo.

    Las policies permisivas se combinan con OR. Si la de reporting se
    hubiera escrito sin ``TO nexus_reporting``, ``nexus_app`` vería
    también todos los tenants — y ningún test de negocio lo notaría,
    porque las consultas de la aplicación llevan su propio filtro.
    """
    sm = get_sessionmaker()
    async with sm() as session:
        await _seed_usage(session, tenants_ab["a"], cost="0.0025")
        await _seed_usage(session, tenants_ab["b"], cost="0.0025")
        await session.commit()

    async with sm() as session:
        await set_tenant(session, tenants_ab["a"])
        visible = (
            (await session.execute(sa.text("SELECT DISTINCT tenant_id FROM usage_records")))
            .scalars()
            .all()
        )

    assert set(visible) <= {tenants_ab["a"]}, (
        "nexus_app ve consumo de otro tenant: la policy de reporting se "
        f"aplicó a todos los roles. Visto: {set(visible)}"
    )


async def test_reporting_role_is_not_privileged() -> None:
    """``BYPASSRLS`` o ``SUPERUSER`` harían irrelevante todo lo anterior:
    el alcance dejaría de ser el de los GRANT y pasaría a ser la base
    entera, sin cambiar una sola línea de esta suite."""
    sm = get_sessionmaker()
    async with sm() as session:
        row = (
            await session.execute(
                sa.text(
                    "SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole, rolinherit "
                    "FROM pg_roles WHERE rolname = :r"
                ),
                {"r": REPORTING_ROLE},
            )
        ).one_or_none()

    assert row is not None, f"el rol {REPORTING_ROLE} no existe — ¿se aplicó la 0078?"
    super_, bypass, createdb, createrole, inherit = row
    assert not super_, "el rol de reporting es superusuario"
    assert not bypass, "el rol de reporting tiene BYPASSRLS: lee la base entera"
    assert not createdb and not createrole, "el rol de reporting puede crear objetos"
    assert not inherit, (
        "el rol hereda privilegios de los roles de los que sea miembro; "
        "NOINHERIT es lo que hace que SET ROLE dé exactamente este alcance"
    )
