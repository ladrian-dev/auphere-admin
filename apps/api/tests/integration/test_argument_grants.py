"""Requisitos 2.3 y 2.5 — los argumentos sí se aprueban, y el permiso es durable.

El permiso apunta a ``companion.actions``, que es donde viven ``state_hash``,
``decided_at`` y ``decided_by``. Aquí **no** se duplica ninguno de los tres: habría dos
sitios donde mirar quién aprobó qué, y en una auditoría eso es peor que uno solo.

Lo que sí se prueba aquí es lo que este lado posee: que el permiso es idempotente por
construcción —uuid5 determinista sobre `(tenant, ejecutable, firma)` + UPSERT— para
que dos aprobaciones simultáneas no creen dos filas, y que **una firma distinta es un
permiso distinto**.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from nexus_api.core.tenant_context import tenant_context
from nexus_api.db.models import LocalExecutable, Tenant, TenantPlan
from nexus_api.repositories.local_workstation import (
    LocalArgumentGrantRepository,
    grant_id_for,
)
from nexus_api.services.local_exec_gate import LocalExecGate, argv_signature

pytestmark = pytest.mark.asyncio


async def _setup(session) -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id, executable_id = uuid.uuid4(), uuid.uuid4()
    session.add(
        Tenant(id=tenant_id, name="Grants", slug=f"gr-{tenant_id.hex[:6]}", plan=TenantPlan.PRO)
    )
    await session.flush()
    session.add(
        LocalExecutable(id=executable_id, tenant_id=tenant_id, executable="make", added_by="tester")
    )
    await session.commit()
    await session.execute(
        text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
    )
    return tenant_id, executable_id


async def test_granting_turns_approval_into_permission(db_session):
    tenant_id, executable_id = await _setup(db_session)
    args = ["build", "--release"]

    with tenant_context(tenant_id):
        gate = LocalExecGate(db_session)
        assert (await gate.evaluate(executable="make", args=args)).outcome == "requiere_aprobacion"

        await LocalArgumentGrantRepository(db_session).grant(
            executable_id=executable_id,
            argv_signature=argv_signature(args),
            action_id=uuid.uuid4(),
        )
        assert (await gate.evaluate(executable="make", args=args)).outcome == "permitida"


async def test_the_grant_is_idempotent_under_a_race(db_session):
    """Dos aprobaciones simultáneas no pueden crear dos permisos."""
    tenant_id, executable_id = await _setup(db_session)
    signature = argv_signature(["build"])
    repo = LocalArgumentGrantRepository(db_session)

    with tenant_context(tenant_id):
        first = await repo.grant(
            executable_id=executable_id, argv_signature=signature, action_id=uuid.uuid4()
        )
        second = await repo.grant(
            executable_id=executable_id, argv_signature=signature, action_id=uuid.uuid4()
        )

    assert first == second == grant_id_for(tenant_id, executable_id, signature)


async def test_a_different_signature_is_a_different_permission(db_session):
    """Aprobar ``make build`` no aprueba ``make deploy``."""
    tenant_id, executable_id = await _setup(db_session)

    with tenant_context(tenant_id):
        await LocalArgumentGrantRepository(db_session).grant(
            executable_id=executable_id,
            argv_signature=argv_signature(["build"]),
            action_id=uuid.uuid4(),
        )
        gate = LocalExecGate(db_session)
        assert (await gate.evaluate(executable="make", args=["build"])).outcome == "permitida"
        assert (
            await gate.evaluate(executable="make", args=["deploy"])
        ).outcome == "requiere_aprobacion"


async def test_argument_splitting_changes_the_signature(db_session):
    """``["a b"]`` y ``["a","b"]`` son invocaciones distintas y firman distinto."""
    assert argv_signature(["a b"]) != argv_signature(["a", "b"])
