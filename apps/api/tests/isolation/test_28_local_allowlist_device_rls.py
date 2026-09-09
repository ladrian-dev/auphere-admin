"""Garantía 1 — RLS sobre la lista blanca y los dispositivos (migración 0106).

La superficie 3a añade cuatro tablas por tenant. Este fichero comprueba lo que §I
exige de ellas: que un tenant no alcanza las filas de otro **aunque la consulta no
lleve ``WHERE tenant_id``**, porque quien filtra es Postgres y no un WHERE que
alguien pueda olvidar.

El nº 25 queda reservado a la VM compartida de la beta 5.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError

from nexus_api.db.models import LocalExecutable, PartnerDevice

from .conftest import set_tenant

pytestmark = [pytest.mark.isolation, pytest.mark.asyncio]


async def _seed(session, tenant_id: uuid.UUID, *, executable: str, device_name: str) -> None:
    session.add_all(
        [
            LocalExecutable(
                id=uuid.uuid4(), tenant_id=tenant_id, executable=executable, added_by="tester"
            ),
            PartnerDevice(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                principal_id=uuid.uuid4(),
                display_name=device_name,
                platform="macos",
                workdir="/tmp/proyecto",
            ),
        ]
    )
    await session.flush()


async def test_allowlist_does_not_leak_across_tenants(db_session, tenants_ab):
    await _seed(db_session, tenants_ab["a"], executable="make", device_name="mac de A")
    await _seed(db_session, tenants_ab["b"], executable="pytest", device_name="pc de B")
    await db_session.commit()

    await set_tenant(db_session, tenants_ab["a"])
    rows = (await db_session.execute(select(LocalExecutable.executable))).scalars().all()
    assert set(rows) == {"make"}, "la lista blanca de otro tenant es alcanzable"


async def test_devices_do_not_leak_across_tenants(db_session, tenants_ab):
    await _seed(db_session, tenants_ab["a"], executable="make", device_name="mac de A")
    await _seed(db_session, tenants_ab["b"], executable="pytest", device_name="pc de B")
    await db_session.commit()

    await set_tenant(db_session, tenants_ab["b"])
    rows = (await db_session.execute(select(PartnerDevice.display_name))).scalars().all()
    assert set(rows) == {"pc de B"}


async def test_without_the_guc_there_are_no_rows(db_session, tenants_ab):
    """Fail-closed: sin ``app.tenant_id`` no se ve nada, no se ve todo."""
    await _seed(db_session, tenants_ab["a"], executable="make", device_name="mac de A")
    await db_session.commit()

    await db_session.execute(text("SELECT set_config('app.tenant_id', '', true)"))
    await db_session.execute(text("SET LOCAL ROLE nexus_app"))
    rows = (await db_session.execute(select(LocalExecutable.executable))).scalars().all()
    assert rows == []


async def test_a_tenant_cannot_write_a_row_for_another(db_session, tenants_ab):
    """``WITH CHECK``: ni siquiera insertando el ``tenant_id`` ajeno a mano."""
    await set_tenant(db_session, tenants_ab["a"])
    db_session.add(
        LocalExecutable(
            id=uuid.uuid4(), tenant_id=tenants_ab["b"], executable="curl", added_by="atacante"
        )
    )
    # ProgrammingError, no IntegrityError: la RLS no es una restricción de tabla —
    # Postgres lo rechaza como falta de privilegio sobre la fila.
    with pytest.raises(ProgrammingError):
        await db_session.flush()
