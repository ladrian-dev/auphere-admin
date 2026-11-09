"""Spec 057, T024 — el trabajo ``agenda_text``: la propuesta de texto y su medida
(requisitos 3.1, 3.2, 3.5, 3.6 y 3.7).

- **Con modelo**: las operaciones solo tocan los bloques de citas; lo que no pasa las
  comprobaciones (otro puntero, un texto que sigue prohibiendo la agenda) no se propone
  y se usa el respaldo.
- **Medida**: dentro de ``usage_turn(source="builder")``: la partida de construcción del
  partner, nunca la bolsa del cliente.
- **Vive 7 días** y la siguiente de la agenda deja ``stale`` la anterior.
- **La ficha** que dice que el equipo confirma las citas se señala (``ficha_links``) y no
  se toca.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models.agent_spec import Proposal

from ..business._business_world import Biz, new_business
from ._builder_world import FakeBuilder, job_row, run_jobs, start_draft

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

#: Lo que el constructor escribió para Spa Jemma con Reservas apagado.
ALTERNATIVE = {
    "id": "request_appointment",
    "title": "Recoger una solicitud de cita",
    "when": "La persona pide una cita o pregunta por disponibilidad.",
    "steps": (
        "1. Pregunta el día y la franja horaria que prefiere. 2. No ofrezcas huecos ni "
        "confirmes la reserva. 3. Indica que el equipo revisará la disponibilidad. "
        "4. Pasa la conversación al equipo."
    ),
}


@pytest.fixture
async def biz(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> Biz:
    return await new_business(client, db_session, console_world, name="Spa Jemma")


async def _agent_with_the_old_text(client: Any, db_session: AsyncSession, biz: Biz) -> uuid.UUID:
    """Un agente en blanco al que se le escribe a mano lo que dejó el constructor sin agenda."""
    resp = await start_draft(
        client,
        f"/console/clients/{biz.ref}",
        biz.headers(),
        name="Recepción",
        start="blank",
        description=None,
        agenda=False,
    )
    assert resp.status_code == 202, resp.text
    agent_id = uuid.UUID(resp.json()["agent_id"])
    url = f"/console/clients/{biz.ref}/agents/{agent_id}/draft"
    draft = (await client.get(url, headers=biz.headers())).json()
    spec = draft["spec"]
    spec["procedures"] = [ALTERNATIVE]
    spec["rules"] = ["Una solicitud de cita no es una reserva confirmada."]
    saved = await client.patch(
        url,
        json={"spec": spec},
        headers={**biz.headers(), "If-Match": f'"{draft["revision"]}"'},
    )
    assert saved.status_code == 200, saved.text
    return agent_id


async def _switch_on(client: Any, biz: Biz, agent_id: uuid.UUID) -> dict[str, Any]:
    resp = await client.put(
        f"/console/clients/{biz.ref}/agents/{agent_id}/agenda",
        json={"enabled": True, "reservas": {"mode": "services"}},
        headers=biz.headers(),
    )
    assert resp.status_code == 200, resp.text
    return dict(resp.json())


async def _proposals(db_session: AsyncSession, biz: Biz) -> list[Proposal]:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        rows = await db_session.scalars(
            sa.select(Proposal)
            .order_by(Proposal.created_at)
            .execution_options(populate_existing=True)
        )
        return list(rows.all())


async def test_the_model_rewrites_the_appointment_text_and_it_is_metered(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent_with_the_old_text(client, db_session, biz)
    body = await _switch_on(client, biz, agent_id)
    builder = FakeBuilder(
        reply={
            "summary": "Ahora reserva ella misma.",
            "ops": [
                {
                    "op": "replace",
                    "path": "/procedures/0",
                    "value": {
                        "id": "reservar",
                        "title": "Reservar una cita",
                        "when": "Cuando alguien pide una cita",
                        "steps": "Busca huecos, ofrece dos y reserva al sí. Confirma con la reserva creada.",
                        "tools": ["reservas.find_slots", "reservas.create"],
                    },
                },
                {"op": "remove", "path": "/rules/0"},
            ],
        }
    )
    await run_jobs(fake_redis, None, agenda_builder=builder)

    job = await job_row(db_session, biz.tenant_id, body["job"]["id"])
    assert job.status == "done", job.error_code
    assert job.result["fallback"] is False
    [proposal] = await _proposals(db_session, biz)
    assert proposal.summary == "Ahora reserva ella misma."
    paths = {op["path"] for op in proposal.diff["ops"]}
    assert paths <= {
        "/procedures",
        "/rules",
        "/escalation",
        "/skills",
        "/instructions",
        "/services",
    }
    assert (proposal.expires_at - proposal.created_at).days >= 6

    # Medido como construcción (la partida del partner), con el turno del trabajo.
    entries = await fake_redis.xrange("nexus:usage")
    (fields,) = [
        e[1]
        for e in entries
        if e[1].get("source") == "builder" and e[1].get("turn_id") == f"job:{job.id}"
    ]
    assert {e["task"] for e in json.loads(fields["events"])} == {"build"}


async def test_an_op_outside_the_appointment_blocks_falls_back(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent_with_the_old_text(client, db_session, biz)
    body = await _switch_on(client, biz, agent_id)
    builder = FakeBuilder(
        reply={"summary": "x", "ops": [{"op": "replace", "path": "/tools", "value": []}]}
    )
    await run_jobs(fake_redis, None, agenda_builder=builder)
    job = await job_row(db_session, biz.tenant_id, body["job"]["id"])
    assert job.status == "done" and job.result["fallback"] is True
    [proposal] = await _proposals(db_session, biz)
    assert not any(op["path"].startswith("/tools") for op in proposal.diff["ops"])


async def test_a_reply_that_keeps_forbidding_the_agenda_falls_back(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent_with_the_old_text(client, db_session, biz)
    body = await _switch_on(client, biz, agent_id)
    builder = FakeBuilder(
        reply={"summary": "Nada que cambiar.", "ops": [{"op": "remove", "path": "/rules/0"}]}
    )
    await run_jobs(fake_redis, None, agenda_builder=builder)
    job = await job_row(db_session, biz.tenant_id, body["job"]["id"])
    assert job.result["fallback"] is True, "el procedimiento viejo seguía prohibiendo la agenda"
    [proposal] = await _proposals(db_session, biz)
    after = {op["path"]: op.get("value") for op in proposal.diff["ops"]}
    titles = {p["title"] for p in after["/procedures"]}
    assert "Recoger una solicitud de cita" not in titles
    assert "Reservar una cita" in titles


async def test_a_failing_provider_falls_back(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent_with_the_old_text(client, db_session, biz)
    body = await _switch_on(client, biz, agent_id)
    await run_jobs(fake_redis, None, agenda_builder=FakeBuilder(fail=True))
    job = await job_row(db_session, biz.tenant_id, body["job"]["id"])
    assert job.status == "done" and job.result["fallback"] is True
    assert job.result["proposal_id"] is not None


async def test_the_next_one_makes_the_previous_stale(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent_with_the_old_text(client, db_session, biz)
    await _switch_on(client, biz, agent_id)
    await run_jobs(fake_redis, None)
    off = await client.put(
        f"/console/clients/{biz.ref}/agents/{agent_id}/agenda",
        json={"enabled": False},
        headers=biz.headers(),
    )
    assert off.status_code == 200, off.text
    await run_jobs(fake_redis, None)
    first, second = await _proposals(db_session, biz)
    assert first.status == "stale" and second.status == "open"
    # Al apagarla, la propuesta deja la alternativa de pasar la cita a una persona.
    after = {op["path"]: op.get("value") for op in second.diff["ops"]}
    assert any(p.get("id") == "pedir_cita" for p in after.get("/procedures") or [])


async def test_the_business_policy_that_says_the_team_confirms_is_pointed_at(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    from ..business._business_world import read, write

    revision = (await read(client, biz, "/policies"))["revision"]
    await write(
        client,
        biz,
        "PUT",
        "/policies",
        {
            "cancellation": (
                "Avísanos con antelación por WhatsApp. El equipo confirmará si el cambio "
                "está disponible."
            )
        },
        revision=revision,
    )
    agent_id = await _agent_with_the_old_text(client, db_session, biz)
    await _switch_on(client, biz, agent_id)
    await run_jobs(fake_redis, None)
    [proposal] = await _proposals(db_session, biz)
    links = proposal.diff.get("ficha_links") or []
    assert {link["section"] for link in links} == {"policies"}
