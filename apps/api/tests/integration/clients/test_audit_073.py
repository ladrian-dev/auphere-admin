"""Spec 073 (§1) — la Auditoría que se lee.

- Cada persona con su nombre y lo que es: del partner o de un cliente (1.3, 1.4).
- El origen coincide con el evento: lo del teléfono del cliente es «app» (1.5).
- «Solo cambios» deja fuera los accesos (1.6, D3), en la lista y en el CSV.
- Garantía 1: el nombre de una persona de otro partner nunca sale, aunque su
  correo coincida con el de una fila de este (encabezado de la spec).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from nexus_api.api.console import audit as audit_module
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import AuditLog
from nexus_api.db.models.client_access import ClientMembership
from tests.integration.wallet._wallet_world import money_world

pytestmark = [pytest.mark.integration]

OWNER = "owner-mw@example.com"  # el dueño de ``money_world``, «Owner»


async def _rows(client: Any, headers: dict[str, str], query: str = "") -> list[dict[str, Any]]:
    resp = await client.get(f"/console/audit?lang=es&group=false{query}", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


async def _client_member(db: Any, world: Any, email: str, name: str) -> None:
    db.add(
        ClientMembership(
            partner_id=world.partner_id,
            tenant_id=world.us.tenant_id,
            user_id=f"user_{uuid.uuid4().hex[:12]}",
            email=email,
            display_name=name,
        )
    )
    await db.commit()


async def _log(db: Any, world: Any, *rows: tuple[str, str, dict[str, Any]]) -> None:
    async with tenant_scoped_session(db, world.us.tenant_id):
        for actor, action, after in rows:
            db.add(
                AuditLog(
                    tenant_id=world.us.tenant_id,
                    actor=actor,
                    action=action,
                    target=f"tenant:{world.us.tenant_id}",
                    after_json=after,
                )
            )
    await db.commit()


async def test_each_person_has_a_name_and_says_whose_it_is(client: Any, db_session: Any) -> None:
    audit_module.reset_vocabulary_cache_for_tests()
    world = await money_world(db_session, roles=())
    await _client_member(db_session, world, "lucia@cliente.example", "Lucía")
    await _log(
        db_session,
        world,
        (f"console:{OWNER}", "agent.paused", {"origin": "console"}),
        ("client:lucia@cliente.example", "agent.paused", {"origin": "lite_web"}),
        ("client:nadie@cliente.example", "agent.paused", {"origin": "lite_web"}),
    )
    rows = await _rows(client, world.headers())
    by_actor = {r["actor"]: r for r in rows if r["action"] == "agent.paused"}

    mine = by_actor[OWNER]
    assert mine["actor_name"] == "Owner" and mine["actor_scope"] == "partner"
    assert mine["summary"].startswith("Owner "), "la frase nombra a la persona, no su correo"

    lucia = by_actor["lucia@cliente.example"]
    assert lucia["actor_name"] == "Lucía" and lucia["actor_scope"] == "client"
    assert lucia["summary"].startswith("Lucía ")

    # Sin nombre conocido, el correo; el filtro por persona sigue usando el correo.
    nobody = by_actor["nadie@cliente.example"]
    assert nobody["actor_name"] == "nadie@cliente.example" and nobody["actor_scope"] == "client"


async def test_what_was_done_from_the_phone_says_app(client: Any, db_session: Any) -> None:
    audit_module.reset_vocabulary_cache_for_tests()
    world = await money_world(db_session, roles=())
    # Así escribe hoy ``client_phones._audit``: sin ``origin``, con la plataforma.
    await _log(
        db_session,
        world,
        (
            "client:lucia@cliente.example",
            "client_phone.signed_in",
            {"machine": "iPhone 17", "platform": "ios"},
        ),
    )
    rows = await _rows(client, world.headers(), "&view=all")
    (signed_in,) = [r for r in rows if r["action"] == "client_phone.signed_in"]
    assert signed_in["origin"] == "app", "entrar desde el iPhone no es «Desde la web»"


async def test_only_changes_leaves_the_accesses_out(client: Any, db_session: Any) -> None:
    audit_module.reset_vocabulary_cache_for_tests()
    world = await money_world(db_session, roles=())
    await _log(
        db_session,
        world,
        (f"console:{OWNER}", "console.auth.login", {}),
        (f"console:{OWNER}", "console.auth.logout", {}),
        ("client:lucia@cliente.example", "client_phone.signed_in", {"platform": "ios"}),
        ("client:lucia@cliente.example", "client_phone.signed_out", {"platform": "ios"}),
        ("client:lucia@cliente.example", "client_phone.closed", {"platform": "ios"}),
        (f"console:{OWNER}", "agent.paused", {"origin": "console"}),
    )
    accesses = {
        "console.auth.login",
        "console.auth.logout",
        "client_phone.signed_in",
        "client_phone.signed_out",
        "client_phone.closed",
    }
    changes = {r["action"] for r in await _rows(client, world.headers(), "&view=changes")}
    assert "agent.paused" in changes and not changes & accesses
    everything = {r["action"] for r in await _rows(client, world.headers(), "&view=all")}
    assert accesses <= everything
    # Sin ``view`` la API lo da todo, como hoy: la consola pide «Solo cambios».
    assert accesses <= {r["action"] for r in await _rows(client, world.headers())}

    csv = await client.get(
        "/console/audit/export.csv?lang=es&view=changes", headers=world.headers()
    )
    assert csv.status_code == 200
    assert "agent.paused" in csv.text and "console.auth.login" not in csv.text
