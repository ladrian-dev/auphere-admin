"""Garantía 1 — RLS sobre la lista blanca, las máquinas y los vínculos.

Reescrito por la spec 002: la máquina pasa a ser **del partner** (RLS por partner y
por persona, en ``test_30``), y lo que sigue siendo dato de tenant —la lista blanca
y el vínculo máquina↔cliente con su directorio— se prueba aquí: un tenant no alcanza
las filas de otro **aunque la consulta no lleve ``WHERE tenant_id``**.

El nº 25 queda reservado a la VM compartida de la beta 5.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError

from nexus_api.db.models import DeviceClientLink, LocalExecutable, PartnerDevice

from .conftest import set_tenant

pytestmark = [pytest.mark.isolation, pytest.mark.asyncio]


async def _seed(session, console_world, label: str, *, executable: str) -> None:
    w = console_world[label]
    device = PartnerDevice(
        id=uuid.uuid4(),
        partner_id=w["partner_id"],
        principal_id=w["user_id"],
        display_name=f"mac de {label}",
        hostname=f"mac-{label}.local",
        platform="macos",
    )
    session.add(device)
    await session.flush()
    session.add_all(
        [
            LocalExecutable(
                id=uuid.uuid4(), tenant_id=w["tenant_id"], executable=executable, added_by="tester"
            ),
            DeviceClientLink(
                id=uuid.uuid4(),
                tenant_id=w["tenant_id"],
                device_id=device.id,
                workdir=f"/Users/{label}/proyecto",
                created_by=w["user_id"],
            ),
        ]
    )
    await session.flush()


async def test_allowlist_does_not_leak_across_tenants(db_session, console_world):
    await _seed(db_session, console_world, "a", executable="make")
    await _seed(db_session, console_world, "b", executable="pytest")
    await db_session.commit()

    await set_tenant(db_session, console_world["a"]["tenant_id"])
    rows = (await db_session.execute(select(LocalExecutable.executable))).scalars().all()
    assert set(rows) == {"make"}, "la lista blanca de otro tenant es alcanzable"


async def test_links_and_their_directories_do_not_leak_across_tenants(db_session, console_world):
    await _seed(db_session, console_world, "a", executable="make")
    await _seed(db_session, console_world, "b", executable="pytest")
    await db_session.commit()

    await set_tenant(db_session, console_world["b"]["tenant_id"])
    rows = (await db_session.execute(select(DeviceClientLink.workdir))).scalars().all()
    assert rows == ["/Users/b/proyecto"]


async def test_without_the_guc_there_are_no_rows(db_session, console_world):
    """Fail-closed: sin ``app.tenant_id`` no se ve nada, no se ve todo."""
    await _seed(db_session, console_world, "a", executable="make")
    await db_session.commit()

    await db_session.execute(text("SELECT set_config('app.tenant_id', '', true)"))
    await db_session.execute(text("SET LOCAL ROLE nexus_app"))
    assert (await db_session.execute(select(LocalExecutable.executable))).scalars().all() == []
    assert (await db_session.execute(select(DeviceClientLink.id))).scalars().all() == []


async def test_a_tenant_cannot_write_a_row_for_another(db_session, console_world):
    """``WITH CHECK``: ni siquiera insertando el ``tenant_id`` ajeno a mano."""
    a, b = console_world["a"], console_world["b"]
    await set_tenant(db_session, a["tenant_id"])
    db_session.add(
        LocalExecutable(
            id=uuid.uuid4(), tenant_id=b["tenant_id"], executable="curl", added_by="atacante"
        )
    )
    # ProgrammingError, no IntegrityError: la RLS no es una restricción de tabla —
    # Postgres lo rechaza como falta de privilegio sobre la fila.
    with pytest.raises(ProgrammingError):
        await db_session.flush()
