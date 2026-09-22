"""Retirar todo el acceso de una persona — spec 012, Requisito 1.

Hoy esto **no se puede hacer de ninguna forma**, ni siquiera a mano. Los dos
únicos borrados de sesión que existen son «las caducadas» y «ésta una, por su
token»; no hay ninguno por persona. Y desemparejar desde la aplicación no toca el
servidor, así que la credencial sigue valiendo hasta doce horas.

De los tres bloques, el que importa es el segundo. Que retirar el acceso
funcione por el camino feliz no prueba que sea **atómico**: eso solo se ve
cuando algo se rompe a mitad, y por eso hay un test que lo rompe a propósito. El
estado que no puede existir es «sesiones cerradas, máquinas vivas» — alguien que
cree que ha echado a una persona y lo que ha hecho es quitarle el navegador y
dejarle la ejecución local.

La frontera —que esto no alcance a otra persona— se prueba aparte, en
`tests/isolation/test_38_principal_access_revocation_scope.py`, porque la
operación corre con rol dueño y la RLS no la protege.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.db.models import AuditLog, PartnerDevice, PartnerMembership
from nexus_api.db.models.console_identity import ConsoleAccount, ConsoleSession
from nexus_api.services import console_identity
from tests.conftest import add_console_member

pytestmark = pytest.mark.asyncio


async def _account(db_session, email: str) -> ConsoleAccount:
    account = await console_identity.create_account(
        db_session, email=email, password="una-contrasena-larga", display_name="Quien sea"
    )
    await db_session.commit()
    return account


async def _sessions(db_session, account: ConsoleAccount, *, how_many: int) -> list[str]:
    """Sesiones abiertas de verdad, con su token, como las que abre entrar."""
    tokens = []
    for _ in range(how_many):
        token, _expires = await console_identity.start_session(db_session, account)
        tokens.append(token)
    await db_session.commit()
    return tokens


async def _machines(db_session, *, partner_id: uuid.UUID, principal_id: str, how_many: int):
    machines = [
        PartnerDevice(
            id=uuid.uuid4(),
            partner_id=partner_id,
            principal_id=principal_id,
            display_name=f"mac-{i}",
            hostname=f"mac-{i}.local",
            platform="macos",
        )
        for i in range(how_many)
    ]
    db_session.add_all(machines)
    await db_session.commit()
    return machines


async def _world(db_session, console_world) -> dict[str, Any]:
    """Una persona real del partner A, con dos sesiones y dos máquinas."""
    a = console_world["a"]
    account = await _account(db_session, f"quien-{uuid.uuid4().hex[:8]}@example.com")
    await db_session.execute(
        sa.update(PartnerMembership)
        .where(PartnerMembership.partner_id == a["partner_id"])
        .values(user_id=str(account.id), email=account.email)
    )
    await db_session.commit()
    tokens = await _sessions(db_session, account, how_many=2)
    machines = await _machines(
        db_session, partner_id=a["partner_id"], principal_id=str(account.id), how_many=2
    )
    return {
        "account": account,
        "tokens": tokens,
        "machines": machines,
        "partner_id": a["partner_id"],
    }


# ── que sirva para lo que dice que sirve ────────────────────────────────


async def test_revoking_access_closes_every_session(db_session, console_world):
    from nexus_api.services import principal_access

    w = await _world(db_session, console_world)

    await principal_access.revoke_all_access(
        db_session, principal_id=w["account"].id, reason="prueba", actor="console:test"
    )
    await db_session.commit()

    for token in w["tokens"]:
        assert await console_identity.resolve_session(db_session, token) is None


async def test_revoking_access_archives_every_machine(db_session, console_world):
    """Sin esperar a que caduque nada.

    Una credencial de máquina vive doce horas. Si retirar el acceso solo
    impidiera renovarla, la persona seguiría ejecutando en su ordenador media
    jornada después de que alguien creyera haberla echado.
    """
    from nexus_api.services import principal_access

    w = await _world(db_session, console_world)

    await principal_access.revoke_all_access(
        db_session, principal_id=w["account"].id, reason="prueba", actor="console:test"
    )
    await db_session.commit()

    for machine in w["machines"]:
        await db_session.refresh(machine)
        assert machine.revoked_at is not None
        assert machine.revoked_reason is not None


# ── lo atómico, que solo se ve cuando algo se rompe ─────────────────────


async def test_a_failure_halfway_leaves_nothing_half_done(db_session, console_world, monkeypatch):
    """El estado que no puede existir: sesiones cerradas y máquinas vivas.

    Se rompe a propósito la segunda mitad. Probar esto por el camino feliz no
    prueba nada: dos operaciones seguidas que funcionan se parecen mucho a una
    transacción hasta el día en que una falla.

    Que la persona siga **dentro** tras un fallo es incómodo y honesto; que se
    quede fuera del navegador pero con la ejecución local viva es peor que no
    haber hecho nada, porque quien lo pidió cree que terminó.
    """
    from nexus_api.repositories import local_workstation
    from nexus_api.services import principal_access

    w = await _world(db_session, console_world)

    async def _boom(*_args: object, **_kwargs: object) -> int:
        raise RuntimeError("la mitad de las máquinas se cayó")

    monkeypatch.setattr(
        local_workstation.PartnerDeviceRepository, "archive_all_for_principal", _boom
    )

    with pytest.raises(RuntimeError):
        await principal_access.revoke_all_access(
            db_session, principal_id=w["account"].id, reason="prueba", actor="console:test"
        )
    await db_session.rollback()

    # Ninguna de las dos mitades quedó aplicada.
    for token in w["tokens"]:
        assert await console_identity.resolve_session(db_session, token) is not None
    for machine in w["machines"]:
        await db_session.refresh(machine)
        assert machine.revoked_at is None


# ── que quede dicho quién lo hizo ───────────────────────────────────────


async def test_revoking_access_leaves_an_audit_trail(db_session, console_world):
    from nexus_api.services import principal_access

    w = await _world(db_session, console_world)

    await principal_access.revoke_all_access(
        db_session,
        principal_id=w["account"].id,
        reason="portatil perdido",
        actor="console:jefa",
    )
    await db_session.commit()

    rows = (
        (
            await db_session.execute(
                sa.select(AuditLog).where(AuditLog.action == "principal.access_revoked")
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.actor == "console:jefa"
    assert str(w["account"].id) in str(row.target)
    assert "portatil perdido" in str(row.after_json)


# ── lo que no cuenta ────────────────────────────────────────────────────


async def test_an_already_expired_session_does_not_break_the_operation(db_session, console_world):
    """Retirar el acceso de alguien que ya no tenía ninguna sesión viva.

    Es el caso aburrido y por eso se olvida: no debe fallar ni afirmar que
    cerró algo que no existía.
    """
    from nexus_api.services import principal_access

    w = await _world(db_session, console_world)
    await db_session.execute(
        sa.update(ConsoleSession)
        .where(ConsoleSession.principal_id == w["account"].id)
        .values(expires_at=datetime.now(UTC) - timedelta(days=1))
    )
    await db_session.commit()

    await principal_access.revoke_all_access(
        db_session, principal_id=w["account"].id, reason="prueba", actor="console:test"
    )
    await db_session.commit()

    for machine in w["machines"]:
        await db_session.refresh(machine)
        assert machine.revoked_at is not None


# ── la puerta: quién puede pedirlo ──────────────────────────────────────


async def test_a_builder_cannot_revoke_anyone(client, db_session, console_world):
    """El permiso es ``team:manage``, no ``workstation:pair``.

    Y la diferencia no es cosmética. ``workstation:pair`` lo tiene el **builder**,
    porque —dice su propia declaración— es «reclamar lo que es tuyo». Esto es lo
    contrario: retirarle el acceso a otra persona. Colgarlo del permiso vecino,
    por estar el código al lado, habría dejado a un builder echando a un owner.
    """
    a = console_world["a"]
    builder = await add_console_member(db_session, partner_id=a["partner_id"], role="builder")

    refused = await client.delete(
        f"/console/team/members/{a['membership_id']}/access",
        headers=builder["headers"](),
    )

    assert refused.status_code == 403, refused.text


async def test_an_owner_cannot_revoke_someone_from_another_partner(
    client, db_session, console_world
):
    """Y se responde igual que para un identificador inventado.

    Decir «ese miembro existe pero no es tuyo» convierte esta ruta en un
    directorio de quién trabaja en qué partner.
    """
    a, b = console_world["a"], console_world["b"]

    refused = await client.delete(
        f"/console/team/members/{b['membership_id']}/access", headers=a["headers"]()
    )
    invented = await client.delete(
        f"/console/team/members/{uuid.uuid4()}/access", headers=a["headers"]()
    )

    assert refused.status_code == 404
    assert refused.json() == invented.json()


async def test_an_owner_revokes_a_member_end_to_end(client, db_session, console_world):
    a = console_world["a"]
    colleague = await add_console_member(db_session, partner_id=a["partner_id"], role="builder")
    account = await _account(db_session, f"colega-{uuid.uuid4().hex[:8]}@example.com")
    await db_session.execute(
        sa.update(PartnerMembership)
        .where(PartnerMembership.id == colleague["membership_id"])
        .values(user_id=str(account.id), email=account.email)
    )
    await db_session.commit()
    tokens = await _sessions(db_session, account, how_many=2)
    machines = await _machines(
        db_session, partner_id=a["partner_id"], principal_id=str(account.id), how_many=1
    )

    done = await client.delete(
        f"/console/team/members/{colleague['membership_id']}/access", headers=a["headers"]()
    )

    assert done.status_code == 204, done.text
    for token in tokens:
        assert await console_identity.resolve_session(db_session, token) is None
    await db_session.refresh(machines[0])
    assert machines[0].revoked_at is not None
