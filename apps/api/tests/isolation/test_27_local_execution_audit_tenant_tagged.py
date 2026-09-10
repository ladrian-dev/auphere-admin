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
    """Spec 002: la máquina es del partner del tenant; el directorio, un vínculo."""
    from nexus_api.db.models import DeviceClientLink, Partner, Tenant

    tenant = await session.get(Tenant, tenant_id)
    if tenant.partner_id is None:
        partner = Partner(id=uuid.uuid4(), name="Iso Partner", slug=f"isop-{uuid.uuid4().hex[:6]}")
        session.add(partner)
        await session.flush()
        tenant.partner_id = partner.id
        await session.flush()
    device_id = uuid.uuid4()
    session.add(
        PartnerDevice(
            id=device_id,
            partner_id=tenant.partner_id,
            principal_id="user_iso",
            display_name="portátil",
            hostname="portatil.local",
            platform="macos",
        )
    )
    await session.flush()
    session.add(
        DeviceClientLink(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            device_id=device_id,
            workdir="/tmp/proyecto",
            created_by="user_iso",
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


# ── spec 002: los actos de identidad de una máquina, etiquetados (R13) ──────


async def test_identity_acts_are_tagged_with_partner_and_person(client, db_session, console_world):
    """Garantía 6 para los actos de identidad: cada asiento nombra al partner en
    ``target`` y a la persona —o a la máquina— en ``actor``; y ningún asiento de
    A aparece en la auditoría de B."""
    from sqlalchemy import select

    from nexus_api.db.models import AuditLog

    a, b = console_world["a"], console_world["b"]
    issued = await client.post("/console/workstation/pairing-codes", headers=a["headers"]())
    paired = await client.post(
        "/device/pair",
        json={"code": issued.json()["code"], "hostname": "mac.local", "platform": "macos"},
    )
    assert paired.status_code == 201
    token = paired.json()["credential"]
    await client.post("/device/renew", headers={"Authorization": f"Bearer {token}"})
    await client.delete(
        f"/console/workstation/devices/{paired.json()['device_id']}", headers=a["headers"]()
    )

    rows = (
        (await db_session.execute(select(AuditLog).where(AuditLog.action.like("device.%"))))
        .scalars()
        .all()
    )
    actions = {r.action for r in rows}
    assert {
        "device.pair_code_issued",
        "device.paired",
        "device.renewed",
        "device.archived",
    } <= actions
    for row in rows:
        assert row.target == f"partner:{a['partner_id']}", row.action
        assert row.actor.startswith(("console:", "device:")), row.actor
    renewed = next(r for r in rows if r.action == "device.renewed")
    assert renewed.actor == f"device:{paired.json()['device_id']}"

    # La auditoría de B no ve nada de esto (la de consola filtra por partner).
    audit_b = await client.get("/console/audit", headers=b["headers"]())
    assert audit_b.status_code == 200, audit_b.text
    body = audit_b.json()
    items = body["items"] if isinstance(body, dict) else body
    assert all(not str(item.get("action", "")).startswith("device.") for item in items)
