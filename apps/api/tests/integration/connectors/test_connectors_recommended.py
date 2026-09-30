"""Spec 023 (Requisitos 4.1, 4.2): ``GET /console/clients/{ref}/connectors``
marks as recommended exactly what the client's sector template lists, and
recommending never hides a card nor moves it out of its category.
"""

from __future__ import annotations

import pytest

from nexus_api.core.tenant_context import apply_tenant_to_session, tenant_context
from nexus_api.db.models import AgentConfig, AgentConfigStatus

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
    assert cards["agendapro"]["recommended"] is True
    assert cards["calendly"]["recommended"] is True  # dynamic, from the fake provider
    assert cards["woocommerce"]["recommended"] is False
    assert cards["googlecalendar"]["recommended"] is False


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
    assert after["agendapro"]["recommended"] is False
