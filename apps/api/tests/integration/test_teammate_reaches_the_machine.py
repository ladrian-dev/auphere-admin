"""El teammate tiene que poder alcanzar la máquina de su persona.

La spec 003 dejó construido el camino entero —emparejamiento, puente saliente,
contención de escrituras con sus seis ataques, política en tres capas, tarjeta
de aprobación— y **nadie podía recorrerlo**: los dos sitios que montan el
catálogo de un teammate pasaban ``machine_present=False`` escrito a mano, y
``for_teammate`` solo publica ``shell_local`` cuando ese valor es verdadero.

Con la herramienta fuera del catálogo, el modelo ni siquiera puede intentarlo.
Eso es lo correcto **cuando la máquina no está** (001-R4.2: que no pueda
intentarlo es lo que impide que afirme resultados de comandos que nunca
ejecutó). El defecto era que valía siempre.

Y había una segunda mitad, más callada: el módulo que sabe decidir esto
—``services/device_presence``— tenía escritas ``tenant_presence`` y
``catalog_includes_local_tools`` **sin un solo llamador**. El mecanismo existía,
documentado contra su requisito, y no lo invocaba nadie.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.db.models.local_workstation import DeviceClientLink, PartnerDevice
from nexus_api.services.device_presence import PRESENCE_EXPIRY, principal_presence
from nexus_api.services.teammate_catalog import MACHINE_TOOL

pytestmark = pytest.mark.asyncio


async def _machine(
    db_session,
    world,
    *,
    beat: datetime | None,
    workdir: str | None = "/Users/adrian/clientes/boreal",
    revoked: bool = False,
) -> PartnerDevice:
    """Una máquina de esta persona, vinculada a un cliente del partner."""
    device = PartnerDevice(
        id=uuid.uuid4(),
        partner_id=world["partner_id"],
        principal_id=world["user_id"],
        display_name="portátil",
        hostname="portatil.local",
        platform="macos",
        last_heartbeat_at=beat,
        revoked_at=datetime.now(UTC) if revoked else None,
    )
    db_session.add(device)
    await db_session.flush()
    db_session.add(
        DeviceClientLink(
            id=uuid.uuid4(),
            device_id=device.id,
            tenant_id=world["tenant_id"],
            workdir=workdir,
            created_by=world["user_id"],
        )
    )
    await db_session.commit()
    return device


async def _present(db_session, world) -> bool:
    """Bajo los GUC del partner, que es donde la RLS filtra por persona."""
    await apply_partner_to_session(db_session, world["partner_id"], principal_id=world["user_id"])
    return await principal_presence(db_session) == "presente"


# ── la presencia, derivada del latido ──────────────────────────────────


async def test_a_machine_beating_now_is_present(db_session, console_world):
    w = console_world["a"]
    await _machine(db_session, w, beat=datetime.now(UTC))
    assert await _present(db_session, w) is True


async def test_a_machine_that_stopped_beating_is_absent(db_session, console_world):
    """Sin columna de estado: la mentira «conectada» es imposible, no improbable."""
    w = console_world["a"]
    await _machine(db_session, w, beat=datetime.now(UTC) - PRESENCE_EXPIRY - timedelta(seconds=5))
    assert await _present(db_session, w) is False


async def test_a_machine_without_a_declared_directory_is_not_usable(db_session, console_world):
    """002-R7.5: sin directorio no hay dónde ejecutar. Es una espera diseñada."""
    w = console_world["a"]
    await _machine(db_session, w, beat=datetime.now(UTC), workdir=None)
    assert await _present(db_session, w) is False


async def test_a_revoked_machine_does_not_count(db_session, console_world):
    w = console_world["a"]
    await _machine(db_session, w, beat=datetime.now(UTC), revoked=True)
    assert await _present(db_session, w) is False


async def test_no_machine_at_all_is_absent(db_session, console_world):
    assert await _present(db_session, console_world["a"]) is False


# ── y lo que decide de verdad: qué ve el modelo ────────────────────────


@pytest.mark.parametrize("present", [True, False])
async def test_the_catalog_follows_the_machine(present: bool):
    """La prueba de que el valor **se usa**, y no está escrito a mano."""
    from types import SimpleNamespace

    from nexus_api.services.teammate_catalog import for_teammate

    teammate = SimpleNamespace(
        tool_names=["console.get_usage"],
        local_exec=True,
        name="Sofía",
        job="analista",
    )
    names = for_teammate(teammate, mode="work", machine_present=present)
    assert (MACHINE_TOOL in names) is present


async def test_a_teammate_without_local_exec_never_gets_it():
    """``shell_local`` no entra por ningún interruptor de permisos: depende de
    ``local_exec`` **y** de la máquina. Un teammate con permiso de escritura no
    se lleva de propina el ordenador de nadie."""
    from types import SimpleNamespace

    from nexus_api.services.teammate_catalog import for_teammate

    teammate = SimpleNamespace(
        tool_names=["console.get_usage"],
        local_exec=False,
        name="Vera",
        job="finanzas",
    )
    assert MACHINE_TOOL not in for_teammate(teammate, mode="work", machine_present=True)
