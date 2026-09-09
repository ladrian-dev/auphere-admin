"""Requisito 8 — cada intento queda registrado, y la salida no.

Lo que hace útil a esta auditoría en un incidente es que registre **también lo
que no llegó a correr**: la pregunta de un incidente es casi siempre «¿esto se
intentó?». Y lo que la hace legítima es que no guarde la salida: eso es
contenido leído (§III) y el hilo de un teammate no transcribe texto de cliente
final.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text

from nexus_api.core.tenant_context import tenant_context
from nexus_api.db.models import LocalExecutable, LocalExecution, PartnerDevice, Tenant, TenantPlan
from nexus_api.db.models.local_workstation import DENIAL_EJECUTABLE_NO_PERMITIDO
from nexus_api.services.local_exec_gate import LocalExecGate
from nexus_api.services.local_execution_recorder import record_decision

pytestmark = pytest.mark.asyncio


async def _setup(session) -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id, device_id = uuid.uuid4(), uuid.uuid4()
    session.add(
        Tenant(id=tenant_id, name="Audit", slug=f"au-{tenant_id.hex[:6]}", plan=TenantPlan.PRO)
    )
    await session.flush()
    session.add_all(
        [
            LocalExecutable(
                id=uuid.uuid4(), tenant_id=tenant_id, executable="make", added_by="tester"
            ),
            PartnerDevice(
                id=device_id,
                tenant_id=tenant_id,
                principal_id="user_audit",
                display_name="portátil",
                platform="macos",
                workdir="/tmp/proyecto",
            ),
        ]
    )
    await session.commit()
    await session.execute(
        text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
    )
    return tenant_id, device_id


async def test_a_denial_is_recorded_with_its_code(db_session):
    tenant_id, device_id = await _setup(db_session)
    with tenant_context(tenant_id):
        decision = await LocalExecGate(db_session).evaluate(executable="curl", args=[])
        row = await record_decision(db_session, decision=decision, device_id=device_id)

    assert row is not None
    assert row.outcome == "denegada"
    assert row.denial_reason == DENIAL_EJECUTABLE_NO_PERMITIDO
    assert row.executable == "curl", "se guarda lo que se intentó, no lo que estaba permitido"


async def test_an_approval_request_is_not_yet_an_execution(db_session):
    """Pedir permiso no es haber ejecutado: no se inventa un asiento."""
    tenant_id, device_id = await _setup(db_session)
    with tenant_context(tenant_id):
        decision = await LocalExecGate(db_session).evaluate(executable="make", args=["build"])
        assert decision.outcome == "requiere_aprobacion"
        row = await record_decision(db_session, decision=decision, device_id=device_id)

    assert row is None
    rows = (await db_session.execute(select(LocalExecution))).scalars().all()
    assert rows == []


async def test_the_audit_has_nowhere_to_put_command_output(db_session):
    """La garantía es estructural: no hay columna donde guardar la salida."""
    columns = {c.name for c in LocalExecution.__table__.columns}
    assert "stdout" not in columns
    assert "output" not in columns
    assert "content" not in columns
