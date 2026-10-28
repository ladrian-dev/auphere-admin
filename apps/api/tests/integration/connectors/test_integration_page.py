"""Spec 047, T126 — la página de cada integración (historia 21; requisito 36).

- **La página**: la cuenta, la salud con la hora de la última comprobación, los
  agentes con su permiso y los ajustes.
- **Los ajustes**, declarados en el catálogo y validados.
- **Una autorización caducada** queda «Hay que volver a autorizar», avisa al
  partner y deja desactualizadas las pruebas de los agentes que la usan.
- **«Desconectar para todos»** lista lo afectado y pide confirmación.
- **Los ajustes repartidos** pasan a la activación de cada agente (la 0194).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import (
    AgentConnectorActivation,
    ConsoleNotification,
    Partner,
    TenantConnector,
)
from nexus_api.db.models.agent_spec import AgentTest
from nexus_api.services.business.writes import drain_after_commit
from nexus_api.services.connectors.service import complete_consent_from_webhook
from nexus_api.services.testing.suites import add_test, ensure_suite

from ..business._business_world import Biz, new_business
from ._activation_world import SLUG, agent_with_spec, connect, seed_integration

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def biz(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> Biz:
    biz = await new_business(client, db_session, console_world, name="Tienda Lumen")
    partner = await db_session.get(Partner, biz.partner_id)
    assert partner is not None
    partner.console_v2_enabled_at = datetime.now(UTC)
    await db_session.commit()
    return biz


async def _activate(client: Any, biz: Biz, agent_id: uuid.UUID, body: dict[str, Any]) -> Any:
    return await client.put(
        f"/console/clients/{biz.ref}/agents/{agent_id}/activations/{SLUG}",
        json=body,
        headers=biz.headers(),
    )


async def test_the_page_shows_account_health_agents_and_settings(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    connector = await seed_integration(db_session)
    install_id = await connect(db_session, biz, connector)
    ventas = await agent_with_spec(db_session, biz, "Ventas")
    recepcion = await agent_with_spec(db_session, biz, "Recepción")
    bad = await _activate(
        client, biz, ventas, {"permission": "read_write", "settings": {"store_url": "http://x"}}
    )
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "invalid_settings"
    unknown = await _activate(
        client, biz, ventas, {"permission": "read_write", "settings": {"color": "rojo"}}
    )
    assert unknown.status_code == 422, "solo los ajustes que declara el catálogo"
    ok = await _activate(
        client,
        biz,
        ventas,
        {"permission": "read_write", "settings": {"store_url": "https://tienda.example"}},
    )
    assert ok.status_code == 200
    await _activate(client, biz, recepcion, {"permission": "read"})

    page = await client.get(
        f"/console/clients/{biz.ref}/connections/{install_id}", headers=biz.headers()
    )
    assert page.status_code == 200, page.text
    body = page.json()
    assert body["integration"] == SLUG and body["status"] == "connected"
    assert body["account"] == "https://tienda.example"
    assert "last_checked_at" in body and body["needs_reauth"] is False
    assert {(a["name"], a["permission"]) for a in body["agents"]} == {
        ("Ventas", "read_write"),
        ("Recepción", "read"),
    }
    assert next(a for a in body["agents"] if a["name"] == "Ventas")["settings"] == {
        "store_url": "https://tienda.example"
    }
    assert "credentials" not in page.text.lower() or "credentials_ref" not in page.text

    stranger = await client.get(
        f"/console/clients/client-b-1/connections/{install_id}", headers=biz.headers()
    )
    assert stranger.status_code in (403, 404)


async def test_an_expired_authorization_is_flagged_tells_the_partner_and_the_tests(
    db_session: AsyncSession, biz: Biz, fake_composio: Any
) -> None:
    connector = await seed_integration(db_session)
    install_id = await connect(db_session, biz, connector)
    ventas = await agent_with_spec(db_session, biz, "Ventas")
    async with tenant_scoped_session(db_session, biz.tenant_id):
        install = await db_session.get(TenantConnector, install_id)
        assert install is not None
        install.credentials_ref = {"composio_connection_id": "ca_expired"}
        db_session.add(
            AgentConnectorActivation(
                tenant_id=biz.tenant_id,
                agent_id=ventas,
                connector_id=install_id,
                permission="read_write",
                settings={},
            )
        )
        suite = await ensure_suite(db_session, ventas)
        await add_test(
            db_session, suite, {"name": "Pedido", "first_message": "Quiero un taladro"}, kind="case"
        )
    await db_session.commit()
    async with tenant_scoped_session(db_session, biz.tenant_id):
        await complete_consent_from_webhook(
            db_session,
            composio_connection_id="ca_expired",
            upstream_status="EXPIRED",
            granted_scopes=[],
            composio=fake_composio,
        )
    await db_session.commit()
    await drain_after_commit()
    async with tenant_scoped_session(db_session, biz.tenant_id):
        install = await db_session.get(TenantConnector, install_id, populate_existing=True)
        stale = await db_session.scalar(sa.select(AgentTest.stale))
    await db_session.commit()
    assert install is not None and install.status == "needs_reauth"
    assert stale is True, "se refleja en las pruebas de los agentes que la usan"
    notices = (
        await db_session.scalars(
            sa.select(ConsoleNotification).where(
                ConsoleNotification.partner_id == biz.partner_id,
                ConsoleNotification.kind == "integration.reauth_required",
            )
        )
    ).all()
    assert len(notices) == 1 and notices[0].payload["integration"] == SLUG


async def test_disconnect_for_everyone_lists_what_breaks_and_asks_first(
    client: Any, db_session: AsyncSession, biz: Biz
) -> None:
    connector = await seed_integration(db_session)
    install_id = await connect(db_session, biz, connector)
    ventas = await agent_with_spec(db_session, biz, "Ventas")
    await _activate(client, biz, ventas, {"permission": "read_write"})
    url = f"/console/clients/{biz.ref}/connections/{install_id}/disconnect"
    ask = await client.post(url, json={}, headers=biz.headers())
    assert ask.status_code == 409
    assert ask.json()["detail"]["code"] == "confirm_required"
    assert ask.json()["detail"]["affected"] == [
        {
            "agent_id": str(ventas),
            "name": "Ventas",
            "skills": ["orders"],
            "procedures": ["Tomar un pedido"],
        }
    ]
    done = await client.post(url, json={"confirm": True}, headers=biz.headers())
    assert done.status_code == 200, done.text
    async with tenant_scoped_session(db_session, biz.tenant_id):
        install = await db_session.get(TenantConnector, install_id, populate_existing=True)
        left = await db_session.scalar(
            sa.select(sa.func.count()).select_from(AgentConnectorActivation)
        )
    await db_session.commit()
    assert install is not None and install.status == "disconnected"
    assert left == 0


def test_the_spread_settings_move_to_each_activation() -> None:
    """La regla de la 0194: la tienda y el negocio de la conexión, y los
    recordatorios del agente de cobranza, pasan a la activación."""
    import importlib.util
    from pathlib import Path

    path = (
        Path(__file__).resolve().parents[3]
        / "alembic"
        / "versions"
        / "0194_connector_activations.py"
    )
    spec = importlib.util.spec_from_file_location("m0194", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    reminders = {"enabled": True, "hour_local": 10}
    assert module.settings_for(
        "woocommerce", {"endpoint_meta": {"store_url": "https://t.example", "_": "console"}}, {}
    ) == {"store_url": "https://t.example"}
    assert module.settings_for(
        "amigable_cobro",
        {"endpoint_meta": {"business_uuid": "b-1", "base_url": "https://a.example"}},
        {"reminders": reminders},
    ) == {"business_uuid": "b-1", "base_url": "https://a.example", "reminders": reminders}
    assert module.settings_for("googlecalendar", {}, {"reminders": reminders}) == {}
