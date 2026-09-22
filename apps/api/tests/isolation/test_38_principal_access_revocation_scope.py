"""Retirar el acceso de una persona no alcanza a nadie más — spec 012, R1.5.

**Por qué esto necesita un test y no se puede dar por hecho.** Casi todo lo que
toca `partner_devices` está protegido por la RLS: si la consulta se equivoca de
partner, la política la corta. Esta operación **no**. Corre con el rol dueño a
propósito —es mantenimiento de plataforma, igual que archivar las máquinas de
quien pierde la pertenencia— y eso significa que la red de seguridad está
retirada.

Lo único que impide que alcance a otra persona es **el `WHERE` de su propia
consulta**. Una condición olvidada aquí no da un error: da un éxito silencioso
que echa de la plataforma a gente que no tenía nada que ver.

Por eso hay dos casos y no uno: la compañera del mismo partner —donde la RLS
nunca habría ayudado, porque las dos filas son legítimamente del mismo partner—
y la persona de otro partner, que es donde alguien podría suponer que la RLS
sigue cubriendo y no lo hace.

En rojo bloquea el merge.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from nexus_api.db.models import PartnerDevice, PartnerMembership
from nexus_api.db.models.console_identity import ConsoleAccount
from nexus_api.services import console_identity

pytestmark = [pytest.mark.isolation, pytest.mark.asyncio]


async def _person_with_machines(
    db_session, *, partner_id: uuid.UUID, label: str
) -> tuple[ConsoleAccount, list[PartnerDevice], list[str]]:
    account = await console_identity.create_account(
        db_session,
        email=f"{label}-{uuid.uuid4().hex[:8]}@example.com",
        password="una-contrasena-larga",
        display_name=label,
    )
    await db_session.commit()

    machines = [
        PartnerDevice(
            id=uuid.uuid4(),
            partner_id=partner_id,
            principal_id=str(account.id),
            display_name=f"mac-{label}-{i}",
            hostname=f"mac-{label}-{i}.local",
            platform="macos",
        )
        for i in range(2)
    ]
    db_session.add_all(machines)
    await db_session.commit()

    tokens = []
    for _ in range(2):
        token, _expires = await console_identity.start_session(db_session, account)
        tokens.append(token)
    await db_session.commit()

    return account, machines, tokens


async def _still_has_everything(db_session, account, machines, tokens) -> None:
    for token in tokens:
        assert await console_identity.resolve_session(db_session, token) is not None, (
            f"{account.email} perdió una sesión que no era suya de perder"
        )
    for machine in machines:
        await db_session.refresh(machine)
        assert machine.revoked_at is None, (
            f"{account.email} perdió una máquina que no era suya de perder"
        )


async def test_revoking_one_person_does_not_touch_a_colleague(db_session, console_world):
    """El caso donde la RLS nunca habría ayudado.

    Dos personas del **mismo** partner: sus filas son legítimamente del mismo
    partner, así que ninguna política las separa. Es el mismo punto ciego que
    la garantía 8 nombró un nivel más abajo, entre clientes de un tenant.
    """
    from nexus_api.services import principal_access

    partner_id = console_world["a"]["partner_id"]
    mine, my_machines, my_tokens = await _person_with_machines(
        db_session, partner_id=partner_id, label="yo"
    )
    theirs, their_machines, their_tokens = await _person_with_machines(
        db_session, partner_id=partner_id, label="colega"
    )
    await db_session.execute(
        sa.update(PartnerMembership)
        .where(PartnerMembership.partner_id == partner_id)
        .values(user_id=str(mine.id), email=mine.email)
    )
    await db_session.commit()

    await principal_access.revoke_all_access(
        db_session, principal_id=mine.id, reason="prueba", actor="console:test"
    )
    await db_session.commit()

    # La mía, fuera.
    for token in my_tokens:
        assert await console_identity.resolve_session(db_session, token) is None
    for machine in my_machines:
        await db_session.refresh(machine)
        assert machine.revoked_at is not None

    # La suya, intacta.
    await _still_has_everything(db_session, theirs, their_machines, their_tokens)


async def test_revoking_one_person_does_not_touch_another_partner(db_session, console_world):
    """Y el caso donde alguien podría suponer que la RLS sigue cubriendo.

    No cubre: la operación corre con rol dueño. Si el `WHERE` por persona
    desapareciera, esto se llevaría por delante a un partner entero sin que
    ninguna política dijera nada.
    """
    from nexus_api.services import principal_access

    mine, my_machines, my_tokens = await _person_with_machines(
        db_session, partner_id=console_world["a"]["partner_id"], label="yo"
    )
    theirs, their_machines, their_tokens = await _person_with_machines(
        db_session, partner_id=console_world["b"]["partner_id"], label="otro-partner"
    )

    await principal_access.revoke_all_access(
        db_session, principal_id=mine.id, reason="prueba", actor="console:test"
    )
    await db_session.commit()

    for token in my_tokens:
        assert await console_identity.resolve_session(db_session, token) is None
    for machine in my_machines:
        await db_session.refresh(machine)
        assert machine.revoked_at is not None

    await _still_has_everything(db_session, theirs, their_machines, their_tokens)
