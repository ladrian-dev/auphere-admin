"""Spec 047, T164 — la Auditoría de la consola nueva (requisito 49.1;
``contracts/events.md`` §4).

Las acciones nuevas se escriben (también las del dinero) y se leen en el idioma del
partner; cada fila dice quién y desde dónde; las filas seguidas iguales se juntan
(«{n} más como esta»); lo sensible va marcado; y los filtros de la spec (persona,
periodo) funcionan en la lista y en el CSV.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from nexus_api.api.console import audit as audit_module
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import AuditLog
from tests.integration.wallet._wallet_world import UNIT, money, money_world

pytestmark = [pytest.mark.integration]


async def _rows(client: Any, headers: dict[str, str], query: str = "") -> list[dict[str, Any]]:
    resp = await client.get(f"/console/audit?lang=es{query}", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


async def test_money_actions_are_audited_in_words_with_their_origin(
    client: Any, db_session: Any
) -> None:
    audit_module.reset_vocabulary_cache_for_tests()
    world = await money_world(db_session, roles=("builder",))
    for _ in range(3):
        resp = await client.post(
            f"/console/clients/{world.us.ref}/bag/assign",
            json={"amount": money(UNIT, "USD")},
            headers=world.headers(),
        )
        assert resp.status_code == 200
    await client.post(
        f"/console/clients/{world.es.ref}/bag/request",
        json={"note": "Se acaba"},
        headers=world.as_role("builder"),
    )
    rows = await _rows(client, world.headers())
    assigned = [r for r in rows if r["action"] == "wallet.assigned"]
    (group,) = assigned
    assert group["more_like_this"] == 2, "tres seguidas iguales: una y «2 más como esta»"
    assert group["origin"] == "console" and group["actor_kind"] == "person"
    assert group["category"] == "usage"
    assert group["summary"].endswith("asignó saldo a Cliente US.")
    (asked,) = [r for r in rows if r["action"] == "balance.requested"]
    assert "pidió saldo para Cliente ES" in asked["summary"]

    ungrouped = await _rows(client, world.headers(), "&group=false")
    assert len([r for r in ungrouped if r["action"] == "wallet.assigned"]) == 3


async def test_person_period_and_sensitive_rows(client: Any, db_session: Any) -> None:
    audit_module.reset_vocabulary_cache_for_tests()
    world = await money_world(db_session, roles=())
    old = datetime.now(UTC) - timedelta(days=40)
    async with tenant_scoped_session(db_session, world.us.tenant_id):
        db_session.add(
            AuditLog(
                tenant_id=world.us.tenant_id,
                actor="console:otra@example.com",
                action="integration.deactivated",
                target=f"tenant:{world.us.tenant_id}",
                after_json={"origin": "console"},
            )
        )
        db_session.add(
            AuditLog(
                tenant_id=world.us.tenant_id,
                actor="client:persona-del-negocio",
                action="agent.paused",
                target=f"agent:{uuid.uuid4()}",
                after_json={"origin": "app"},
                created_at=old,
            )
        )
    await db_session.commit()
    rows = await _rows(client, world.headers())
    (sensitive,) = [r for r in rows if r["action"] == "integration.deactivated"]
    assert sensitive["sensitive"] is True and sensitive["severity"] == "critical"
    recent = await _rows(client, world.headers(), "&days=30")
    assert not [r for r in recent if r["action"] == "agent.paused"], "el periodo filtra"
    everything = await _rows(client, world.headers(), "&days=all")
    (paused,) = [r for r in everything if r["action"] == "agent.paused"]
    assert paused["origin"] == "app", "lo que hizo una persona del cliente desde la app"
    by_person = await _rows(client, world.headers(), "&days=all&person=otra@")
    assert {r["action"] for r in by_person} == {"integration.deactivated"}
    csv = await client.get(
        "/console/audit/export.csv?lang=es&days=all&person=otra@", headers=world.headers()
    )
    assert csv.status_code == 200
    assert "integration.deactivated" in csv.text and "agent.paused" not in csv.text


async def test_the_new_categories_have_names(client: Any, db_session: Any) -> None:
    world = await money_world(db_session, roles=())
    filters = await client.get("/console/audit/filters?lang=es", headers=world.headers())
    assert filters.status_code == 200
    labels = {c["value"]: c["label"] for c in filters.json()["categories"]}
    for category, label in (("business", "Negocio"), ("integrations", "Integraciones")):
        assert labels.get(category) == label
