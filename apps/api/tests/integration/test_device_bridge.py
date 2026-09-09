"""El puente, de extremo a extremo — Requisitos 6.1, 6.3 y 4.1.

Recorre lo que hace una máquina real: se da de alta, recibe su credencial, late,
sondea y devuelve un resultado. Lo que se comprueba en cada paso no es que
responda 200 — es la propiedad que hace que el paso sea correcto.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from nexus_api.core.tenant_context import tenant_context
from nexus_api.db.models import LocalExecution, PartnerDevice, Tenant, TenantPlan
from nexus_api.repositories.local_workstation import PartnerDeviceRepository
from nexus_api.services.device_credential import issue_device_token, verify_device_token
from nexus_api.services.device_presence import derive_presence

pytestmark = pytest.mark.asyncio


async def _tenant(session) -> uuid.UUID:
    tenant_id = uuid.uuid4()
    session.add(
        Tenant(id=tenant_id, name="Bridge", slug=f"br-{tenant_id.hex[:6]}", plan=TenantPlan.PRO)
    )
    await session.commit()
    await session.execute(
        text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
    )
    return tenant_id


async def test_enrolment_gives_the_device_a_credential_that_names_it(db_session):
    tenant_id = await _tenant(db_session)
    with tenant_context(tenant_id):
        device = await PartnerDeviceRepository(db_session).enrol(
            principal_id="user_bridge",
            display_name="portátil",
            platform="macos",
            workdir="/tmp/proyecto",
        )
    token = issue_device_token(device_id=device.id, tenant_id=tenant_id)
    claims = verify_device_token(token)
    assert claims.device_id == device.id
    assert claims.tenant_id == tenant_id


async def test_the_heartbeat_moves_the_heartbeat_and_nothing_else(db_session):
    """Si moviera algo más, habría un estado que puede quedar desincronizado."""
    tenant_id = await _tenant(db_session)
    with tenant_context(tenant_id):
        repo = PartnerDeviceRepository(db_session)
        device = await repo.enrol(
            principal_id="user_bridge",
            display_name="portátil",
            platform="macos",
            workdir="/tmp/proyecto",
        )
        before = {
            c.name: getattr(device, c.name)
            for c in PartnerDevice.__table__.columns
            if c.name != "last_heartbeat_at"
        }
        assert derive_presence(device.last_heartbeat_at) == "ausente"

        await repo.record_heartbeat(device.id)

        after = {
            c.name: getattr(device, c.name)
            for c in PartnerDevice.__table__.columns
            if c.name != "last_heartbeat_at"
        }
    assert before == after, "el latido tocó algo más que su propia columna"
    assert derive_presence(device.last_heartbeat_at) == "presente"


async def test_a_result_closes_the_audit_entry(db_session):
    from nexus_api.repositories.local_workstation import LocalExecutionRepository

    tenant_id = await _tenant(db_session)
    with tenant_context(tenant_id):
        device = await PartnerDeviceRepository(db_session).enrol(
            principal_id="user_bridge",
            display_name="portátil",
            platform="macos",
            workdir="/tmp/proyecto",
        )
        repo = LocalExecutionRepository(db_session)
        row = await repo.start(
            device_id=device.id, executable="make", argv_signature='["build"]', grant_id=None
        )
        assert row.ended_at is None

        await repo.finish(row.id, outcome="expirada", exit_code=None, children_reaped=2)

        closed = await db_session.get(LocalExecution, row.id)
    assert closed is not None
    assert closed.outcome == "expirada"
    assert closed.ended_at is not None
    assert closed.children_reaped == 2


async def test_the_result_has_nowhere_to_carry_the_command_output(db_session):
    """La garantía sigue siendo estructural en este extremo también."""
    from nexus_api.api.device_bridge import ResultIn

    assert "stdout" not in ResultIn.model_fields
    assert "output" not in ResultIn.model_fields
    assert set(ResultIn.model_fields) == {
        "execution_id",
        "outcome",
        "exit_code",
        "children_reaped",
    }
