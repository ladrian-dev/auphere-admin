"""Spec 047, T125 — autorizar una vez por cliente, activar por agente (historia 21;
requisito 35).

- **La conexión es del cliente; la activación, del agente.**
- **El catálogo** del agente pone primero lo que piden sus habilidades.
- **Ya autorizada**, activarla en otro agente no la vuelve a pedir; sin autorizar,
  se abre la autorización y al terminar queda activada con el permiso elegido.
- **El runtime aplica los permisos**: sin activación, nada; «Solo leer», sin
  escrituras; «Preguntar antes de escribir», aprobación durable del dueño.
- **Quitar** una activación quita sus herramientas y dice qué habilidades afecta.
- **Lo de antes sigue**: sin activaciones y fuera de la consola nueva, nada cambia;
  al conectar por el camino de siempre, el agente recibe su activación.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.runtime.llm import ToolCall
from nexus_worker.runtime.pipeline import _approval_envelope, _load_tool_policy
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import (
    AgentConnectorActivation,
    Connector,
    Conversation,
    ConversationStatus,
    Customer,
    OwnerConsultation,
    Partner,
    TenantConnector,
)
from nexus_api.services import activations
from nexus_api.services.connectors.service import (
    auto_enable_connector_tools,
    complete_consent_from_webhook,
)

from ..business._business_world import Biz, new_business
from ._activation_world import READ, SLUG, WRITE, agent_with_spec, connect, seed_integration

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def biz(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> Biz:
    biz = await new_business(client, db_session, console_world, name="Tienda Lumen")
    partner = await db_session.get(Partner, biz.partner_id)
    assert partner is not None
    partner.console_v2_enabled_at = datetime.now(UTC)
    await db_session.commit()
    return biz


def _agent_url(biz: Biz, agent_id: uuid.UUID) -> str:
    return f"/console/clients/{biz.ref}/agents/{agent_id}"


async def _policy(biz: Biz, agent_id: uuid.UUID) -> activations.ToolPolicy:
    return await _load_tool_policy(biz.tenant_id, agent_id)


async def test_one_connection_per_client_and_an_activation_per_agent(
    client: Any, db_session: AsyncSession, biz: Biz, seeded_catalog: None, fake_composio: Any
) -> None:
    connector = await seed_integration(db_session)
    ventas = await agent_with_spec(db_session, biz, "Ventas")
    recepcion = await agent_with_spec(db_session, biz, "Recepción")
    install_id = await connect(db_session, biz, connector)

    catalog = await client.get(f"{_agent_url(biz, ventas)}/integrations", headers=biz.headers())
    assert catalog.status_code == 200, catalog.text
    first = catalog.json()[0]
    assert first["slug"] == SLUG and first["needed"] is True, "primero lo que piden sus habilidades"
    assert first["connection"]["status"] == "connected" and first["activation"] is None
    assert first["settings_schema"]["properties"]["store_url"]

    put = await client.put(
        f"{_agent_url(biz, ventas)}/activations/{SLUG}",
        json={"permission": "read_write", "settings": {"store_url": "https://tienda.example"}},
        headers=biz.headers(),
    )
    assert put.status_code == 200, put.text
    # Ya autorizada: activarla en otro agente no vuelve a pedir la autorización.
    again = await client.post(
        f"/console/clients/{biz.ref}/connections",
        json={"integration": SLUG, "agent_id": str(recepcion), "permission": "read"},
        headers=biz.headers(),
    )
    assert again.status_code == 201 and again.json()["status"] == "activated"
    async with tenant_scoped_session(db_session, biz.tenant_id):
        installs = (await db_session.scalars(sa.select(TenantConnector))).all()
        rows = (await db_session.scalars(sa.select(AgentConnectorActivation))).all()
    await db_session.commit()
    assert [i.id for i in installs if i.connector_id == connector.id] == [install_id]
    assert {(r.agent_id, r.permission) for r in rows} == {
        (ventas, "read_write"),
        (recepcion, "read"),
    }


async def test_the_agent_catalog_leaves_out_the_channels(
    client: Any, db_session: AsyncSession, biz: Biz, seeded_catalog: None, fake_composio: Any
) -> None:
    # Recorrido UI de la 047: WhatsApp y TikTok salían en Conectores del agente
    # como «Sin conectar» aunque el número estuviera conectado. Son canales
    # (``provider_meta.channel_only``): viven en Canales, como en el admin.
    await seed_integration(db_session)
    db_session.add(
        Connector(
            slug="canal_test",
            display_name="Canal Test",
            vendor="Test",
            category="messaging",
            auth_kind="api_key",
            mcp_server_ref="internal:canal_test",
            status="available",
            provider_meta={"channel_only": True},
        )
    )
    await db_session.commit()
    ventas = await agent_with_spec(db_session, biz, "Ventas")
    catalog = await client.get(f"{_agent_url(biz, ventas)}/integrations", headers=biz.headers())
    assert catalog.status_code == 200, catalog.text
    slugs = {row["slug"] for row in catalog.json()}
    assert SLUG in slugs
    assert "canal_test" not in slugs


async def test_connecting_without_authorization_authorizes_then_activates(
    client: Any, db_session: AsyncSession, biz: Biz, seeded_catalog: None, fake_composio: Any
) -> None:
    await seed_integration(db_session)
    ventas = await agent_with_spec(db_session, biz, "Ventas")
    form = await client.post(
        f"/console/clients/{biz.ref}/connections",
        json={"integration": "woocommerce", "agent_id": str(ventas)},
        headers=biz.headers(),
    )
    assert form.status_code == 409 and form.json()["detail"]["code"] == "authorize_with_form"

    oauth = await client.post(
        f"/console/clients/{biz.ref}/connections",
        json={
            "integration": "googlecalendar",
            "agent_id": str(ventas),
            "permission": "ask_before_write",
        },
        headers=biz.headers(),
    )
    assert oauth.status_code == 201, oauth.text
    assert "consent_token=" in oauth.json()["signed_consent_url"]
    async with tenant_scoped_session(db_session, biz.tenant_id):
        install = await db_session.scalar(sa.select(TenantConnector))
        assert install is not None and install.config["pending_activation"]["agent_id"] == str(
            ventas
        )
        connection_id = str(install.credentials_ref.get("composio_connection_id"))
        await complete_consent_from_webhook(
            db_session,
            composio_connection_id=connection_id,
            upstream_status="ACTIVE",
            granted_scopes=[],
            composio=fake_composio,
        )
        activation = await db_session.scalar(sa.select(AgentConnectorActivation))
        refreshed = await db_session.get(TenantConnector, install.id)
    await db_session.commit()
    assert activation is not None and activation.agent_id == ventas
    assert activation.permission == "ask_before_write", "con el permiso elegido al conectar"
    assert refreshed is not None and "pending_activation" not in refreshed.config


async def test_the_runtime_applies_each_permission(db_session: AsyncSession, biz: Biz) -> None:
    connector = await seed_integration(db_session)
    install_id = await connect(db_session, biz, connector)
    agents = {
        perm: await agent_with_spec(db_session, biz, f"Agente {perm}")
        for perm in ("read", "ask_before_write", "read_write", "none")
    }
    async with tenant_scoped_session(db_session, biz.tenant_id):
        for perm, agent_id in agents.items():
            if perm != "none":
                db_session.add(
                    AgentConnectorActivation(
                        tenant_id=biz.tenant_id,
                        agent_id=agent_id,
                        connector_id=install_id,
                        permission=perm,
                        settings={},
                    )
                )
    await db_session.commit()
    read = await _policy(biz, agents["read"])
    assert read.blocked == {WRITE} and not read.needs_approval, "«Solo leer»: sin escrituras"
    ask = await _policy(biz, agents["ask_before_write"])
    assert not ask.blocked and ask.needs_approval == {WRITE}
    full = await _policy(biz, agents["read_write"])
    assert not full.blocked and not full.needs_approval
    none = await _policy(biz, agents["none"])
    assert none.blocked == {READ, WRITE}, "sin activación no hay uso (garantías 2 y 9)"


async def test_ask_before_write_asks_the_owner_and_runs_once_when_approved(
    db_session: AsyncSession, biz: Biz
) -> None:
    connector = await seed_integration(db_session)
    install_id = await connect(db_session, biz, connector)
    agent_id = await agent_with_spec(db_session, biz, "Ventas")
    async with tenant_scoped_session(db_session, biz.tenant_id):
        db_session.add(
            AgentConnectorActivation(
                tenant_id=biz.tenant_id,
                agent_id=agent_id,
                connector_id=install_id,
                permission="ask_before_write",
                settings={},
            )
        )
        from nexus_api.db.models import Channel, ChannelType

        channel = Channel(
            tenant_id=biz.tenant_id,
            type=ChannelType.WHATSAPP,
            provider="meta",
            provider_identifier=f"+3491{uuid.uuid4().int % 10**7:07d}",
            config={},
            agent_id=agent_id,
        )
        customer = Customer(tenant_id=biz.tenant_id, identifier="34600555111", preferences={})
        db_session.add_all([channel, customer])
        await db_session.flush()
        conversation = Conversation(
            tenant_id=biz.tenant_id,
            channel_id=channel.id,
            customer_id=customer.id,
            status=ConversationStatus.OPEN,
        )
        db_session.add(conversation)
        await db_session.flush()
        conv_id = conversation.id
    await db_session.commit()
    state: Any = {
        "tenant_id": str(biz.tenant_id),
        "conversation_id": str(conv_id),
        "agent_id": str(agent_id),
    }
    call = ToolCall(id="c1", name=WRITE, arguments={"product": "taladro", "qty": 2})

    asked = await _approval_envelope(state, call, "sales")
    assert asked is not None and asked["status"] == "approval_requested"
    pending = await _approval_envelope(state, call, "sales")
    assert pending is not None and pending["status"] == "approval_pending", (
        "no se pregunta dos veces"
    )

    async with tenant_scoped_session(db_session, biz.tenant_id):
        row = await db_session.scalar(sa.select(OwnerConsultation))
        assert row is not None and row.expected_reply_kind == "yes_no"
        assert "taladro" in row.question_text
        row.status = "answered"
        row.sent_at = datetime.now(UTC)
        row.owner_response_at = datetime.now(UTC)
        row.owner_response_text = "Sí, adelante"
    await db_session.commit()
    assert await _approval_envelope(state, call, "sales") is None, "aprobada: se ejecuta"
    again = await _approval_envelope(state, call, "sales")
    assert again is not None and again["status"] == "approval_requested", "una sola vez"

    other = ToolCall(id="c2", name=WRITE, arguments={"product": "sierra", "qty": 1})
    await _approval_envelope(state, other, "sales")
    async with tenant_scoped_session(db_session, biz.tenant_id):
        rows = (
            await db_session.scalars(
                sa.select(OwnerConsultation).where(
                    OwnerConsultation.question_text.contains("sierra")
                )
            )
        ).all()
        rows[0].status = "answered"
        rows[0].sent_at = datetime.now(UTC)
        rows[0].owner_response_at = datetime.now(UTC)
        rows[0].owner_response_text = "No"
    await db_session.commit()
    denied = await _approval_envelope(state, other, "sales")
    assert denied is not None and denied["status"] == "approval_denied"


async def test_removing_an_activation_removes_its_tools_and_names_the_skills(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    connector = await seed_integration(db_session)
    await connect(db_session, biz, connector)
    agent_id = await agent_with_spec(db_session, biz, "Ventas")
    await client.put(
        f"{_agent_url(biz, agent_id)}/activations/{SLUG}",
        json={"permission": "read_write"},
        headers=biz.headers(),
    )
    assert not (await _policy(biz, agent_id)).blocked
    removed = await client.delete(
        f"{_agent_url(biz, agent_id)}/activations/{SLUG}", headers=biz.headers()
    )
    assert removed.status_code == 200, removed.text
    assert removed.json() == {"skills": ["orders"], "procedures": ["Tomar un pedido"]}
    assert (await _policy(biz, agent_id)).blocked == {READ, WRITE}


async def test_what_came_before_keeps_working(
    client: Any, db_session: AsyncSession, console_world: dict[str, Any]
) -> None:
    """Un partner con la consola de hoy y una conexión sin activaciones: nada
    cambia; al conectar por el camino de siempre, el agente recibe la suya."""
    legacy = await new_business(client, db_session, console_world, name="Ferretería Vieja")
    connector = await seed_integration(db_session)
    agent_id = await agent_with_spec(db_session, legacy, "Recepción")
    install_id = await connect(db_session, legacy, connector)
    assert not (await _policy(legacy, agent_id)).blocked, "sin activaciones, como antes"
    async with tenant_scoped_session(db_session, legacy.tenant_id):
        await auto_enable_connector_tools(
            db_session, tenant_id=legacy.tenant_id, connector=connector, actor="test"
        )
        rows = (await db_session.scalars(sa.select(AgentConnectorActivation))).all()
    await db_session.commit()
    assert [(r.agent_id, r.connector_id) for r in rows] == [(agent_id, install_id)]
    assert not (await _policy(legacy, agent_id)).blocked
