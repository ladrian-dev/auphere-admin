"""Spec 047, enmienda del 2026-10-29, T196 — herramientas pendientes de conexión
(requisito 62; research D53).

- El borrador **conserva** las herramientas que pide una habilidad aunque su
  integración no esté conectada, junto con la petición de conexión (62.1).
- El validador las acepta si están en el catálogo y permitidas al partner (62.4);
  lo desconocido, lo interno y lo retirado se sigue rechazando.
- Activar la conexión en el agente deja sus pruebas desactualizadas (62.3).

Que el runtime no las vea sin conexión y activación (62.2) lo barre
``tests/isolation/test_44_agent_within_client.py``.
"""

from __future__ import annotations

import copy
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.services.agent_spec.validator import Context, ToolInfo, validate_spec
from nexus_api.services.builder.agent_draft import DraftRequest, sanitize
from nexus_api.services.business.compilation import Facts
from tests.unit.test_agent_spec_contract import STRUCTURED

PENDING = "tienda_test.list_items"

CTX = Context(
    tools={
        "reservas.find_slots": ToolInfo("reservas.find_slots"),
        "escalate.escalate_to_human": ToolInfo("escalate.escalate_to_human"),
        PENDING: ToolInfo(PENDING, integration="tienda_test", connected=False),
        "ops.sync_internal": ToolInfo("ops.sync_internal", status="internal"),
        # El catálogo de Meta del canal: sin conector ni activación que la retenga.
        "catalog.search_products": ToolInfo(
            "catalog.search_products",
            integration="channel_catalog",
            connected=False,
            activatable=False,
        ),
        "shopify.list_orders": ToolInfo(
            "shopify.list_orders", integration="shopify", integration_offered=False
        ),
    }
)


def test_the_draft_keeps_a_tool_whose_integration_is_not_connected() -> None:
    draft = sanitize(
        {
            "tools": [
                "reservas.find_slots",
                PENDING,
                "shopify.list_orders",
                "nada.que_ver",
                "catalog.search_products",
            ],
            "skills": [{"key": "orders", "enabled": True, "integration": "tienda_test"}],
            "instructions": [{"title": "Qué haces", "body": "Vende por WhatsApp."}],
        },
        DraftRequest.clean("Ventas", "Vende los productos de la tienda por WhatsApp."),
        CTX,
        Facts(name="Tienda Lumen"),
        model_policy=None,
    )
    spec = draft.spec
    assert PENDING in (spec.tools or []), "62.1: se guarda, pendiente de conexión"
    assert "shopify.list_orders" not in (spec.tools or []), "lo no permitido sigue fuera"
    assert "nada.que_ver" not in (spec.tools or [])
    requests = {r.integration for r in spec.connection_requests or []}
    # Spec 047, enmienda del 2026-10-30 (65.3): el catálogo de Meta se enlaza en
    # Canales, no se «conecta» desde el agente; sale como lo que falta.
    assert requests == {"tienda_test"}, "con su petición de conexión"
    dropped = {d["tool"]: d["why"] for d in draft.dropped_tools}
    assert PENDING not in dropped
    assert dropped["shopify.list_orders"] == "tool_not_allowed"
    assert dropped["catalog.search_products"] == "tool_not_connected", "sin activación, fuera"
    assert ("channel_catalog", "not_linked") in {(m["key"], m["reason"]) for m in draft.missing}


def test_the_validator_accepts_a_pending_tool_from_the_catalog() -> None:
    doc = copy.deepcopy(STRUCTURED)
    doc["tools"] = ["reservas.find_slots", PENDING]
    doc["connection_requests"] = [{"integration": "tienda_test", "reason": "Para los pedidos"}]
    for author in ("person", "builder"):
        spec, problems = validate_spec(doc, CTX, author=author)
        assert spec is not None
        assert not [p for p in problems if p.pointer.startswith("/tools")], problems
    for tool, code in (
        ("ops.sync_internal", "tool_not_allowed"),
        ("x.y", "tool_unknown"),
        # Sin activación que la retenga en el turno, sin conectar sigue sin entrar.
        ("catalog.search_products", "tool_not_connected"),
    ):
        doc["tools"] = ["reservas.find_slots", tool]
        _spec, problems = validate_spec(doc, CTX)
        assert ("/tools/1", code) in {(p.pointer, p.code) for p in problems}


pytestmark = pytest.mark.asyncio


async def test_activating_the_connection_marks_the_agents_tests_stale(
    client: Any, db_session: AsyncSession, console_world: dict[str, Any]
) -> None:
    from nexus_api.core.tenant_context import tenant_scoped_session
    from nexus_api.db.models import Partner
    from nexus_api.db.models.agent_spec import AgentTest, AgentTestSuite
    from nexus_api.services import activations
    from tests.integration.business._business_world import new_business
    from tests.integration.connectors._activation_world import (
        SLUG,
        agent_with_spec,
        connect,
        seed_integration,
    )

    biz = await new_business(client, db_session, console_world, name="Tienda Lumen")
    partner = await db_session.get(Partner, biz.partner_id)
    assert partner is not None
    partner.console_v2_enabled_at = datetime.now(UTC)
    await db_session.commit()
    connector = await seed_integration(db_session)
    await connect(db_session, biz, connector)
    agent_id = await agent_with_spec(db_session, biz, "Ventas")
    async with tenant_scoped_session(db_session, biz.tenant_id):
        suite = AgentTestSuite(id=uuid.uuid4(), tenant_id=biz.tenant_id, agent_id=agent_id)
        db_session.add(suite)
        await db_session.flush()
        db_session.add(
            AgentTest(
                tenant_id=biz.tenant_id,
                suite_id=suite.id,
                kind="case",
                name="Pide un pedido",
                first_message="Quiero dos velas.",
                criteria=[{"key": "order", "text": "Toma el pedido."}],
                critical=False,
            )
        )
    async with tenant_scoped_session(db_session, biz.tenant_id):
        await activations.activate(
            db_session,
            tenant_id=biz.tenant_id,
            agent_id=agent_id,
            slug=SLUG,
            permission="read_write",
            settings={},
            actor="console:ana@example.com",
        )
    async with tenant_scoped_session(db_session, biz.tenant_id):
        stale = (
            await db_session.scalars(
                sa.select(AgentTest.stale)
                .where(AgentTest.suite_id == suite.id)
                .execution_options(populate_existing=True)
            )
        ).all()
    assert stale == [True], "62.3: conectar cambia lo que puede hacer; sus pruebas no cuentan"
