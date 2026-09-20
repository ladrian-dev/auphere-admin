"""El subdirectorio del comando sobrevive el viaje — D4 del bug del teammate.

`shell_local` acepta `cwd_relative` y la puerta lo **valida** contra fugas: ni
rutas absolutas, ni `~`, ni `..` (`local_exec_gate._escapes_workdir`). Y la
máquina sabe resolverlo dentro del directorio declarado
(`local-runner.ts` → `resolveDirInside`).

Entre medias no había nada: la fila de `local_executions` no tenía dónde
guardarlo y el poll mandaba `cwd_relative: None` escrito a mano. El resultado
era que **todo se ejecutaba en la raíz del directorio del cliente**, por muy
bien que el modelo pidiera otra cosa, y sin decírselo a nadie.

Validar un dato y después tirarlo es peor que no aceptarlo: el gate cobra el
precio de la comprobación y el producto no entrega la capacidad.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from nexus_api.core.tenant_context import tenant_context
from nexus_api.db.models.local_workstation import DeviceClientLink, PartnerDevice
from nexus_api.services.device_credential import issue_device_token
from nexus_api.services.local_dispatch import dispatch

pytestmark = pytest.mark.asyncio

SUBDIR = "analitica/informes"


async def _device_with_workdir(db_session, world) -> tuple[PartnerDevice, str]:
    device = PartnerDevice(
        id=uuid.uuid4(),
        partner_id=world["partner_id"],
        principal_id=world["user_id"],
        display_name="portátil",
        hostname="portatil.local",
        platform="macos",
        last_heartbeat_at=datetime.now(UTC),
    )
    db_session.add(device)
    await db_session.flush()
    db_session.add(
        DeviceClientLink(
            id=uuid.uuid4(),
            tenant_id=world["tenant_id"],
            device_id=device.id,
            created_by=world["user_id"],
            workdir="/Users/adrian/clientes/boreal",
        )
    )
    await db_session.commit()
    token = issue_device_token(device_id=device.id, partner_id=world["partner_id"], generation=1)
    return device, token


async def test_the_row_remembers_the_subdirectory(db_session, console_world):
    w = console_world["a"]
    device, _ = await _device_with_workdir(db_session, w)

    with tenant_context(w["tenant_id"]):
        row = await dispatch(
            db_session,
            device_id=device.id,
            executable="python",
            argv_signature='["analizar.py"]',
            cwd_relative=SUBDIR,
            grant_id=None,
            principal_id=w["user_id"],
            teammate_id=None,
            task_id=None,
        )
        await db_session.commit()

    assert row.cwd_relative == SUBDIR


async def test_the_machine_is_told_where_to_run(client, db_session, console_world):
    """Lo que de verdad importa: que llegue al otro lado."""
    w = console_world["a"]
    device, token = await _device_with_workdir(db_session, w)

    with tenant_context(w["tenant_id"]):
        await dispatch(
            db_session,
            device_id=device.id,
            executable="python",
            argv_signature='["analizar.py"]',
            cwd_relative=SUBDIR,
            grant_id=None,
            principal_id=w["user_id"],
            teammate_id=None,
            task_id=None,
        )
        await db_session.commit()

    polled = (await client.get("/device/poll", headers={"Authorization": f"Bearer {token}"})).json()

    assert len(polled["work"]) == 1, polled
    assert polled["work"][0]["cwd_relative"] == SUBDIR, (
        "el comando va a correr en la raíz del directorio, no donde se pidió"
    )


async def test_no_subdirectory_still_means_the_root(client, db_session, console_world):
    """Sin subdirectorio, `None` es la respuesta correcta y no una ausencia de dato."""
    w = console_world["a"]
    device, token = await _device_with_workdir(db_session, w)

    with tenant_context(w["tenant_id"]):
        await dispatch(
            db_session,
            device_id=device.id,
            executable="make",
            argv_signature="[]",
            cwd_relative=None,
            grant_id=None,
            principal_id=w["user_id"],
            teammate_id=None,
            task_id=None,
        )
        await db_session.commit()

    polled = (await client.get("/device/poll", headers={"Authorization": f"Bearer {token}"})).json()
    assert polled["work"][0]["cwd_relative"] is None
