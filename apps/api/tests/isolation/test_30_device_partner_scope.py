"""Garantías 1, 2 y 6 — la máquina es del partner (spec 002, Requisito 4).

La 001 modeló ``partner_devices`` por tenant porque §I lo exige de toda tabla con
datos de tenant, y nadie preguntó si una máquina es un dato del tenant o del
partner. La 002 contesta: **del partner y de la persona que la emparejó**. Este
fichero prueba lo que eso obliga:

* la fila se ve por partner **y** por persona (dueña) o por gestor — y sin GUC, nada;
* un vínculo máquina↔cliente es dato de tenant y no cruza tenants;
* la credencial de una máquina de A no late, sondea, renueva ni declara para B;
* un ``client_ref`` que no es del partner → 404 **y** asiento de auditoría;
* una máquina archivada recibe 403 en las cinco operaciones — la revocación que la
  001 citó y nunca cubrió;
* una generación vieja fuera de la gracia → 401.

En rojo bloquea el merge.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError

from nexus_api.db.models import AuditLog, DeviceClientLink, PartnerDevice
from nexus_api.services.device_credential import issue_device_token

from .conftest import set_partner, set_tenant

pytestmark = [pytest.mark.isolation, pytest.mark.asyncio]


def _device(partner_id: uuid.UUID, principal_id: str, name: str) -> PartnerDevice:
    return PartnerDevice(
        id=uuid.uuid4(),
        partner_id=partner_id,
        principal_id=principal_id,
        display_name=name,
        hostname=f"{name}.local",
        platform="macos",
    )


async def _seed_world(db_session, console_world):
    """Dos máquinas en A (dueña y compañera) y una en B, sin GUC (rol dueño)."""
    a, b = console_world["a"], console_world["b"]
    mine = _device(a["partner_id"], a["user_id"], "mac-de-a")
    colleague = _device(a["partner_id"], "user_colleague_a", "mac-colega-a")
    theirs = _device(b["partner_id"], b["user_id"], "mac-de-b")
    db_session.add_all([mine, colleague, theirs])
    await db_session.commit()
    return mine, colleague, theirs


# ── garantía 1: RLS por partner y por persona ───────────────────────────


async def test_the_owner_sees_only_her_own_machines(db_session, console_world):
    a = console_world["a"]
    await _seed_world(db_session, console_world)
    await set_partner(db_session, a["partner_id"], principal_id=a["user_id"])
    names = (await db_session.execute(select(PartnerDevice.display_name))).scalars().all()
    assert set(names) == {"mac-de-a"}


async def test_the_manager_sees_every_machine_of_the_partner_and_none_of_another(
    db_session, console_world
):
    a = console_world["a"]
    await _seed_world(db_session, console_world)
    await set_partner(db_session, a["partner_id"], principal_id=a["user_id"], manager=True)
    names = (await db_session.execute(select(PartnerDevice.display_name))).scalars().all()
    assert set(names) == {"mac-de-a", "mac-colega-a"}


async def test_without_partner_or_person_there_are_no_rows(db_session, console_world):
    a = console_world["a"]
    await _seed_world(db_session, console_world)
    # Sin partner: nada.
    await db_session.execute(text("SELECT set_config('app.partner_id', '', true)"))
    await db_session.execute(text("SET LOCAL ROLE nexus_app"))
    assert (await db_session.execute(select(PartnerDevice.id))).scalars().all() == []
    await db_session.rollback()
    # Con partner pero sin persona ni gestor: tampoco.
    await set_partner(db_session, a["partner_id"])
    assert (await db_session.execute(select(PartnerDevice.id))).scalars().all() == []


async def test_a_partner_cannot_write_a_machine_for_another(db_session, console_world):
    a, b = console_world["a"], console_world["b"]
    await set_partner(db_session, a["partner_id"], principal_id=a["user_id"])
    db_session.add(_device(b["partner_id"], a["user_id"], "colada"))
    with pytest.raises(ProgrammingError):
        await db_session.flush()


# ── garantía 2: el vínculo es dato de tenant ────────────────────────────


async def test_links_do_not_cross_tenants(db_session, console_world):
    a, b = console_world["a"], console_world["b"]
    mine, _, theirs = await _seed_world(db_session, console_world)
    db_session.add_all(
        [
            DeviceClientLink(
                id=uuid.uuid4(),
                tenant_id=a["tenant_id"],
                device_id=mine.id,
                workdir="/Users/a/cliente",
                created_by=a["user_id"],
            ),
            DeviceClientLink(
                id=uuid.uuid4(),
                tenant_id=b["tenant_id"],
                device_id=theirs.id,
                workdir="/Users/b/cliente",
                created_by=b["user_id"],
            ),
        ]
    )
    await db_session.commit()
    await set_tenant(db_session, a["tenant_id"])
    rows = (await db_session.execute(select(DeviceClientLink.workdir))).scalars().all()
    assert rows == ["/Users/a/cliente"]


# ── la credencial: cinco operaciones, acotadas al partner ───────────────


async def _paired(db_session, console_world, label: str) -> tuple[PartnerDevice, str]:
    w = console_world[label]
    device = _device(w["partner_id"], w["user_id"], f"mac-{label}")
    device.last_heartbeat_at = datetime.now(UTC)
    db_session.add(device)
    await db_session.commit()
    token = issue_device_token(
        device_id=device.id, partner_id=w["partner_id"], generation=device.credential_generation
    )
    return device, token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_a_machine_cannot_declare_a_directory_for_a_client_of_another_partner(
    client, db_session, console_world
):
    _, token = await _paired(db_session, console_world, "a")
    foreign_ref = console_world["b"]["ref"]
    response = await client.post(
        "/device/links",
        headers=_auth(token),
        json={"client_ref": foreign_ref, "workdir": "/tmp/x", "checks": {}},
    )
    assert response.status_code == 404
    # Y el intento queda registrado (Requisito 4.4 / 13.2).
    rows = (
        (await db_session.execute(select(AuditLog).where(AuditLog.action == "device.link_denied")))
        .scalars()
        .all()
    )
    assert rows, "el intento de vincular un cliente ajeno no dejó asiento"


async def test_an_archived_machine_is_refused_on_every_operation(client, db_session, console_world):
    device, token = await _paired(db_session, console_world, "a")
    device.revoked_at = datetime.now(UTC)
    device.revoked_reason = "archivada_consola"
    await db_session.commit()
    ref = console_world["a"]["ref"]
    calls = [
        client.post("/device/heartbeat", headers=_auth(token), json={}),
        client.get("/device/poll", headers=_auth(token)),
        client.post(
            "/device/result",
            headers=_auth(token),
            json={"execution_id": str(uuid.uuid4()), "outcome": "completada"},
        ),
        client.post("/device/renew", headers=_auth(token)),
        client.post(
            "/device/links",
            headers=_auth(token),
            json={"client_ref": ref, "workdir": "/tmp/x", "checks": {}},
        ),
    ]
    for call in calls:
        response = await call
        assert response.status_code == 403, response.text
        assert response.json()["code"] == "device_archived"


async def test_a_stale_generation_outside_the_grace_window_is_refused(
    client, db_session, console_world
):
    device, _ = await _paired(db_session, console_world, "a")
    old = issue_device_token(
        device_id=device.id, partner_id=console_world["a"]["partner_id"], generation=1
    )
    device.credential_generation = 2
    device.credential_rotated_at = datetime.now(UTC) - timedelta(seconds=120)
    await db_session.commit()
    response = await client.post("/device/heartbeat", headers=_auth(old), json={})
    assert response.status_code == 401


async def test_a_machine_abandoned_for_thirty_days_must_pair_again(
    client, db_session, console_world
):
    device, token = await _paired(db_session, console_world, "a")
    device.last_heartbeat_at = datetime.now(UTC) - timedelta(days=31)
    await db_session.commit()
    for call in (
        client.post("/device/renew", headers=_auth(token)),
        client.post("/device/heartbeat", headers=_auth(token), json={}),
    ):
        response = await call
        assert response.status_code == 403
        assert response.json()["code"] == "pairing_required"


async def test_a_token_names_partner_and_device_and_never_a_tenant():
    from nexus_api.services.device_credential import verify_device_token

    device_id, partner_id = uuid.uuid4(), uuid.uuid4()
    claims = verify_device_token(
        issue_device_token(device_id=device_id, partner_id=partner_id, generation=3)
    )
    assert (claims.device_id, claims.partner_id, claims.generation) == (device_id, partner_id, 3)
    assert not hasattr(claims, "tenant_id")


async def test_polling_from_b_never_returns_links_of_a(client, db_session, console_world):
    a = console_world["a"]
    mine, _ = await _paired(db_session, console_world, "a")
    _, token_b = await _paired(db_session, console_world, "b")
    db_session.add(
        DeviceClientLink(
            id=uuid.uuid4(),
            tenant_id=a["tenant_id"],
            device_id=mine.id,
            workdir=None,
            created_by=a["user_id"],
        )
    )
    await db_session.commit()
    response = await client.get("/device/poll", headers=_auth(token_b))
    assert response.status_code == 200
    assert response.json()["links"] == []
