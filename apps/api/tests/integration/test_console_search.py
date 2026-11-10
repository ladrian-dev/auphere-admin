"""Spec 047, T008 — ``GET /console/search?q=`` (⌘K, requisito 47.2).

- clientes del partner por nombre (y por su referencia), con ``niche`` nulo
  hasta que llegue la ficha (bloque B);
- agentes **activos** por nombre, con su cliente (historia 30, escenario 2:
  «Recep» trae los agentes que se llaman así);
- pantallas y **solo** las acciones que la persona puede hacer;
- **aislamiento**: otro partner no ve nada de este —ni sus clientes ni sus
  agentes—, y los agentes se leen con el cliente puesto (RLS), de modo que un
  cliente que no está en ``partner_tenants`` no aporta nada aunque lleve el id
  del partner;
- sin credencial, 401.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import Agent, PartnerTenant, Tenant, TenantPlan, TenantStatus
from tests.conftest import add_console_member

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _client(
    db_session: AsyncSession,
    partner_id: uuid.UUID,
    *,
    name: str,
    ref: str | None,
    agents: tuple[tuple[str, str], ...] = (),
) -> uuid.UUID:
    tid = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tid,
            name=name,
            slug=f"s-{tid.hex[:10]}",
            plan=TenantPlan.PRO,
            status=TenantStatus.ACTIVE,
            partner_id=partner_id,
        )
    )
    await db_session.flush()
    if ref is not None:
        db_session.add(
            PartnerTenant(
                partner_id=partner_id, external_client_ref=ref, tenant_id=tid, client_name=name
            )
        )
    for agent_name, agent_status in agents:
        db_session.add(Agent(tenant_id=tid, name=agent_name, status=agent_status))
    await db_session.commit()
    return tid


@pytest.fixture
async def world(db_session: AsyncSession, console_world: dict[str, Any]) -> dict[str, Any]:
    a, b = console_world["a"], console_world["b"]
    await _client(
        db_session,
        a["partner_id"],
        name="Café Origen",
        ref="cafe-origen",
        agents=(("Recepción", "active"), ("Ventas mayoristas", "active")),
    )
    await _client(
        db_session,
        a["partner_id"],
        name="Clínica Dental Sur",
        ref="dental-sur",
        agents=(("Recepción Sur", "active"), ("Recepción antigua", "archived")),
    )
    # Carries A's id but is not one of its clients: no mapping.
    await _client(
        db_session,
        a["partner_id"],
        name="Recepción Fantasma",
        ref=None,
        agents=(("Recep X", "active"),),
    )
    await _client(
        db_session,
        b["partner_id"],
        name="Recepciones B",
        ref="b-recepciones",
        agents=(("Recepción de B", "active"),),
    )
    return console_world


async def _search(client: Any, who: dict[str, Any], q: str | None) -> dict[str, Any]:
    params = {} if q is None else {"q": q}
    resp = await client.get("/console/search", params=params, headers=who["headers"]())
    assert resp.status_code == 200, resp.text
    body: dict[str, Any] = resp.json()
    return body


async def test_recep_brings_the_agents_with_their_client(
    client: Any, world: dict[str, Any]
) -> None:
    body = await _search(client, world["a"], "Recep")
    agents = [(h["name"], h["client_ref"], h["client_name"]) for h in body["agents"]]
    assert agents == [
        ("Recepción", "cafe-origen", "Café Origen"),
        ("Recepción Sur", "dental-sur", "Clínica Dental Sur"),
    ]
    assert all(uuid.UUID(h["agent_id"]) for h in body["agents"])


async def test_the_match_ignores_case(client: Any, world: dict[str, Any]) -> None:
    body = await _search(client, world["a"], "recep")
    assert [h["name"] for h in body["agents"]] == ["Recepción", "Recepción Sur"]


async def test_clients_by_name_and_by_ref(client: Any, world: dict[str, Any]) -> None:
    by_name = await _search(client, world["a"], "café")
    assert by_name["clients"] == [{"ref": "cafe-origen", "name": "Café Origen", "niche": None}]

    by_ref = await _search(client, world["a"], "dental-s")
    assert [h["ref"] for h in by_ref["clients"]] == ["dental-sur"]


async def test_another_partner_sees_nothing_of_this_one(client: Any, world: dict[str, Any]) -> None:
    a_body = await _search(client, world["a"], "Recep")
    assert "b-recepciones" not in str(a_body)
    assert "Recepción de B" not in str(a_body)

    b_body = await _search(client, world["b"], "Recep")
    assert [h["ref"] for h in b_body["clients"]] == ["b-recepciones"]
    assert [h["name"] for h in b_body["agents"]] == ["Recepción de B"]
    for word in ("Café", "Dental", "cafe-origen", "Recepción Sur", "Ventas"):
        assert word not in str(b_body)


async def test_a_tenant_that_is_not_a_client_of_the_partner_brings_nothing(
    client: Any, world: dict[str, Any]
) -> None:
    body = await _search(client, world["a"], "Recep")
    assert "Recepción Fantasma" not in str(body)
    assert "Recep X" not in str(body)


async def test_archived_agents_are_not_found(client: Any, world: dict[str, Any]) -> None:
    body = await _search(client, world["a"], "antigua")
    assert body["agents"] == []


async def test_a_blank_query_brings_screens_and_actions_only(
    client: Any, world: dict[str, Any]
) -> None:
    for q in (None, "", "   "):
        body = await _search(client, world["a"], q)
        assert body["clients"] == []
        assert body["agents"] == []
        assert [s["key"] for s in body["screens"]][:2] == ["home", "clients"]
        assert {a["key"] for a in body["actions"]} == {"new_client", "invite_member", "new_api_key"}


async def test_like_wildcards_are_plain_characters(client: Any, world: dict[str, Any]) -> None:
    body = await _search(client, world["a"], "%")
    assert body["clients"] == []
    assert body["agents"] == []


async def test_only_the_actions_the_person_may_do(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    a = world["a"]
    analyst = await add_console_member(db_session, partner_id=a["partner_id"], role="analyst")
    body = await _search(client, analyst, "Recep")
    assert body["actions"] == []
    assert [h["name"] for h in body["agents"]] == ["Recepción", "Recepción Sur"]

    builder = await add_console_member(db_session, partner_id=a["partner_id"], role="builder")
    body = await _search(client, builder, None)
    assert body["actions"] == [{"key": "new_client", "href": "/clients/new"}]


async def test_a_role_without_clients_finds_no_client_and_no_agent(
    client: Any, db_session: AsyncSession, world: dict[str, Any]
) -> None:
    billing = await add_console_member(
        db_session, partner_id=world["a"]["partner_id"], role="billing"
    )
    body = await _search(client, billing, "Recep")
    assert body["clients"] == []
    assert body["agents"] == []
    assert "billing" in [s["key"] for s in body["screens"]]


async def test_without_a_token_it_is_a_401(client: Any) -> None:
    resp = await client.get("/console/search", params={"q": "Recep"})
    assert resp.status_code == 401
