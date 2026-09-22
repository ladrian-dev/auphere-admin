"""Registrar la máquina con la sesión — spec 012, Requisito 3.

Sustituye al canje del código de ocho símbolos. La diferencia no es el
resultado —la misma credencial, para la misma máquina, de la misma persona—
sino quién demuestra tener derecho a pedirla: antes un código tecleado, ahora la
sesión que la aplicación ya tenía.

Dos bloques merecen leerse antes de tocar nada:

* **La frescura** sale del momento en que la sesión se **abrió**, no del último
  uso. Son cosas distintas y confundirlas es un error silencioso: tener la
  aplicación abierta movería `last_used_at` y haría pasar por «recién
  confirmada» una sesión de hace seis días, que es justo el caso que el umbral
  existe para atajar.

* **El rechazo es uniforme para los cuatro motivos**, y el cuarto —estar en el
  tope— es el que se cuela. Decir «tienes cinco máquinas» parece amable y es
  contar de más a quien todavía no ha demostrado ser nadie.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from nexus_api.core.workstation_limits import MAX_ACTIVE_MACHINES_PER_PRINCIPAL
from nexus_api.db.models import AuditLog, PartnerDevice, PartnerMembership
from nexus_api.db.models.console_identity import ConsoleAccount, ConsoleSession
from nexus_api.services import console_identity
from tests.conftest import add_console_member, console_headers

pytestmark = pytest.mark.asyncio

INSTALL = "install-de-esta-maquina"


async def _person(db_session, console_world, label: str = "a") -> ConsoleAccount:
    """Una persona real del partner, con su membresía apuntando a ella.

    Reapuntar la membresía es lo que hace que el `principal_id` del token sea
    una cuenta de consola de verdad, que es lo que la frescura necesita mirar.
    Y por eso los encabezados se rehacen: los de `console_world` llevan el
    `user_id` de antes, y con ése no hay membresía.
    """
    world = console_world[label]
    account = await console_identity.create_account(
        db_session,
        email=f"reg-{uuid.uuid4().hex[:8]}@example.com",
        password="una-contrasena-larga",
        display_name="Quien registra",
    )
    await db_session.commit()
    await db_session.execute(
        sa.update(PartnerMembership)
        .where(PartnerMembership.partner_id == world["partner_id"])
        .values(user_id=str(account.id), email=account.email)
    )
    await db_session.commit()
    world["headers"] = lambda **kw: console_headers(
        user_id=str(account.id), partner_id=world["partner_id"], **kw
    )
    return account


def _body(**over: object) -> dict[str, object]:
    return {
        "hostname": "mac-de-prueba.local",
        "platform": "macos",
        "install_id": INSTALL,
        **over,
    }


async def _open_session(db_session, account: ConsoleAccount) -> str:
    token, _ = await console_identity.start_session(db_session, account)
    await db_session.commit()
    return token


async def _age_session(db_session, account: ConsoleAccount, *, hours: float) -> None:
    """Envejece la **apertura** de la sesión, no su último uso.

    La API no ve la cookie —recibe el token de servicio del BFF—, así que la
    frescura se mira por persona: ¿tiene alguna sesión abierta hace poco? Si la
    tiene, es que confirmó quién era hace poco, que es lo que el requisito
    pregunta.
    """
    await db_session.execute(
        sa.update(ConsoleSession)
        .where(ConsoleSession.principal_id == account.id)
        .values(created_at=datetime.now(UTC) - timedelta(hours=hours))
    )
    await db_session.commit()


# ── el camino ──────────────────────────────────────────────────────────


async def test_a_confirmed_session_registers_the_machine(client, db_session, console_world):
    a = console_world["a"]
    account = await _person(db_session, console_world)
    await _open_session(db_session, account)

    done = await client.post("/console/workstation/machines", json=_body(), headers=a["headers"]())

    assert done.status_code == 201, done.text
    body = done.json()
    assert body["credential"]
    assert body["device_id"]
    row = (
        await db_session.execute(
            sa.select(PartnerDevice).where(PartnerDevice.principal_id == str(account.id))
        )
    ).scalar_one()
    assert row.install_id == INSTALL


async def test_registering_twice_from_the_same_machine_returns_the_same_one(
    client, db_session, console_world
):
    """R3.7. Con registro silencioso esto pasa de raro a frecuente.

    Y la clave es el identificador de instalación, no el nombre: renombrar el
    ordenador no puede crear una máquina nueva.
    """
    a = console_world["a"]
    account = await _person(db_session, console_world)
    await _open_session(db_session, account)

    first = await client.post("/console/workstation/machines", json=_body(), headers=a["headers"]())
    second = await client.post(
        "/console/workstation/machines",
        json=_body(hostname="mac-con-otro-nombre.local"),
        headers=a["headers"](),
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["device_id"] == second.json()["device_id"]
    count = (
        await db_session.execute(
            sa.select(sa.func.count())
            .select_from(PartnerDevice)
            .where(PartnerDevice.principal_id == str(account.id))
        )
    ).scalar_one()
    assert count == 1


async def test_registering_leaves_an_audit_trail(client, db_session, console_world):
    a = console_world["a"]
    account = await _person(db_session, console_world)
    await _open_session(db_session, account)

    await client.post("/console/workstation/machines", json=_body(), headers=a["headers"]())

    rows = (
        (await db_session.execute(sa.select(AuditLog).where(AuditLog.action == "device.paired")))
        .scalars()
        .all()
    )
    assert len(rows) == 1


# ── la frescura, que es la razón de elegir la Opción B ──────────────────


async def test_a_session_opened_long_ago_is_refused(client, db_session, console_world):
    a = console_world["a"]
    account = await _person(db_session, console_world)
    await _open_session(db_session, account)
    await _age_session(db_session, account, hours=3)

    refused = await client.post(
        "/console/workstation/machines", json=_body(), headers=a["headers"]()
    )

    assert refused.status_code == 401, refused.text


async def test_using_the_app_does_not_make_an_old_session_fresh(client, db_session, console_world):
    """El error silencioso que este test existe para cazar.

    Si la frescura saliera de `last_used_at`, tener la aplicación abierta la
    renovaría sola y una sesión de hace seis días pasaría por recién
    confirmada — que es exactamente el caso que el umbral atajaba.
    """
    a = console_world["a"]
    account = await _person(db_session, console_world)
    await _open_session(db_session, account)
    await _age_session(db_session, account, hours=144)
    # Y la usa ahora mismo, que es lo que hace cualquiera con la app abierta.
    await db_session.execute(
        sa.update(ConsoleSession)
        .where(ConsoleSession.principal_id == account.id)
        .values(last_used_at=datetime.now(UTC))
    )
    await db_session.commit()

    refused = await client.post(
        "/console/workstation/machines", json=_body(), headers=a["headers"]()
    )

    assert refused.status_code == 401, refused.text


# ── los rechazos: cada uno dice lo que ayuda, y nada más ───────────────


async def test_the_two_session_refusals_are_indistinguishable(client, db_session, console_world):
    """«No hay sesión» y «la sesión caducó» dan lo mismo.

    Es lo único que de verdad se hereda del rechazo indistinguible de la spec
    009: las dos llevan al mismo sitio —entrar de nuevo—, así que separarlas
    añade un detalle sin uso.

    Lo que **no** se hereda es uniformar el permiso y el tope. Aquel rechazo
    protege el canje de un código, donde quien llama es un desconocido que puede
    probar hasta acertar. Aquí quien llama ya presentó su sesión y su membresía,
    y los motivos son sobre sí mismo.
    """
    a = console_world["a"]
    account = await _person(db_session, console_world)

    sin_sesion = await client.post(
        "/console/workstation/machines", json=_body(), headers=a["headers"]()
    )

    await _open_session(db_session, account)
    await _age_session(db_session, account, hours=3)
    caducada = await client.post(
        "/console/workstation/machines", json=_body(), headers=a["headers"]()
    )

    assert sin_sesion.status_code == caducada.status_code == 401
    assert sin_sesion.text == caducada.text


async def test_the_cap_says_it_is_the_cap(client, db_session, console_world):
    """Porque saberlo es lo que le dice qué hacer: retirar una."""
    a = console_world["a"]
    account = await _person(db_session, console_world)
    db_session.add_all(
        [
            PartnerDevice(
                id=uuid.uuid4(),
                partner_id=a["partner_id"],
                principal_id=str(account.id),
                display_name=f"llena-{i}",
                hostname=f"llena-{i}.local",
                install_id=f"otra-{i}",
                platform="macos",
            )
            for i in range(MAX_ACTIVE_MACHINES_PER_PRINCIPAL)
        ]
    )
    await db_session.commit()
    await _open_session(db_session, account)

    en_el_tope = await client.post(
        "/console/workstation/machines", json=_body(), headers=a["headers"]()
    )

    assert en_el_tope.status_code == 409
    assert "cap" in en_el_tope.text


async def test_without_the_permission_it_answers_like_the_rest_of_the_console(
    client, db_session, console_world
):
    """403 con su motivo, como cualquier otra ruta. El rol sale de la
    membresía, nunca del token."""
    a = console_world["a"]
    analista = await add_console_member(db_session, partner_id=a["partner_id"], role="analyst")

    refused = await client.post(
        "/console/workstation/machines", json=_body(), headers=analista["headers"]()
    )

    assert refused.status_code == 403


# ── el tope ────────────────────────────────────────────────────────────


async def test_archived_machines_do_not_count_towards_the_cap(client, db_session, console_world):
    """Si contaran, cada retirada de acceso cerraría el tope un poco más.

    Sería un tope que se cierra solo: un defecto, no una política.
    """
    a = console_world["a"]
    account = await _person(db_session, console_world)
    db_session.add_all(
        [
            PartnerDevice(
                id=uuid.uuid4(),
                partner_id=a["partner_id"],
                principal_id=str(account.id),
                display_name=f"vieja-{i}",
                hostname=f"vieja-{i}.local",
                install_id=f"archivada-{i}",
                platform="macos",
                revoked_at=datetime.now(UTC),
                revoked_reason="archivada_consola",
            )
            for i in range(MAX_ACTIVE_MACHINES_PER_PRINCIPAL + 3)
        ]
    )
    await db_session.commit()
    await _open_session(db_session, account)

    done = await client.post("/console/workstation/machines", json=_body(), headers=a["headers"]())

    assert done.status_code == 201, done.text


async def test_the_cap_does_not_archive_anything_by_itself(client, db_session, console_world):
    """Archivar la más antigua sería cómodo y una sorpresa desagradable.

    La «más antigua» puede ser la que está ejecutando algo ahora mismo, y
    archivar es terminal: la sorpresa no se deshace.
    """
    a = console_world["a"]
    account = await _person(db_session, console_world)
    llenas = [
        PartnerDevice(
            id=uuid.uuid4(),
            partner_id=a["partner_id"],
            principal_id=str(account.id),
            display_name=f"llena-{i}",
            hostname=f"llena-{i}.local",
            install_id=f"otra-{i}",
            platform="macos",
        )
        for i in range(MAX_ACTIVE_MACHINES_PER_PRINCIPAL)
    ]
    db_session.add_all(llenas)
    await db_session.commit()
    await _open_session(db_session, account)

    await client.post("/console/workstation/machines", json=_body(), headers=a["headers"]())

    for maquina in llenas:
        await db_session.refresh(maquina)
        assert maquina.revoked_at is None
