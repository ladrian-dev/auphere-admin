"""Spec 060, T015 y T016 — quitar el acceso no rompe nada y vuelve intacto.

- **5.5 y 5.6**: deshabilitar un conector para el partner no toca la conexión, sus
  credenciales, sus activaciones ni sus excepciones; al rehabilitarlo, el agente
  recupera exactamente las mismas herramientas.
- **5.7 y 1.6**: un agente que ya tenía herramientas de ese conector se sigue
  pudiendo editar y guardar, y las conserva sin mostrarlas; añadir una nueva no se
  puede.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.runtime.pipeline import _load_tool_policy
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AgentConfig,
    AgentConnectorActivation,
    ConnectorPartnerAccess,
    Partner,
    TenantConnector,
    TenantConnectorToolOverride,
)
from nexus_api.services import activations

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


async def _lose_access(db_session: AsyncSession, biz: Biz) -> None:
    db_session.add(
        ConnectorPartnerAccess(
            connector_slug=SLUG, partner_id=biz.partner_id, enabled=False, reason="t", set_by="t"
        )
    )
    await db_session.commit()


async def _snapshot(tenant_id: uuid.UUID) -> dict[str, Any]:
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
        install = (await s.scalars(sa.select(TenantConnector))).one()
        acts = (
            await s.execute(
                sa.select(AgentConnectorActivation.agent_id, AgentConnectorActivation.permission)
            )
        ).all()
        overrides = (
            await s.execute(
                sa.select(TenantConnectorToolOverride.tool_name, TenantConnectorToolOverride.mode)
            )
        ).all()
        return {
            "status": str(getattr(install.status, "value", install.status)),
            "credentials_ref": install.credentials_ref,
            "activations": sorted((str(a), p) for a, p in acts),
            "overrides": sorted((n, str(m)) for n, m in overrides),
        }


async def test_losing_access_changes_nothing_and_coming_back_restores_it(
    db_session: AsyncSession, biz: Biz, seeded_catalog: None, fake_composio: Any
) -> None:
    connector = await seed_integration(db_session)
    agent = await agent_with_spec(db_session, biz, "Ventas")
    install_id = await connect(db_session, biz, connector)
    async with tenant_scoped_session(db_session, biz.tenant_id):
        db_session.add(
            AgentConnectorActivation(
                tenant_id=biz.tenant_id,
                agent_id=agent,
                connector_id=install_id,
                permission="ask_before_write",
                settings={},
            )
        )
        db_session.add(
            TenantConnectorToolOverride(
                tenant_id=biz.tenant_id, tool_name=WRITE, mode="blocked", set_by_actor="t"
            )
        )
    await db_session.commit()

    before_policy = await _load_tool_policy(biz.tenant_id, agent)
    before = await _snapshot(biz.tenant_id)
    assert activations.allowed_names((READ, WRITE), before_policy) == (READ, WRITE)

    await _lose_access(db_session, biz)
    assert (
        activations.allowed_names((READ, WRITE), await _load_tool_policy(biz.tenant_id, agent))
        == ()
    )
    assert await _snapshot(biz.tenant_id) == before, "5.5: nada cambia de estado"

    await db_session.execute(sa.delete(ConnectorPartnerAccess))
    await db_session.commit()
    after_policy = await _load_tool_policy(biz.tenant_id, agent)
    assert after_policy == before_policy, "5.6: vuelve exactamente igual"
    assert await _snapshot(biz.tenant_id) == before


async def _agent(db_session: AsyncSession, biz: Biz, name: str) -> uuid.UUID:
    """El agente del mundo de activaciones, con una descripción que el AgentSpec
    acepta al leer el borrador (20 caracteres o más)."""
    agent_id = await agent_with_spec(db_session, biz, name)
    async with tenant_scoped_session(db_session, biz.tenant_id):
        cfg = (
            await db_session.scalars(sa.select(AgentConfig).where(AgentConfig.agent_id == agent_id))
        ).first()
        assert cfg is not None
        spec = dict(cfg.spec or {})
        spec["identity"] = {**spec["identity"], "description": "Vende por WhatsApp a sus clientes."}
        cfg.spec = spec
    await db_session.commit()
    return agent_id


async def test_an_agent_keeps_what_it_had_and_cannot_add_new_withheld_tools(
    client: Any, db_session: AsyncSession, biz: Biz, seeded_catalog: None, fake_composio: Any
) -> None:
    connector = await seed_integration(db_session)
    ventas = await _agent(db_session, biz, "Ventas")
    await connect(db_session, biz, connector)
    await _lose_access(db_session, biz)

    caps = await client.get(
        f"/console/clients/{biz.ref}/capabilities?agent={ventas}", headers=biz.headers()
    )
    assert caps.status_code == 200, caps.text
    assert READ not in caps.text, "5.1: no se muestran"

    # Editar y guardar el agente entero (el PATCH valida la ficha completa) no falla
    # y conserva lo del conector retenido: la habilidad y la herramienta del
    # procedimiento.
    url = f"/console/clients/{biz.ref}/agents/{ventas}/draft"
    draft = (await client.get(url, headers=biz.headers())).json()
    spec = dict(draft["spec"])
    edited = await client.patch(
        url,
        json={"spec": {**spec, "rules": ["Pide siempre el nombre."]}},
        headers={**biz.headers(), "If-Match": f'"{draft["revision"]}"'},
    )
    assert edited.status_code == 200, edited.text
    out = edited.json()["spec"]
    assert any(s.get("integration") == SLUG for s in out.get("skills") or []), "5.7"
    assert WRITE in {t for p in out.get("procedures") or [] for t in p.get("tools") or []}

    # Añadir una nueva de ese conector a otro agente que no la tenía, no se puede.
    recepcion = await _agent(db_session, biz, "Recepción")
    async with tenant_scoped_session(db_session, biz.tenant_id):
        cfg = (
            await db_session.scalars(
                sa.select(AgentConfig).where(AgentConfig.agent_id == recepcion)
            )
        ).first()
        assert cfg is not None
        cfg.tools = []
        cfg.spec = {**(cfg.spec or {}), "skills": [], "procedures": []}
    await db_session.commit()
    url_r = f"/console/clients/{biz.ref}/agents/{recepcion}/draft"
    draft_r = (await client.get(url_r, headers=biz.headers())).json()
    spec_r = dict(draft_r["spec"])
    added = await client.patch(
        url_r,
        json={"spec": {**spec_r, "tools": [*(spec_r.get("tools") or []), READ]}},
        headers={**biz.headers(), "If-Match": f'"{draft_r["revision"]}"'},
    )
    assert added.status_code == 422, added.text
    assert "tool_not_allowed" in added.text
