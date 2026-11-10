"""Spec 047, T103 — el enlace del dueño, ya para un agente (historia 10;
requisito 31).

- **El enlace**: uno por agente, de un solo uso, que caduca a los 7 días y se
  guarda solo como huella; la URL sale una vez.
- **Uno pendiente**: crear otro ofrece revocar el pendiente («Revocar y crear»).
- **Al completarlo**: el número queda en el agente, en modo prueba con el número
  del dueño; el partner recibe el aviso y el enlace deja de servir.
- **La beta «WhatsApp login»**: solo donde Auphere la activó y nunca en la UE ni
  en el EEE.
- **El partner** ve el pendiente en la pestaña del agente y lo revoca; el de otro
  agente o de otro cliente es un 404.

Solo el cliente de Meta es de mentira.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import (
    Agent,
    Channel,
    ChannelSignupLink,
    ConsoleNotification,
    Tenant,
    WhatsappLoginBetaCountry,
)
from nexus_api.services import channel_config, meta_signup_service
from tests.conftest import console_headers
from tests.unit.test_endpoint_console_whatsapp import _FakeMeta

from ..business._business_world import Biz, new_business

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

OWNER = "+56 9 8765 4321"


def _svc() -> dict[str, str]:
    return console_headers(user_id="console-bff", partner_id=None, service=True)


def _token(url: str) -> str:
    return url.rsplit("/", 1)[-1]


@pytest.fixture
async def chile(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> Biz:
    biz = await new_business(
        client,
        db_session,
        console_world,
        name="Peluquería Lastarria",
        country="CL",
        timezone="America/Santiago",
        price_currency="CLP",
    )
    tenant = await db_session.get(Tenant, biz.tenant_id)
    assert tenant is not None
    tenant.owner_phone = OWNER
    await db_session.commit()
    return biz


async def _agent(db_session: AsyncSession, biz: Biz, name: str) -> uuid.UUID:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        agent = Agent(id=uuid.uuid4(), tenant_id=biz.tenant_id, name=name)
        db_session.add(agent)
    await db_session.commit()
    return agent.id


def _links(biz: Biz, agent_id: uuid.UUID) -> str:
    return f"/console/clients/{biz.ref}/agents/{agent_id}/channels/owner-links"


async def test_one_link_per_agent_shown_once_and_stored_as_a_fingerprint(
    client: Any, db_session: AsyncSession, chile: Biz
) -> None:
    recepcion = await _agent(db_session, chile, "Recepción")
    ventas = await _agent(db_session, chile, "Ventas")
    made = await client.post(
        _links(chile, recepcion), json={"mode": "coexistence"}, headers=chile.headers()
    )
    assert made.status_code == 201, made.text
    token = _token(made.json()["url"])
    expires = datetime.fromisoformat(made.json()["expires_at"])
    assert timedelta(days=6, hours=23) < expires - datetime.now(UTC) <= timedelta(days=7)
    stored = (await db_session.execute(sa.select(ChannelSignupLink.token_hash))).scalars().all()
    assert token not in stored, "solo la huella"

    # Otro agente tiene su propio enlace pendiente: no choca con el primero.
    other = await client.post(
        _links(chile, ventas), json={"mode": "cloud_api"}, headers=chile.headers()
    )
    assert other.status_code == 201

    # El mismo agente: ofrece revocar el pendiente.
    again = await client.post(
        _links(chile, recepcion), json={"mode": "cloud_api"}, headers=chile.headers()
    )
    assert again.status_code == 409
    assert again.json()["detail"] == {
        "code": "link_pending_exists",
        "link_id": made.json()["id"],
    }
    replaced = await client.post(
        _links(chile, recepcion),
        json={"mode": "cloud_api", "replace": True},
        headers=chile.headers(),
    )
    assert replaced.status_code == 201
    old = await client.get(f"/console/channel-signup/{token}", headers=_svc())
    assert old.json()["state"] == "revoked"

    # La pestaña del agente lo enseña pendiente, sin la URL.
    tab = await client.get(
        f"/console/clients/{chile.ref}/agents/{recepcion}/channels", headers=chile.headers()
    )
    assert tab.status_code == 200, tab.text
    assert tab.json()["pending_link"]["id"] == replaced.json()["id"]
    assert "url" not in tab.json()["pending_link"]


async def test_completing_it_puts_the_number_on_the_agent_in_test_mode(
    client: Any, db_session: AsyncSession, chile: Biz, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent_id = await _agent(db_session, chile, "Recepción")
    made = await client.post(
        _links(chile, agent_id), json={"mode": "coexistence"}, headers=chile.headers()
    )
    token = _token(made.json()["url"])
    number = f"+5692{uuid.uuid4().int % 10**7:07d}"
    monkeypatch.setattr(meta_signup_service, "build_meta_client", lambda: _FakeMeta(number))
    done = await client.post(
        f"/console/channel-signup/{token}", headers=_svc(), json={"code": "c", "waba_id": "W-047"}
    )
    assert done.status_code == 201, done.text
    channel_id = uuid.UUID(done.json()["channel_id"])

    db_session.expire_all()
    async with tenant_scoped_session(db_session, chile.tenant_id):
        channel = await db_session.get(Channel, channel_id)
        assert channel is not None and channel.agent_id == agent_id, "el número queda en el agente"
        assert channel.audience_mode == "team_only", "empieza en modo prueba (32.9)"
        config = await channel_config.read_config(db_session, channel)
    assert config["audience"]["test_numbers"] == ["+56987654321"], "con el número del dueño"

    tab = await client.get(
        f"/console/clients/{chile.ref}/agents/{agent_id}/channels", headers=chile.headers()
    )
    assert [c["id"] for c in tab.json()["channels"]] == [str(channel_id)]
    assert tab.json()["pending_link"] is None
    assert tab.json()["channels"][0]["visible_state"]["code"] == "team_only"

    notices = (
        await db_session.scalars(
            sa.select(ConsoleNotification).where(
                ConsoleNotification.partner_id == chile.partner_id,
                ConsoleNotification.kind == "channel.connected",
            )
        )
    ).all()
    assert len(notices) == 1 and notices[0].payload["agent_id"] == str(agent_id)

    used = await client.post(
        f"/console/channel-signup/{token}", headers=_svc(), json={"code": "c", "waba_id": "W-047"}
    )
    assert used.status_code == 410, "un solo uso"


async def test_the_whatsapp_login_beta_only_where_enabled_and_never_in_the_eu(
    client: Any, db_session: AsyncSession, chile: Biz
) -> None:
    agent_id = await _agent(db_session, chile, "Recepción")
    off = await client.post(
        _links(chile, agent_id), json={"mode": "whatsapp_login"}, headers=chile.headers()
    )
    assert off.status_code == 409
    assert off.json()["detail"]["code"] == "whatsapp_login_unavailable"

    db_session.add(WhatsappLoginBetaCountry(country="ES", enabled_by="op"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    db_session.add(WhatsappLoginBetaCountry(country="CL", enabled_by="op"))
    await db_session.commit()
    on = await client.post(
        _links(chile, agent_id), json={"mode": "whatsapp_login"}, headers=chile.headers()
    )
    assert on.status_code == 201, on.text
    assert on.json()["mode"] == "whatsapp_login"


async def test_the_partner_revokes_it_and_nobody_else_reaches_it(
    client: Any, db_session: AsyncSession, chile: Biz, console_world: dict[str, Any]
) -> None:
    recepcion = await _agent(db_session, chile, "Recepción")
    ventas = await _agent(db_session, chile, "Ventas")
    made = await client.post(_links(chile, recepcion), json={}, headers=chile.headers())
    link_id = made.json()["id"]

    sibling = await client.delete(f"{_links(chile, ventas)}/{link_id}", headers=chile.headers())
    assert sibling.status_code == 404, "el enlace de un agente no se toca desde su hermano"
    b = console_world["b"]
    stranger = await client.delete(
        f"/console/clients/{b['ref']}/agents/{recepcion}/channels/owner-links/{link_id}",
        headers=b["headers"](),
    )
    assert stranger.status_code == 404

    gone = await client.delete(f"{_links(chile, recepcion)}/{link_id}", headers=chile.headers())
    assert gone.status_code == 204
    state = await client.get(
        f"/console/channel-signup/{_token(made.json()['url'])}", headers=_svc()
    )
    assert state.json()["state"] == "revoked"
