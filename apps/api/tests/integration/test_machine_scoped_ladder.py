"""Requisito 7.2 — lo que se queda en la máquina **no consume** aprobación durable.

Que las dos escaleras existan no basta: hay que comprobar que la cara no se gasta
donde no toca. Si cada comando local abriera una acción durable, la bandeja de
aprobaciones del partner se llenaría de ruido y la señal que importa —«esto toca a
un cliente tuyo»— se perdería entre cientos de `make build`.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select, text

from nexus_api.core.tenant_context import tenant_context
from nexus_api.db.models import LocalExecutable, PartnerDevice, Tenant, TenantPlan
from nexus_api.db.models.companion import CompanionAction
from nexus_api.repositories.local_workstation import LocalArgumentGrantRepository
from nexus_api.services.action_scope import ActionScope, classify_tool
from nexus_api.services.local_exec_gate import LocalExecGate, argv_signature

pytestmark = pytest.mark.asyncio


async def _setup(session) -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id, executable_id = uuid.uuid4(), uuid.uuid4()
    session.add(
        Tenant(id=tenant_id, name="Ladder", slug=f"ld-{tenant_id.hex[:6]}", plan=TenantPlan.PRO)
    )
    await session.flush()
    session.add_all(
        [
            LocalExecutable(
                id=executable_id, tenant_id=tenant_id, executable="make", added_by="tester"
            ),
            PartnerDevice(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                principal_id="user_ladder",
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
    return tenant_id, executable_id


async def test_a_local_command_opens_no_durable_action(db_session):
    tenant_id, executable_id = await _setup(db_session)
    before = (await db_session.execute(select(func.count()).select_from(CompanionAction))).scalar()

    with tenant_context(tenant_id):
        gate = LocalExecGate(db_session)
        decision = await gate.evaluate(executable="make", args=["build"])
        assert decision.outcome == "requiere_aprobacion"
        # La aprobación de argumentos referencia una acción, pero el permiso en sí
        # no crea ninguna: quien la crea es la escalera que corresponda.
        await LocalArgumentGrantRepository(db_session).grant(
            executable_id=executable_id,
            argv_signature=argv_signature(["build"]),
            action_id=uuid.uuid4(),
        )

    after = (await db_session.execute(select(func.count()).select_from(CompanionAction))).scalar()
    assert after == before, "un comando local no debe llenar la bandeja de aprobaciones"


async def test_the_local_tool_is_classified_as_machine_scoped(db_session):
    assert classify_tool("shell_local") is ActionScope.MACHINE
