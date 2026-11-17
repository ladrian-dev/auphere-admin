"""Spec 047, enmienda del 2026-11-16 (requisito 70) — un borrador para un cliente con
Quédate conectado da de alta a quien escribe.

En staging, «Anfitriones Quédate» salió sin ``quedate.register_me`` en la tarea de alta
y con la regla «No envíes teléfono, nombre o documento de un cliente final como
argumentos…». Aquí pasa por el trabajo del borrador de verdad: el catálogo, la
disponibilidad por partner (spec 060) y la conexión salen de la base
(``load_context``). El modelo es de mentira; lo que haga el de verdad con el prompt
nuevo se comprueba regenerando el agente en staging.
"""

from __future__ import annotations

import copy
import uuid
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import ConnectorPartnerAccess
from nexus_api.services.connectors import key_check

from ..builder._builder_world import RECEPTION, FakeBuilder, run_jobs, start_draft
from ..business._business_world import new_business

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

STAGING_RULE = (
    "No envíes teléfono, nombre o documento de un cliente final como argumentos de "
    "ninguna herramienta."
)
GATE_RULE = "No llames a la herramienta de alta sin el correo confirmado."

REPLY: dict[str, Any] = {
    **copy.deepcopy(RECEPTION),
    "goal": "Que quien quiere alquilar su casa quede dado de alta en Quédate.",
    "instructions": [{"title": "Cómo atiendes", "body": "Ayudas a quien quiere alquilar."}],
    "procedures": [
        {
            "id": "alta",
            "title": "Dar de alta a la anfitriona",
            "when": "Cuando alguien quiere alquilar su casa en Quédate",
            "steps": (
                "Pide su nombre y apellido, su documento, su fecha de nacimiento, su sexo y "
                "su correo. Léele el correo y espera a que lo confirme. Dala de alta y "
                "mándale el enlace para verificar su identidad."
            ),
            "tools": ["quedate.register_me", "quedate.my_host", "quedate.my_verification_link"],
        }
    ],
    "tools": [
        "quedate.register_me",
        "quedate.my_host",
        "quedate.my_verification_link",
        "quedate.create_host",
        "escalate.escalate_to_human",
    ],
    "skills": [],
    "rules": [STAGING_RULE, GATE_RULE, "No ofrezcas descuentos."],
    "tests": [],
}


async def test_a_draft_for_a_client_with_quedate_signs_up_the_person(
    client: Any,
    db_session: AsyncSession,
    console_world: dict[str, Any],
    quedate_catalog: None,
    fake_composio: Any,
    fake_redis: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    biz = await new_business(client, db_session, console_world, name="Prueba Quédate 061")
    await db_session.merge(
        ConnectorPartnerAccess(
            connector_slug="quedate",
            partner_id=biz.partner_id,
            enabled=True,
            reason="t",
            set_by="t",
        )
    )
    await db_session.commit()

    async def accepted(_secrets: dict[str, Any], _meta: dict[str, Any]) -> key_check.Outcome:
        return "ok"

    monkeypatch.setitem(key_check.CHECKERS, "quedate", accepted)
    connected = await client.post(
        f"/console/clients/{biz.ref}/connectors/quedate/api-key",
        headers=biz.headers(),
        json={"secrets": {"api_key": "9|test-key-for-the-builder"}},
    )
    assert connected.status_code == 201, connected.text

    builder = FakeBuilder(reply=REPLY)
    resp = await start_draft(
        client,
        f"/console/clients/{biz.ref}",
        biz.headers(),
        name="Anfitriones Quédate",
        description=(
            "Da de alta en Quédate a quien escribe porque quiere alquilar su casa y le "
            "manda el enlace para verificar su identidad."
        ),
    )
    assert resp.status_code == 202, resp.text
    await run_jobs(fake_redis, builder)
    job = (await client.get(f"/console/jobs/{resp.json()['job_id']}", headers=biz.headers())).json()
    assert job["status"] == "done", job
    agent_id = uuid.UUID(job["result"]["agent_id"])

    # Lo que vio el modelo: el alta marcada y el alta de equipo fuera.
    assert "quedate.register_me" in builder.prompt
    assert "[escribe los datos de la persona del turno]" in builder.prompt
    assert "quedate.create_host" not in builder.prompt

    draft = await client.get(
        f"/console/clients/{biz.ref}/agents/{agent_id}/draft", headers=biz.headers()
    )
    assert draft.status_code == 200, draft.text
    spec = draft.json()["spec"]
    assert "quedate.register_me" in spec["tools"]
    assert "quedate.create_host" not in spec["tools"]
    alta = {p["id"]: p for p in spec["procedures"]}["alta"]
    assert "quedate.register_me" in alta["tools"]
    assert STAGING_RULE not in spec["rules"]
    assert GATE_RULE in spec["rules"], "la regla que protege el alta se queda"
