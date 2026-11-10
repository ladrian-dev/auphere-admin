"""Spec 023 (Requisitos 4.1, 4.2): ``GET /console/clients/{ref}/connectors``
marks as recommended exactly what the client's sector template lists, and
recommending never hides a card nor moves it out of its category.
"""

from __future__ import annotations

import uuid

import pytest

from nexus_api.core.tenant_context import apply_tenant_to_session, tenant_context
from nexus_api.db.models import Agent, AgentConfig, AgentConfigStatus, Connector, TenantConnector
from nexus_api.services.connectors import catalog as connector_catalog

pytestmark = pytest.mark.asyncio


async def _active_config(db_session, tenant_id, template: str) -> None:
    await apply_tenant_to_session(db_session, tenant_id)
    with tenant_context(tenant_id):
        db_session.add(
            AgentConfig(
                tenant_id=tenant_id,
                version=1,
                status=AgentConfigStatus.ACTIVE,
                system_prompt_rendered="Sos el asistente.",
                channels=[],
                tools=[],
                policies={},
                seed_template_ref=template,
            )
        )
        await db_session.commit()


async def _cards(client, w) -> dict[str, dict]:
    r = await client.get(f"/console/clients/{w['ref']}/connectors", headers=w["headers"]())
    assert r.status_code == 200, r.text
    return {c["slug"]: c for c in r.json()}


async def test_the_sector_template_decides_who_is_recommended(
    client, console_world, db_session, seeded_catalog, fake_composio
) -> None:
    a = console_world["a"]
    await _active_config(db_session, a["tenant_id"], "barbershop_v1")

    cards = await _cards(client, a)
    assert "agendapro" not in cards  # spec 048
    assert cards["calendly"]["recommended"] is True  # dynamic, from the fake provider
    assert cards["woocommerce"]["recommended"] is False
    # Spec 043, R11.8: se conecta por profesional en Reservas, no a un agente.
    assert "googlecalendar" not in cards


async def test_without_a_sector_nobody_is_recommended(
    client, console_world, db_session, seeded_catalog, fake_composio
) -> None:
    b = console_world["b"]
    cards = await _cards(client, b)
    assert cards, "the catalogue is empty"
    assert not any(c["recommended"] for c in cards.values())


async def test_recommending_neither_hides_nor_moves_a_card(
    client, console_world, db_session, seeded_catalog, fake_composio
) -> None:
    a = console_world["a"]
    before = await _cards(client, a)
    await _active_config(db_session, a["tenant_id"], "cobranza_v1")
    after = await _cards(client, a)

    assert set(after) == set(before)
    assert {s: c["category"] for s, c in after.items()} == {
        s: c["category"] for s, c in before.items()
    }
    assert after["woocommerce"]["recommended"] is False
    assert after["calendly"]["recommended"] is False


async def test_a_google_connection_from_before_can_only_be_removed(
    client, console_world, db_session, seeded_catalog, fake_composio
) -> None:
    """Spec 043, R11.8 y punto 18 de la revisión: reconectarla responde 409 y manda a un panel que
    el partner no tiene. La tarjeta lo dice, y en el agente ni aparece: no es de ningún agente."""
    a = console_world["a"]
    cards = await _cards(client, a)
    assert "googlecalendar" not in cards, "without a connection it is not offered"
    connector = Connector(
        slug="googlecalendar",
        display_name="Google Calendar",
        vendor="Google",
        category="calendar",
        auth_kind="oauth_composio",
        mcp_server_ref="composio:googlecalendar",
    )
    db_session.add(connector)
    await db_session.flush()
    connector_id = connector.id
    await db_session.commit()
    await apply_tenant_to_session(db_session, a["tenant_id"])
    agent_id = uuid.uuid4()
    with tenant_context(a["tenant_id"]):
        db_session.add(
            TenantConnector(tenant_id=a["tenant_id"], connector_id=connector_id, status="connected")
        )
        db_session.add(Agent(id=agent_id, tenant_id=a["tenant_id"], name="Ana"))
        await db_session.commit()

    google = (await _cards(client, a))["googlecalendar"]
    assert google["installed"] is True
    assert google["managed_elsewhere"] is True

    r = await client.get(
        f"/console/clients/{a['ref']}/agents/{agent_id}/integrations", headers=a["headers"]()
    )
    assert r.status_code == 200, r.text
    assert "googlecalendar" not in {i["slug"] for i in r.json()}


@pytest.mark.parametrize(
    ("installed", "answer"),
    [("needs_reauth", 201), ("error", 201), ("disconnected", 409), (None, 409)],
)
async def test_a_google_connection_from_before_can_be_renewed_but_not_made_new(
    client, console_world, db_session, seeded_catalog, fake_composio, installed, answer
) -> None:
    """Revisión, D4: al agente que aún reserva en Google le caduca la conexión y el partner no
    podía renovarla. R11.8 sigue en pie: no se conecta uno nuevo."""
    a = console_world["a"]
    if installed is not None:
        connector = await connector_catalog.ensure_composio_connector_persisted(
            db_session, fake_composio, "googlecalendar"
        )
        connector_id = connector.id
        await db_session.commit()
        await apply_tenant_to_session(db_session, a["tenant_id"])
        with tenant_context(a["tenant_id"]):
            db_session.add(
                TenantConnector(
                    tenant_id=a["tenant_id"], connector_id=connector_id, status=installed
                )
            )
            await db_session.commit()

    r = await client.post(
        f"/console/clients/{a['ref']}/connectors/googlecalendar/consent", headers=a["headers"]()
    )

    assert r.status_code == answer, r.text
    if answer == 409:
        assert r.json()["detail"]["code"] == "connect_from_reservas"
