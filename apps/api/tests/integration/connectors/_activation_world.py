"""El mundo de las pruebas de activaciones — spec 047, T125 y T126.

Una integración sintética («Tienda», ``api_key``) con una herramienta de lectura y
una de escritura, conectada una vez para el cliente, y agentes publicados con su
especificación (una habilidad que la pide y un procedimiento que la usa).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import (
    AgentConfig,
    Connector,
    TenantConnector,
    ToolCatalog,
    ToolStatus,
)

from ..business._business_world import Biz, seed_agent

SLUG = "tienda_test"
READ = "tienda_test.list_items"
WRITE = "tienda_test.create_order"

SPEC: dict[str, Any] = {
    "schema_version": "1",
    "mode": "instructions",
    "identity": {"name": "Ventas", "description": "Vende por WhatsApp."},
    "instructions": {"legacy_text": "Vende."},
    "skills": [{"key": "orders", "enabled": True, "integration": SLUG}],
    "procedures": [
        {
            "id": "pedido",
            "title": "Tomar un pedido",
            "when": "Cuando piden comprar",
            "steps": "Crea el pedido.",
            "tools": [WRITE],
        }
    ],
    "ai_disclosure": {"decided": False},
    "model_policy": {"kind": "profile", "profile": "auto"},
    "memory": {"scope": "shared"},
}


async def seed_integration(db_session: Any) -> Connector:
    existing = await db_session.scalar(sa.select(Connector).where(Connector.slug == SLUG))
    if existing is not None:
        return existing
    connector = Connector(
        slug=SLUG,
        display_name="Tienda Test",
        vendor="Test",
        category="ecommerce",
        auth_kind="api_key",
        mcp_server_ref=f"internal:{SLUG}",
        auto_enable_on_connect=True,
        auto_enable_destructive=False,
        status="available",
        settings_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {"store_url": {"type": "string", "pattern": "^https://"}},
        },
    )
    db_session.add(connector)
    await db_session.flush()
    for name, read_only in ((READ, True), (WRITE, False)):
        db_session.add(
            ToolCatalog(
                name=name,
                description=name,
                mcp_server=f"internal:{SLUG}",
                status=ToolStatus.ACTIVE,
                connector_id=connector.id,
                read_only=read_only,
                destructive=not read_only,
                default_mode="always",
            )
        )
    await db_session.commit()
    return connector


async def connect(
    db_session: Any, biz: Biz, connector: Connector, *, status: str = "connected"
) -> uuid.UUID:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        install = TenantConnector(
            tenant_id=biz.tenant_id,
            connector_id=connector.id,
            status=status,
            credentials_ref={"endpoint_meta": {"store_url": "https://tienda.example"}},
            connected_at=datetime.now(UTC),
        )
        db_session.add(install)
        await db_session.flush()
        install_id = install.id
    await db_session.commit()
    return install_id


async def agent_with_spec(db_session: Any, biz: Biz, name: str) -> uuid.UUID:
    agent_id, cfg_id = await seed_agent(
        db_session, biz.tenant_id, name=name, prompt="Vende.", tools=[READ, WRITE]
    )
    async with tenant_scoped_session(db_session, biz.tenant_id):
        cfg = await db_session.get(AgentConfig, cfg_id)
        assert cfg is not None
        cfg.spec = {**SPEC, "identity": {**SPEC["identity"], "name": name}}
    await db_session.commit()
    return agent_id
