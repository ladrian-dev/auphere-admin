"""Spec 047, T002 — la migración 0175 deja la base de la fábrica (requisitos 56.1, 55.2).

Fija lo que el resto de la spec da por hecho:

- ``jobs`` es por cliente con RLS ENABLE + FORCE: el rol de la aplicación no ve
  ni escribe un trabajo de otro cliente;
- su FK al agente es **compuesta**: un trabajo del cliente A no puede apuntar a
  un agente del B (la comprobación de una FK no pasa por la RLS);
- ``job_tenant`` devuelve el cliente de un trabajo y nada más, sin contexto;
- el ciclo de vida se sostiene en la base: terminado ⇔ ``finished_at``, y un
  fallo lleva su código;
- ``partners`` gana la activación de la consola nueva, y no hay «quién» sin «cuándo».

La ida y vuelta de la migración la cubre ``test_migration_reversibility.py``.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from tests.conftest import TEST_DB_URL

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _exec(sql: str, *, tenant: uuid.UUID | None = None, **params: Any) -> list[Any]:
    """One transaction. With ``tenant``, as ``nexus_app`` under that client."""
    engine = create_async_engine(TEST_DB_URL)
    try:
        async with engine.begin() as conn:
            if tenant is not None:
                await conn.execute(
                    sa.text(
                        "SELECT set_config('app.tenant_id', :t, true), "
                        "set_config('role', 'nexus_app', true)"
                    ),
                    {"t": str(tenant)},
                )
            result = await conn.execute(sa.text(sql), params)
            return list(result.all()) if result.returns_rows else []
    finally:
        await engine.dispose()


async def _tenant_with_agent() -> tuple[uuid.UUID, uuid.UUID]:
    tid, aid = uuid.uuid4(), uuid.uuid4()
    await _exec(
        "INSERT INTO tenants (id, name, slug, plan, status) VALUES (:i, 'F', :s, 'pro', 'active')",
        i=tid,
        s=f"f-{tid.hex[:10]}",
    )
    await _exec(
        "INSERT INTO agents (id, tenant_id, name, status) VALUES (:a, :t, 'Recepción', 'active')",
        a=aid,
        t=tid,
    )
    return tid, aid


async def _job(tenant: uuid.UUID, agent: uuid.UUID | None = None) -> uuid.UUID:
    rows = await _exec(
        "INSERT INTO jobs (tenant_id, agent_id, kind) VALUES (:t, :a, 'agent_draft') RETURNING id",
        tenant=tenant,
        t=tenant,
        a=agent,
    )
    return rows[0][0]


@pytest.fixture
async def _clean() -> Any:
    yield
    await _exec("TRUNCATE TABLE jobs, agents, tenants, partners RESTART IDENTITY CASCADE")


async def test_jobs_is_forced_rls_with_a_tenant_policy(_clean: Any) -> None:
    rows = await _exec(
        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
        "WHERE relname = 'jobs' AND relnamespace = 'public'::regnamespace"
    )
    assert rows == [(True, True)]
    policies = await _exec(
        "SELECT qual, with_check FROM pg_policies WHERE tablename = 'jobs' AND schemaname = 'public'"
    )
    assert len(policies) == 1
    qual, with_check = policies[0]
    assert "app.tenant_id" in qual
    assert "app.tenant_id" in with_check


async def test_a_client_never_sees_or_writes_another_clients_job(_clean: Any) -> None:
    a, agent_a = await _tenant_with_agent()
    b, _ = await _tenant_with_agent()
    job_a = await _job(a, agent_a)

    assert await _exec("SELECT id FROM jobs WHERE id = :j", tenant=b, j=job_a) == []
    assert await _exec("SELECT id FROM jobs WHERE id = :j", tenant=a, j=job_a) == [(job_a,)]

    with pytest.raises(DBAPIError):  # WITH CHECK: B cannot write a row of A
        await _exec("INSERT INTO jobs (tenant_id, kind) VALUES (:t, 'client_read')", tenant=b, t=a)


async def test_the_agent_fk_is_composite(_clean: Any) -> None:
    a, _ = await _tenant_with_agent()
    _, agent_b = await _tenant_with_agent()

    with pytest.raises(IntegrityError):
        await _job(a, agent_b)


async def test_job_tenant_returns_only_the_client(_clean: Any) -> None:
    a, agent_a = await _tenant_with_agent()
    job_a = await _job(a, agent_a)

    # No tenant in context, as the console route calls it: still answers.
    rows = await _exec("SELECT set_config('role', 'nexus_app', true), job_tenant(:j)", j=job_a)
    assert rows[0][1] == a
    assert (await _exec("SELECT job_tenant(:j)", j=uuid.uuid4()))[0][0] is None


async def test_the_lifecycle_holds_in_the_database(_clean: Any) -> None:
    a, _ = await _tenant_with_agent()

    with pytest.raises(IntegrityError):  # finished without finished_at
        await _exec("INSERT INTO jobs (tenant_id, kind, status) VALUES (:t, 'tests', 'done')", t=a)
    with pytest.raises(IntegrityError):  # failed without a code
        await _exec(
            "INSERT INTO jobs (tenant_id, kind, status, finished_at) "
            "VALUES (:t, 'tests', 'failed', now())",
            t=a,
        )
    with pytest.raises(IntegrityError):  # a kind outside the catalogue
        await _exec("INSERT INTO jobs (tenant_id, kind) VALUES (:t, 'mine')", t=a)

    await _exec(
        "INSERT INTO jobs (tenant_id, kind, status, finished_at, error_code) "
        "VALUES (:t, 'tests', 'failed', now(), 'timeout')",
        t=a,
    )


async def test_partners_carry_the_console_v2_activation(_clean: Any) -> None:
    pid = uuid.uuid4()
    await _exec(
        "INSERT INTO partners (id, name, slug, status) VALUES (:i, 'P', :s, 'active')",
        i=pid,
        s=f"p-{pid.hex[:10]}",
    )
    rows = await _exec(
        "SELECT console_v2_enabled_at, console_v2_enabled_by FROM partners WHERE id = :i", i=pid
    )
    assert rows == [(None, None)]

    with pytest.raises(IntegrityError):  # «who» without «when»
        await _exec(
            "UPDATE partners SET console_v2_enabled_by = 'ana@auphere.com' WHERE id = :i", i=pid
        )
    await _exec(
        "UPDATE partners SET console_v2_enabled_at = now(), "
        "console_v2_enabled_by = 'ana@auphere.com' WHERE id = :i",
        i=pid,
    )
