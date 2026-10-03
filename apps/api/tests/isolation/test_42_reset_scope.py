"""Restablecer una contraseña no alcanza a nadie más — spec 011, R3.5.

**Por qué esto necesita su propio test habiendo ya un ``test_38``.** Aquel fija
que ``revoke_all_access`` no se desborda cuando se la llama directamente. Éste
fija lo mismo para **el camino nuevo**, que es el único que puede llegar ahí sin
que nadie de Auphere haya decidido nada: un enlace que llegó por correo, canjeado
por quien lo recibió. Si la llamada del canje se equivocara de ``principal_id``
—o lo tomara del cuerpo de la petición en vez de del enlace— ninguna política
diría nada.

Y no lo diría porque **la operación corre con rol dueño**: es mantenimiento de
plataforma y la RLS está retirada a propósito. Lo único que impide que alcance a
otra persona es el ``WHERE`` por ``principal_id``.

Por eso hacen falta **dos** personas y no una. Restablecer la propia y mirar que
la propia quedó fuera no prueba ningún límite: prueba el camino feliz otra vez.

En rojo bloquea el merge.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.db.models import PartnerDevice, PartnerMembership
from nexus_api.db.models.console_identity import ConsoleAccount
from nexus_api.services import console_identity
from tests.conftest import mint_console_token

pytestmark = [pytest.mark.isolation, pytest.mark.asyncio]

PASSWORD = "una-contrasena-larga"
NUEVA = "otra-contrasena-mas-larga"


def _svc() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {mint_console_token(user_id='bff', partner_id=None, service=True)}"
    }


def _mail_sink(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []

    async def _fake(**kwargs: Any) -> bool:
        sent.append(kwargs)
        return True

    monkeypatch.setattr("nexus_api.services.email.send_email", _fake)
    return sent


def _link_token(sent: list[dict[str, Any]]) -> str:
    html = sent[-1]["html"]
    start = html.index("/reset/") + len("/reset/")
    end = min(
        (i for i in (html.find('"', start), html.find("<", start), html.find(">", start)) if i > 0),
        default=len(html),
    )
    return html[start:end]


async def _person_with_everything(
    db_session: Any, *, partner_id: uuid.UUID, label: str
) -> tuple[ConsoleAccount, list[PartnerDevice], list[str]]:
    account = await console_identity.create_account(
        db_session,
        email=f"{label}-{uuid.uuid4().hex[:8]}@example.com",
        password=PASSWORD,
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


async def _still_has_everything(
    db_session: Any, account: ConsoleAccount, machines: list[PartnerDevice], tokens: list[str]
) -> None:
    for token in tokens:
        assert await console_identity.resolve_session(db_session, token) is not None, (
            f"{account.email} perdió una sesión que no era suya de perder"
        )
    for machine in machines:
        await db_session.refresh(machine)
        assert machine.revoked_at is None, (
            f"{account.email} perdió una máquina que no era suya de perder"
        )
    assert (
        await console_identity.authenticate(db_session, email=account.email, password=PASSWORD)
        is not None
    ), f"a {account.email} le cambiaron la contraseña sin pedirlo"


async def _reset(client: Any, db_session: Any, account: ConsoleAccount, sent: list[Any]) -> None:
    await client.post("/console/password-reset", json={"email": account.email}, headers=_svc())
    r = await client.post(
        f"/console/password-reset/{_link_token(sent)}", json={"password": NUEVA}, headers=_svc()
    )
    assert r.status_code == 200
    db_session.expire_all()


async def test_restablecer_no_toca_a_una_companera_del_mismo_partner(
    client: Any, db_session: Any, console_world: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El caso donde la RLS nunca habría ayudado: las dos filas son
    legítimamente del mismo partner, así que ninguna política las separa."""
    sent = _mail_sink(monkeypatch)
    partner_id = console_world["a"]["partner_id"]

    mine, my_machines, my_tokens = await _person_with_everything(
        db_session, partner_id=partner_id, label="yo"
    )
    theirs, their_machines, their_tokens = await _person_with_everything(
        db_session, partner_id=partner_id, label="colega"
    )
    await db_session.execute(
        sa.update(PartnerMembership)
        .where(PartnerMembership.partner_id == partner_id)
        .values(user_id=str(mine.id), email=mine.email)
    )
    await db_session.commit()

    await _reset(client, db_session, mine, sent)

    # La mía, fuera.
    for token in my_tokens:
        assert await console_identity.resolve_session(db_session, token) is None
    for machine in my_machines:
        await db_session.refresh(machine)
        assert machine.revoked_at is not None

    # La suya, intacta — sesiones, máquinas y contraseña.
    await _still_has_everything(db_session, theirs, their_machines, their_tokens)


async def test_restablecer_no_toca_a_una_persona_de_otro_partner(
    client: Any, db_session: Any, console_world: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Y el caso donde alguien podría suponer que la RLS sigue cubriendo.

    No cubre. Si el ``WHERE`` por persona desapareciera del canje, un enlace
    recibido por correo se llevaría por delante a un partner entero.
    """
    sent = _mail_sink(monkeypatch)

    mine, my_machines, my_tokens = await _person_with_everything(
        db_session, partner_id=console_world["a"]["partner_id"], label="yo"
    )
    theirs, their_machines, their_tokens = await _person_with_everything(
        db_session, partner_id=console_world["b"]["partner_id"], label="otro-partner"
    )

    await _reset(client, db_session, mine, sent)

    for token in my_tokens:
        assert await console_identity.resolve_session(db_session, token) is None
    for machine in my_machines:
        await db_session.refresh(machine)
        assert machine.revoked_at is not None

    await _still_has_everything(db_session, theirs, their_machines, their_tokens)


async def test_el_enlace_de_una_persona_no_restablece_la_cuenta_de_otra(
    client: Any, db_session: Any, console_world: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Y la forma más directa de equivocarse: que el canje se creyera una
    dirección del cuerpo de la petición en vez del enlace.

    Se piden **dos** enlaces, uno por persona, y se canjea el primero. El
    segundo tiene que seguir siendo el único que abre la segunda cuenta.
    """
    sent = _mail_sink(monkeypatch)
    partner_id = console_world["a"]["partner_id"]

    una, _m1, _t1 = await _person_with_everything(db_session, partner_id=partner_id, label="una")
    otra, otra_machines, otra_tokens = await _person_with_everything(
        db_session, partner_id=partner_id, label="otra"
    )

    await client.post("/console/password-reset", json={"email": una.email}, headers=_svc())
    token_una = _link_token(sent)
    await client.post("/console/password-reset", json={"email": otra.email}, headers=_svc())
    token_otra = _link_token(sent)
    assert token_una != token_otra

    r = await client.post(
        f"/console/password-reset/{token_una}", json={"password": NUEVA}, headers=_svc()
    )
    assert r.status_code == 200
    db_session.expire_all()

    await _still_has_everything(db_session, otra, otra_machines, otra_tokens)
