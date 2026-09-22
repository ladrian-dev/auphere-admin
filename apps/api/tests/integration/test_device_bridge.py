"""El puente, de extremo a extremo — 001-Requisitos 6.1, 6.3 y 4.1, con la máquina
del partner (spec 002).

Recorre lo que hace una máquina real: se empareja, recibe su credencial, late,
sondea, devuelve un resultado, se desempareja o la archivan. Lo que se comprueba
en cada paso no es que responda 200 — es la propiedad que hace que el paso sea
correcto.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from nexus_api.db.models import DeviceClientLink, LocalExecution, PartnerDevice
from nexus_api.services.device_credential import issue_device_token, verify_device_token
from nexus_api.services.device_presence import derive_presence

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _paired(db_session, console_world, label: str = "a", *, principal: str | None = None):
    w = console_world[label]
    device = PartnerDevice(
        id=uuid.uuid4(),
        partner_id=w["partner_id"],
        principal_id=principal or w["user_id"],
        display_name="portátil",
        hostname="portatil.local",
        platform="macos",
        last_heartbeat_at=datetime.now(UTC),
    )
    db_session.add(device)
    await db_session.commit()
    token = issue_device_token(device_id=device.id, partner_id=w["partner_id"], generation=1)
    return device, token


async def test_registering_gives_the_machine_a_credential_that_names_it(
    client, db_session, console_world
):
    """Lo que se comprueba es la credencial, no por dónde se pidió.

    Antes se pedía canjeando un código; desde la spec 012 se pide con la
    sesión. La propiedad es la misma y sigue siendo la que importa: **nombra
    máquina, partner y generación, y no nombra tenant**.
    """
    from tests.conftest import register_machine

    a = console_world["a"]
    registered = await register_machine(client, db_session, a)

    claims = verify_device_token(registered["credential"])
    assert claims.device_id == uuid.UUID(registered["device_id"])
    assert claims.partner_id == a["partner_id"]
    assert claims.generation == 1


async def test_the_heartbeat_moves_the_heartbeat_and_nothing_else(
    client, db_session, console_world
):
    """Si moviera algo más, habría un estado que puede quedar desincronizado."""
    device, token = await _paired(db_session, console_world)
    device.last_heartbeat_at = None
    await db_session.commit()
    before = {
        c.name: getattr(device, c.name)
        for c in PartnerDevice.__table__.columns
        if c.name != "last_heartbeat_at"
    }
    assert derive_presence(device.last_heartbeat_at) == "ausente"

    response = await client.post(
        "/device/heartbeat", headers=_auth(token), json={"app_version": "9.9"}
    )
    assert response.status_code == 204

    await db_session.refresh(device)
    after = {
        c.name: getattr(device, c.name)
        for c in PartnerDevice.__table__.columns
        if c.name != "last_heartbeat_at"
    }
    assert before == after, "el latido tocó algo más que su propia columna"
    assert derive_presence(device.last_heartbeat_at) == "presente"


async def test_the_poll_lists_the_links_and_which_lack_a_directory(
    client, db_session, console_world
):
    a = console_world["a"]
    device, token = await _paired(db_session, console_world)
    db_session.add(
        DeviceClientLink(
            id=uuid.uuid4(), tenant_id=a["tenant_id"], device_id=device.id, created_by=a["user_id"]
        )
    )
    await db_session.commit()
    response = await client.get("/device/poll", headers=_auth(token))
    assert response.status_code == 200
    assert response.json()["work"] == []
    assert response.json()["links"] == [
        {
            "client_ref": a["ref"],
            "client_name": "Client A One",
            "workdir": None,
            "needs_directory": True,
        }
    ]


async def test_declaring_a_directory_fills_the_link(client, db_session, console_world):
    a = console_world["a"]
    device, token = await _paired(db_session, console_world)
    link = DeviceClientLink(
        id=uuid.uuid4(), tenant_id=a["tenant_id"], device_id=device.id, created_by=a["user_id"]
    )
    db_session.add(link)
    await db_session.commit()
    response = await client.post(
        "/device/links",
        headers=_auth(token),
        json={
            "client_ref": a["ref"],
            "workdir": "/Users/a/cliente",
            "checks": {"exists": True, "is_dir": True, "resolves_within": True, "readable": True},
        },
    )
    assert response.status_code == 204, response.text
    await db_session.refresh(link)
    assert link.workdir == "/Users/a/cliente"
    assert link.declared_by_device is True
    assert link.declared_at is not None
    polled = (await client.get("/device/poll", headers=_auth(token))).json()
    assert polled["links"][0]["needs_directory"] is False


async def test_a_client_not_linked_from_the_console_cannot_be_declared(
    client, db_session, console_world
):
    """La consola vincula; la máquina solo declara. Sin vínculo previo, 404."""
    a = console_world["a"]
    _, token = await _paired(db_session, console_world)
    response = await client.post(
        "/device/links",
        headers=_auth(token),
        json={"client_ref": a["ref"], "workdir": "/Users/a/cliente", "checks": {}},
    )
    assert response.status_code == 404


async def test_a_result_closes_the_audit_entry(client, db_session, console_world):
    from sqlalchemy import text

    from nexus_api.core.tenant_context import tenant_context
    from nexus_api.repositories.local_workstation import LocalExecutionRepository

    a = console_world["a"]
    device, token = await _paired(db_session, console_world)
    await db_session.execute(
        text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(a["tenant_id"])}
    )
    with tenant_context(a["tenant_id"]):
        row = await LocalExecutionRepository(db_session).start(
            device_id=device.id, executable="make", argv_signature='["build"]', grant_id=None
        )
    await db_session.commit()

    response = await client.post(
        "/device/result",
        headers=_auth(token),
        json={"execution_id": str(row.id), "outcome": "expirada", "children_reaped": 2},
    )
    assert response.status_code == 204, response.text
    closed = await db_session.get(LocalExecution, row.id)
    await db_session.refresh(closed)
    assert closed.outcome == "expirada"
    assert closed.ended_at is not None
    assert closed.children_reaped == 2


async def test_the_result_carries_one_bounded_window_and_the_row_still_has_none():
    """§III con su enmienda de la spec 003, escrita entera.

    Hasta la 003 el resultado no tenía **dónde** llevar la salida, y eso era la
    garantía. Ahora el teammate ejecuta a petición de una persona y tiene que
    poder leer lo que salió, así que se abre **una** ventana, acotada, y la
    garantía se mueve de "no existe el campo" a "el campo existe, está acotado
    y no se guarda". Lo que no cambia es el asiento: la auditoría sigue
    diciendo qué pasó, nunca qué dijo el comando.
    """
    from nexus_api.api.device_bridge import ResultIn

    assert set(ResultIn.model_fields) == {
        "execution_id",
        "outcome",
        "exit_code",
        "children_reaped",
        "stdout_sample",
        "denial_code",
    }
    # La ventana es una y está medida en el borde, no en la confianza de quien
    # envía: el mismo tope que aplica la app antes de mandarlo.
    #
    # El número subió de 2.048 a 16.384 el 2026-09-20 porque con 2 KB no cabía una
    # traza de compilación y el agente ejecutaba a ciegas
    # (`.specify/bugs/el-teammate-no-alcanza-la-maquina/`). **Lo que este test
    # defiende no es el número, es que haya uno y sea el mismo en todo el viaje**:
    # por eso se afirma contra la constante y no contra un literal, que es como
    # llegaron a divergir la aplicación y el borde.
    from nexus_api.core.local_exec_limits import OUTPUT_SAMPLE_CHARS

    sample = ResultIn.model_fields["stdout_sample"]
    assert any(getattr(m, "max_length", None) == OUTPUT_SAMPLE_CHARS for m in sample.metadata), (
        sample.metadata
    )
    with pytest.raises(ValidationError):
        ResultIn(
            execution_id=uuid.uuid4(),
            outcome="completada",
            stdout_sample="x" * (OUTPUT_SAMPLE_CHARS + 1),
        )

    # Y la fila —lo único que sobrevive a la ejecución— no tiene columna alguna
    # donde esa muestra pudiera acabar.
    columns = set(LocalExecution.__table__.columns.keys())
    assert not columns & {"stdout", "stdout_sample", "output", "stderr", "log"}, columns


# ── Requisito 11: archivar desde la consola, y la pertenencia retirada ─────


async def test_archiving_from_the_console_stops_the_bridge_on_the_next_heartbeat(
    client, db_session, console_world
):
    a = console_world["a"]
    device, token = await _paired(db_session, console_world)
    archived = await client.delete(
        f"/console/workstation/devices/{device.id}", headers=a["headers"]()
    )
    assert archived.status_code == 204, archived.text
    beat = await client.post("/device/heartbeat", headers=_auth(token), json={})
    assert beat.status_code == 403
    assert beat.json() == {"code": "device_archived", "reason": "archivada_consola"}
    await db_session.refresh(device)
    assert device.revoked_reason == "archivada_consola"


async def test_an_archived_machine_stays_archived(client, db_session, console_world):
    a = console_world["a"]
    device, _ = await _paired(db_session, console_world)
    await client.delete(f"/console/workstation/devices/{device.id}", headers=a["headers"]())
    renamed = await client.patch(
        f"/console/workstation/devices/{device.id}",
        headers=a["headers"](),
        json={"display_name": "otra"},
    )
    assert renamed.status_code in (404, 409)


async def test_removing_a_member_archives_their_machines(client, db_session, console_world):
    from tests.conftest import add_console_member

    a = console_world["a"]
    builder = await add_console_member(db_session, partner_id=a["partner_id"], role="builder")
    device, token = await _paired(db_session, console_world, principal=builder["user_id"])
    removed = await client.delete(
        f"/console/team/members/{builder['membership_id']}", headers=a["headers"]()
    )
    assert removed.status_code in (200, 204), removed.text
    await db_session.refresh(device)
    assert device.revoked_reason == "pertenencia_retirada"
    beat = await client.post("/device/heartbeat", headers=_auth(token), json={})
    assert beat.status_code == 403


async def _real_member(db_session, partner_id, *, role: str):
    """Una persona con cuenta de consola **de verdad** y sesión recién abierta.

    `add_console_member` fabrica un `user_id` de mentira, que bastaba mientras
    la credencial salía de un código: al canje le daba igual quién teclease.
    Registrar con la sesión ya no: mira si esa persona confirmó quién era hace
    poco, y una cadena inventada no tiene sesión que mirar.
    """
    import sqlalchemy as sa

    from nexus_api.db.models import PartnerMembership
    from nexus_api.services import console_identity

    account = await console_identity.create_account(
        db_session,
        email=f"{role}-{uuid.uuid4().hex[:8]}@example.com",
        password="una-contrasena-larga",
        display_name=role,
    )
    await db_session.commit()
    existing = (
        await db_session.execute(
            sa.select(PartnerMembership).where(
                PartnerMembership.partner_id == partner_id, PartnerMembership.role == role
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        db_session.add(
            PartnerMembership(
                id=uuid.uuid4(),
                partner_id=partner_id,
                user_id=str(account.id),
                email=account.email,
                display_name=role,
                role=role,
                status="active",
            )
        )
    else:
        existing.user_id = str(account.id)
        existing.email = account.email
    await db_session.commit()
    await console_identity.start_session(db_session, account)
    await db_session.commit()

    from tests.conftest import console_headers

    return {
        "user_id": str(account.id),
        "headers": lambda **kw: console_headers(
            user_id=str(account.id), partner_id=partner_id, **kw
        ),
    }


async def test_two_people_can_register_the_same_hostname(client, db_session, console_world):
    """Historia 5: una máquina física, dos altas, dos dueñas.

    Con el código, la segunda persona se quedaba fuera si la primera ya había
    emparejado el ordenador. Ahora cada una recibe **la suya**, y lo que sigue
    sin pasar —y es lo que este test defiende— es que vea la ajena.
    """
    a = console_world["a"]
    owner = await _real_member(db_session, a["partner_id"], role="owner")
    builder = await _real_member(db_session, a["partner_id"], role="builder")

    for who in (owner, builder):
        registered = await client.post(
            "/console/workstation/machines",
            json={
                "hostname": "imac-recepcion.local",
                "platform": "macos",
                "install_id": f"instalacion-{uuid.uuid4().hex[:12]}",
            },
            headers=who["headers"](),
        )
        assert registered.status_code == 201, registered.text

    # La builder solo ve la suya; la owner (gestora) ve las dos con dueña.
    mine = (await client.get("/console/workstation/devices", headers=builder["headers"]())).json()
    assert [m["mine"] for m in mine] == [True]
    every = (await client.get("/console/workstation/devices", headers=owner["headers"]())).json()
    assert len(every) == 2
    assert {m["owner_user_id"] for m in every} == {owner["user_id"], builder["user_id"]}
    rows = (await db_session.execute(select(PartnerDevice.hostname))).scalars().all()
    assert rows == ["imac-recepcion.local", "imac-recepcion.local"]
