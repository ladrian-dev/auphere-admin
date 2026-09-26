"""Spec 017 (R5): Capacidades — una sola lectura, por función y por sector.

Herramientas y habilidades dejan de ser dos listas: el partner no distingue
una de otra y `booking.create` no le dice nada. Este endpoint las devuelve
juntas, agrupadas por lo que el negocio quiere conseguir, con el nombre de
negocio en su idioma, filtradas por el sector del cliente.

**Decisión del owner del 2026-09-26, que cambia lo que la tarea T032 pedía**:
encender una capacidad a la que le falta su integración **no es un error**.
T032 pedía un 409 `connector_required`; el owner decidió avisar y dejar
encender, porque encenderla es decir «la quiero» y bloquearla castiga al
partner por un orden que no eligió. La capacidad queda encendida y se
devuelve `usable: false` hasta que el conector esté. Lo que sí sigue siendo
422 es pedir el modo «requiere aprobación», que se retira (R5.7).
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from nexus_api.db.models import AgentConfig, AgentConfigStatus, AuditLog

pytestmark = pytest.mark.asyncio


def _agent(
    tenant_id: uuid.UUID,
    *,
    tools: list[str],
    seed: str | None = "barbershop_v1",
    version: int = 1,
    status=AgentConfigStatus.ACTIVE,
):
    return AgentConfig(
        tenant_id=tenant_id,
        version=version,
        status=status,
        system_prompt_rendered="Atiende a los clientes.",
        tools=tools,
        policies={"console": {"schema_version": 1, "ai_disclosure": {"enabled": True}}},
        seed_template_ref=seed,
    )


async def _seed(
    db_session,
    tenant_id: uuid.UUID,
    *,
    tools: list[str] | None = None,
    seed: str | None = "barbershop_v1",
) -> None:
    db_session.add(_agent(tenant_id, tools=tools or [], seed=seed))
    await db_session.commit()


async def _tool_with_connector(db_session) -> str:
    """Una herramienta que necesita una integración, creada por el test.

    El catálogo sembrado cambia según el entorno —unas herramientas las
    ponen las migraciones y otras `seed_connectors.py`—, así que un test que
    dependa de que exista `woocommerce.list_orders` pasa o falla por razones
    que no tienen que ver con lo que prueba. Este se la crea.
    """
    from nexus_api.db.models import Connector, ToolCatalog, ToolStatus

    slug = f"tienda-{uuid.uuid4().hex[:8]}"
    connector = Connector(
        id=uuid.uuid4(),
        slug=slug,
        display_name="Tienda de prueba",
        vendor="test",
        category="ecommerce",
        capabilities=[],
        auth_kind="api_key",
        mcp_server_ref="test",
        provider_meta={},
        auto_enable_on_connect=False,
        auto_enable_destructive=False,
        status="available",
    )
    db_session.add(connector)
    await db_session.flush()
    name = f"{slug}.list_orders"
    db_session.add(
        ToolCatalog(
            id=uuid.uuid4(),
            name=name,
            description="Lista los pedidos de la tienda.",
            mcp_server="test",
            input_schema={},
            output_schema={},
            capability_tags=["ecommerce", "orders", "read"],
            status=ToolStatus.ACTIVE,
            connector_id=connector.id,
            read_only=True,
            destructive=False,
            default_mode="always",
        )
    )
    await db_session.commit()
    return name


async def test_capabilities_come_grouped_by_what_the_business_wants(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    await _seed(db_session, a["tenant_id"])

    r = await client.get(f"/console/clients/{a['ref']}/capabilities", headers=a["headers"]())
    assert r.status_code == 200, r.text
    body = r.json()

    # Los grupos llegan en el orden en que se leen, y ninguno vacío.
    keys = [g["function"] for g in body["groups"]]
    assert keys == [
        k
        for k in ("appointments", "orders", "messages", "escalation", "knowledge", "other")
        if k in keys
    ]
    assert all(g["items"] for g in body["groups"])

    todas = [i for g in body["groups"] for i in g["items"]]
    # Herramientas y habilidades, juntas y sin distinguirse por la forma.
    assert {"tool", "skill"} <= {i["kind"] for i in todas}
    # Y con nombre de negocio, no técnico.
    reservar = next(i for i in todas if i["key"] == "booking.create_appointment")
    assert reservar["business_name"] == "Reservar una cita"
    assert reservar["technical"]["name"] == "booking.create_appointment"


async def test_the_sector_hides_what_is_not_for_this_client(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    await _seed(db_session, a["tenant_id"], seed="barbershop_v1")

    body = (
        await client.get(f"/console/clients/{a['ref']}/capabilities", headers=a["headers"]())
    ).json()
    assert body["sector"] == "barbershop"
    visibles = {i["key"] for g in body["groups"] for i in g["items"]}
    # Lo de otro vertical no está, y se dice cuántas se ocultan.
    assert "pre-op-screening" not in visibles
    assert body["hidden_by_sector"] > 0

    todo = (
        await client.get(
            f"/console/clients/{a['ref']}/capabilities?all=true", headers=a["headers"]()
        )
    ).json()
    con_todo = {i["key"] for g in todo["groups"] for i in g["items"]}
    assert "pre-op-screening" in con_todo
    assert todo["hidden_by_sector"] == 0
    # Lo que es de otro sector viene marcado, para que la pantalla lo diga.
    otra = next(i for g in todo["groups"] for i in g["items"] if i["key"] == "pre-op-screening")
    assert otra["other_sector"] is True


async def test_without_a_sector_everything_shows_and_it_says_so(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    await _seed(db_session, a["tenant_id"], seed=None)

    body = (
        await client.get(f"/console/clients/{a['ref']}/capabilities", headers=a["headers"]())
    ).json()
    assert body["sector"] is None
    assert body["hidden_by_sector"] == 0
    visibles = {i["key"] for g in body["groups"] for i in g["items"]}
    assert "pre-op-screening" in visibles


async def test_the_search_looks_in_the_language_the_partner_reads(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    await _seed(db_session, a["tenant_id"], seed=None)

    es = (
        await client.get(f"/console/clients/{a['ref']}/capabilities?q=cita", headers=a["headers"]())
    ).json()
    claves = {i["key"] for g in es["groups"] for i in g["items"]}
    assert "booking.create_appointment" in claves
    assert "notification.send_text" not in claves

    # La misma búsqueda en inglés encuentra lo inglés, no lo español.
    en = (
        await client.get(
            f"/console/clients/{a['ref']}/capabilities?q=appointment&lang=en",
            headers=a["headers"](),
        )
    ).json()
    claves_en = {i["key"] for g in en["groups"] for i in g["items"]}
    assert "booking.create_appointment" in claves_en

    # Busca también en la descripción, no solo en el nombre.
    desc = (
        await client.get(
            f"/console/clients/{a['ref']}/capabilities?q=agenda", headers=a["headers"]()
        )
    ).json()
    assert any(i["key"] == "booking.create_appointment" for g in desc["groups"] for i in g["items"])


async def test_recommended_are_the_ones_the_sector_template_turns_on(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    await _seed(db_session, a["tenant_id"], seed="barbershop_v1")

    body = (
        await client.get(f"/console/clients/{a['ref']}/capabilities", headers=a["headers"]())
    ).json()
    recomendadas = {i["key"] for g in body["groups"] for i in g["items"] if i["recommended"]}
    assert recomendadas, "la plantilla del sector enciende herramientas; ninguna llegó marcada"
    # Y lo recomendado sale de la plantilla, no de estar encendido.
    assert all(not i["enabled"] for g in body["groups"] for i in g["items"]), (
        "el agente sembrado no tenía nada encendido"
    )


async def test_a_capability_without_its_integration_is_not_usable(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    name = await _tool_with_connector(db_session)
    await _seed(db_session, a["tenant_id"], tools=[name], seed=None)

    r = await client.get(f"/console/clients/{a['ref']}/capabilities", headers=a["headers"]())
    assert r.status_code == 200, r.text
    todas = [i for g in r.json()["groups"] for i in g["items"]]
    item = next((i for i in todas if i["key"] == name), None)
    assert item is not None, f"la herramienta creada no llegó; vinieron {len(todas)}"
    assert item["enabled"] is True
    assert item["usable"] is False
    assert item["connector"] is not None
    assert item["connector"]["status"] != "connected"


async def test_the_modes_no_longer_offer_needs_approval(client, console_world, db_session) -> None:
    a = console_world["a"]
    await _seed(db_session, a["tenant_id"], seed=None)

    body = (
        await client.get(f"/console/clients/{a['ref']}/capabilities", headers=a["headers"]())
    ).json()
    con_modo = [i for g in body["groups"] for i in g["items"] if i["mode"] is not None]
    assert con_modo, "ninguna herramienta trajo modo"
    for item in con_modo:
        assert "needs_approval" not in item["mode"]["options"], (
            f"{item['key']} aún ofrece «requiere aprobación»"
        )
        assert set(item["mode"]["options"]) == {"always", "blocked"}
    # Las habilidades no tienen modo: no se inventa una columna vacía.
    habilidades = [i for g in body["groups"] for i in g["items"] if i["kind"] == "skill"]
    assert habilidades and all(i["mode"] is None for i in habilidades)


async def test_one_change_saves_into_the_draft_and_leaves_its_trace(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    await _seed(db_session, a["tenant_id"], tools=[], seed=None)

    r = await client.put(
        f"/console/clients/{a['ref']}/capabilities",
        headers=a["headers"](),
        json={"key": "booking.create_appointment", "kind": "tool", "enabled": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["draft_created"] is True
    assert body["capability"]["enabled"] is True

    draft = await db_session.scalar(
        sa.select(AgentConfig).where(
            AgentConfig.tenant_id == a["tenant_id"], AgentConfig.status == AgentConfigStatus.STAGED
        )
    )
    assert draft is not None and draft.tools == ["booking.create_appointment"]

    rows = (
        (
            await db_session.execute(
                sa.select(AuditLog).where(AuditLog.action == "console.capability.update")
            )
        )
        .scalars()
        .all()
    )
    assert rows, "cambiar una capacidad tiene que dejar su fila de auditoría"
    assert rows[0].after_json["key"] == "booking.create_appointment"
    assert rows[0].after_json["enabled"] is True


async def test_turning_one_on_does_not_wipe_the_others(client, console_world, db_session) -> None:
    """Un cambio por llamada (R5.4): el resto de la lista blanca no se toca.
    Mandar la lista entera desde la pantalla era lo que hacía que dos
    personas editando a la vez se pisaran."""
    a = console_world["a"]
    await _seed(db_session, a["tenant_id"], tools=["booking.check_availability"], seed=None)

    r = await client.put(
        f"/console/clients/{a['ref']}/capabilities",
        headers=a["headers"](),
        json={"key": "booking.create_appointment", "kind": "tool", "enabled": True},
    )
    assert r.status_code == 200, r.text
    draft = await db_session.scalar(
        sa.select(AgentConfig).where(
            AgentConfig.tenant_id == a["tenant_id"], AgentConfig.status == AgentConfigStatus.STAGED
        )
    )
    assert draft is not None
    assert set(draft.tools) == {"booking.check_availability", "booking.create_appointment"}


async def test_turning_on_something_whose_integration_is_missing_is_allowed(
    client, console_world, db_session
) -> None:
    """Decisión del owner (2026-09-26): avisar, no bloquear. Encenderla es
    decir «la quiero»; empieza a funcionar cuando se conecte el conector."""
    a = console_world["a"]
    name = await _tool_with_connector(db_session)
    await _seed(db_session, a["tenant_id"], tools=[], seed=None)

    r = await client.put(
        f"/console/clients/{a['ref']}/capabilities",
        headers=a["headers"](),
        json={"key": name, "kind": "tool", "enabled": True},
    )
    assert r.status_code == 200, r.text
    assert r.json()["capability"]["enabled"] is True
    assert r.json()["capability"]["usable"] is False


async def test_needs_approval_is_refused(client, console_world, db_session) -> None:
    a = console_world["a"]
    await _seed(db_session, a["tenant_id"], seed=None)

    r = await client.put(
        f"/console/clients/{a['ref']}/capabilities",
        headers=a["headers"](),
        json={"key": "booking.create_appointment", "kind": "tool", "mode": "needs_approval"},
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "mode_not_supported"

    # Y también en el endpoint viejo, que sigue existiendo (R5.7).
    old = await client.put(
        f"/console/clients/{a['ref']}/tools/booking.create_appointment/mode",
        headers=a["headers"](),
        json={"mode": "needs_approval"},
    )
    assert old.status_code == 422
    assert old.json()["detail"] == "mode_not_supported"


async def test_a_skill_switches_too(client, console_world, db_session) -> None:
    a = console_world["a"]
    await _seed(db_session, a["tenant_id"], seed=None)

    r = await client.put(
        f"/console/clients/{a['ref']}/capabilities",
        headers=a["headers"](),
        json={"key": "escalation-policy", "kind": "skill", "enabled": True},
    )
    assert r.status_code == 200, r.text
    assert r.json()["capability"]["enabled"] is True


async def test_reading_needs_only_agents_read_and_writing_does_not(
    client, console_world, db_session
) -> None:
    from nexus_api.db.models import PartnerMembership

    a = console_world["a"]
    await _seed(db_session, a["tenant_id"], seed=None)
    await db_session.execute(
        sa.update(PartnerMembership)
        .where(PartnerMembership.id == a["membership_id"])
        .values(role="analyst")
    )
    await db_session.commit()

    assert (
        await client.get(f"/console/clients/{a['ref']}/capabilities", headers=a["headers"]())
    ).status_code == 200
    denied = await client.put(
        f"/console/clients/{a['ref']}/capabilities",
        headers=a["headers"](),
        json={"key": "booking.create_appointment", "kind": "tool", "enabled": True},
    )
    assert denied.status_code == 403


async def test_another_partner_sees_nothing(client, console_world, db_session) -> None:
    a, b = console_world["a"], console_world["b"]
    await _seed(db_session, a["tenant_id"], seed=None)
    r = await client.get(f"/console/clients/{a['ref']}/capabilities", headers=b["headers"]())
    assert r.status_code == 404
