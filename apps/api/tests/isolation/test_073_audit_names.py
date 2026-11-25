"""Spec 073, garantía 1 (RLS / partner) — los nombres de la Auditoría.

La Auditoría nombra a cada persona («Lucía · cliente») leyendo a las personas
del partner y de sus clientes. Un partner nunca ve el nombre de una persona de
otro partner, ni de un cliente que no es suyo, aunque un correo coincida.
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

pytestmark = [pytest.mark.integration, pytest.mark.isolation]

SHARED = "compartido@ejemplo.example"


async def test_a_partner_never_sees_the_name_of_another_partners_person(
    client: Any, db_session: Any
) -> None:
    audit_module.reset_vocabulary_cache_for_tests()
    a = await money_world(db_session, roles=())
    b = await money_world(db_session, roles=())
    # La persona con nombre es de un cliente de B; A tiene una fila con el mismo correo.
    db_session.add(
        ClientMembership(
            partner_id=b.partner_id,
            tenant_id=b.us.tenant_id,
            user_id=f"user_{uuid.uuid4().hex[:12]}",
            email=SHARED,
            display_name="Secreto de B",
        )
    )
    await db_session.commit()
    for world in (a, b):
        async with tenant_scoped_session(db_session, world.us.tenant_id):
            db_session.add(
                AuditLog(
                    tenant_id=world.us.tenant_id,
                    actor=f"client:{SHARED}",
                    action="agent.paused",
                    target=f"tenant:{world.us.tenant_id}",
                    after_json={"origin": "lite_web"},
                )
            )
        await db_session.commit()

    seen_by_a = await client.get("/console/audit?lang=es&group=false", headers=a.headers())
    assert seen_by_a.status_code == 200
    assert "Secreto de B" not in seen_by_a.text
    (row,) = [r for r in seen_by_a.json()["items"] if r["action"] == "agent.paused"]
    assert row["actor_name"] == SHARED

    csv_a = await client.get("/console/audit/export.csv?lang=es", headers=a.headers())
    assert "Secreto de B" not in csv_a.text

    # Y B sí ve a su persona por su nombre.
    seen_by_b = await client.get("/console/audit?lang=es&group=false", headers=b.headers())
    (own,) = [r for r in seen_by_b.json()["items"] if r["action"] == "agent.paused"]
    assert own["actor_name"] == "Secreto de B"
