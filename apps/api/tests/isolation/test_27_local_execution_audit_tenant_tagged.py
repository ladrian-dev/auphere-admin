"""Garantía 6 — la ejecución local queda etiquetada por tenant, y también la denegada.

Una auditoría que solo registra lo que salió bien no sirve para responder a un
incidente: la pregunta de un incidente es casi siempre *«¿esto se intentó?»*. Por eso
el Requisito 8.3 exige registrar la denegación con su motivo, y la base lo respalda
con un CHECK — una denegación sin motivo no se puede ni guardar.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from nexus_api.db.models import LocalExecution, PartnerDevice
from nexus_api.db.models.local_workstation import (
    DENIAL_EJECUTABLE_NO_PERMITIDO,
    OUTCOME_COMPLETADA,
    OUTCOME_DENEGADA,
)

from .conftest import set_tenant

pytestmark = [pytest.mark.isolation, pytest.mark.asyncio]


async def _device(session, tenant_id: uuid.UUID) -> uuid.UUID:
    device_id = uuid.uuid4()
    session.add(
        PartnerDevice(
            id=device_id,
            tenant_id=tenant_id,
            principal_id="user_iso",
            display_name="portátil",
            platform="macos",
            workdir="/tmp/proyecto",
        )
    )
    await session.flush()
    return device_id


async def test_executions_do_not_leak_across_tenants(db_session, tenants_ab):
    for key, executable in (("a", "make"), ("b", "pytest")):
        device_id = await _device(db_session, tenants_ab[key])
        db_session.add(
            LocalExecution(
                id=uuid.uuid4(),
                tenant_id=tenants_ab[key],
                device_id=device_id,
                executable=executable,
                argv_signature="[]",
                outcome=OUTCOME_COMPLETADA,
            )
        )
    await db_session.commit()

    await set_tenant(db_session, tenants_ab["a"])
    rows = (await db_session.execute(select(LocalExecution.executable))).scalars().all()
    assert set(rows) == {"make"}


async def test_a_denial_is_recorded_with_its_reason(db_session, tenants_ab):
    device_id = await _device(db_session, tenants_ab["a"])
    db_session.add(
        LocalExecution(
            id=uuid.uuid4(),
            tenant_id=tenants_ab["a"],
            device_id=device_id,
            executable="curl",
            argv_signature="['x']",
            outcome=OUTCOME_DENEGADA,
            denial_reason=DENIAL_EJECUTABLE_NO_PERMITIDO,
        )
    )
    await db_session.commit()

    await set_tenant(db_session, tenants_ab["a"])
    row = (
        await db_session.execute(
            select(LocalExecution).where(LocalExecution.outcome == OUTCOME_DENEGADA)
        )
    ).scalar_one()
    assert row.denial_reason == DENIAL_EJECUTABLE_NO_PERMITIDO
    assert row.tenant_id == tenants_ab["a"]


async def test_a_denial_without_a_reason_cannot_be_stored(db_session, tenants_ab):
    """El CHECK de la base impide una denegación que nadie pueda auditar."""
    device_id = await _device(db_session, tenants_ab["a"])
    db_session.add(
        LocalExecution(
            id=uuid.uuid4(),
            tenant_id=tenants_ab["a"],
            device_id=device_id,
            executable="curl",
            argv_signature="[]",
            outcome=OUTCOME_DENEGADA,
            denial_reason=None,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_an_unknown_denial_reason_is_refused(db_session, tenants_ab):
    """Vocabulario cerrado: un motivo que nadie diseñó no entra."""
    device_id = await _device(db_session, tenants_ab["a"])
    db_session.add(
        LocalExecution(
            id=uuid.uuid4(),
            tenant_id=tenants_ab["a"],
            device_id=device_id,
            executable="curl",
            argv_signature="[]",
            outcome=OUTCOME_DENEGADA,
            denial_reason="porque_si",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
