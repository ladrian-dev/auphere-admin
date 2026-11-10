"""Spec 047, T076 — las propuestas del constructor (requisitos 15.2 y 15.3; §IV).

- Son objetos durables con su autor, quién decide, su estado y su ``state_hash``;
  proponer dos veces lo mismo sobre el mismo estado es la misma propuesta.
- Si el estado cambió, aplicar se rechaza (``proposal_stale``).
- Caducan a los 15 minutos (``proposal_expired``).
- Solo aplica una persona con permiso, y solo sobre el agente de la ruta: la
  propuesta de un hermano es un 404 (garantía 9).
- Aplicar vuelve a pasar el validador sin modelo (15.4).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import Proposal
from nexus_api.services import proposal_state
from tests.conftest import add_console_member

from ..business._business_world import Biz, new_business
from ._builder_world import RECEPTION, FakeBuilder, run_jobs, start_draft

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def biz(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> Biz:
    return await new_business(client, db_session, console_world, name="Barbería Cultor")


async def _agent(client: Any, biz: Biz, fake_redis: Any, name: str) -> uuid.UUID:
    resp = await start_draft(client, f"/console/clients/{biz.ref}", biz.headers(), name=name)
    assert resp.status_code == 202, resp.text
    await run_jobs(fake_redis, FakeBuilder(reply=RECEPTION))
    body = (
        await client.get(f"/console/jobs/{resp.json()['job_id']}", headers=biz.headers())
    ).json()
    return uuid.UUID(body["result"]["agent_id"])


def _url(biz: Biz, agent_id: uuid.UUID) -> str:
    return f"/console/clients/{biz.ref}/agents/{agent_id}"


async def _state(client: Any, biz: Biz, agent_id: uuid.UUID) -> tuple[dict[str, Any], int]:
    got = await client.get(f"{_url(biz, agent_id)}/draft", headers=biz.headers())
    assert got.status_code == 200, got.text
    return got.json()["spec"], got.json()["revision"]


async def _propose(
    db_session: AsyncSession,
    biz: Biz,
    agent_id: uuid.UUID,
    spec: dict[str, Any],
    ops: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    author: str = "builder",
) -> uuid.UUID:
    from nexus_api.services.agent_spec.schema import AgentSpec

    state = proposal_state.canonical_hash(
        AgentSpec.model_validate(spec).model_dump(mode="json", exclude_none=True, by_alias=True)
    )
    async with tenant_scoped_session(db_session, biz.tenant_id):
        proposal = await proposal_state.propose(
            db_session,
            agent_id=agent_id,
            kind="agent_spec_patch",
            author=author,
            diff={"ops": ops},
            state_hash=state,
            summary="Añadir una regla",
            now=now,
        )
        return proposal.id


async def _row(db_session: AsyncSession, biz: Biz, pid: uuid.UUID) -> Proposal:
    async with tenant_scoped_session(db_session, biz.tenant_id):
        row = await db_session.get(Proposal, pid, populate_existing=True)
    assert row is not None
    return row


RULE = [{"op": "add", "path": "/rules/-", "value": "Ofrece siempre el primer hueco libre."}]


async def test_a_proposal_is_durable_and_the_same_one_twice(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, biz, fake_redis, "Recepción")
    spec, _rev = await _state(client, biz, agent_id)
    first = await _propose(db_session, biz, agent_id, spec, RULE)
    again = await _propose(db_session, biz, agent_id, spec, RULE)
    assert first == again
    row = await _row(db_session, biz, first)
    assert (row.author, row.status, row.decided_by) == ("builder", "open", None)
    assert len(row.state_hash) == 64
    assert row.expires_at - row.created_at <= timedelta(minutes=15, seconds=1)

    listed = await client.get(f"{_url(biz, agent_id)}/proposals", headers=biz.headers())
    assert [p["id"] for p in listed.json()] == [str(first)]

    applied = await client.post(
        f"{_url(biz, agent_id)}/proposals/{first}/apply", headers=biz.headers()
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["status"] == "applied"
    row = await _row(db_session, biz, first)
    assert row.decided_by is not None and row.decided_at is not None
    spec_after, _rev = await _state(client, biz, agent_id)
    assert "Ofrece siempre el primer hueco libre." in spec_after["rules"]
    # Ya aplicada: no se aplica dos veces.
    twice = await client.post(
        f"{_url(biz, agent_id)}/proposals/{first}/apply", headers=biz.headers()
    )
    assert twice.status_code == 409 and twice.json()["detail"]["code"] == "proposal_closed"


async def test_a_changed_state_makes_it_stale(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, biz, fake_redis, "Recepción")
    spec, revision = await _state(client, biz, agent_id)
    pid = await _propose(db_session, biz, agent_id, spec, RULE)
    # Alguien edita el borrador después.
    edited = dict(spec)
    edited["rules"] = [*spec["rules"], "Pide el nombre."]
    resp = await client.patch(
        f"{_url(biz, agent_id)}/draft",
        json={"spec": edited},
        headers={**biz.headers(), "If-Match": f'"{revision}"'},
    )
    assert resp.status_code == 200, resp.text
    stale = await client.post(f"{_url(biz, agent_id)}/proposals/{pid}/apply", headers=biz.headers())
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "proposal_stale"
    spec_after, _rev = await _state(client, biz, agent_id)
    assert "Ofrece siempre el primer hueco libre." not in spec_after["rules"]


async def test_it_expires_after_15_minutes(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, biz, fake_redis, "Recepción")
    spec, _rev = await _state(client, biz, agent_id)
    pid = await _propose(
        db_session, biz, agent_id, spec, RULE, now=datetime.now(UTC) - timedelta(minutes=16)
    )
    late = await client.post(f"{_url(biz, agent_id)}/proposals/{pid}/apply", headers=biz.headers())
    assert late.status_code == 410 and late.json()["detail"]["code"] == "proposal_expired"
    listed = await client.get(f"{_url(biz, agent_id)}/proposals", headers=biz.headers())
    assert listed.json() == []


async def test_only_a_person_with_permission_applies_it(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, biz, fake_redis, "Recepción")
    spec, _rev = await _state(client, biz, agent_id)
    pid = await _propose(db_session, biz, agent_id, spec, RULE)
    analyst = await add_console_member(db_session, partner_id=biz.partner_id, role="analyst")
    denied = await client.post(
        f"{_url(biz, agent_id)}/proposals/{pid}/apply", headers=analyst["headers"]()
    )
    assert denied.status_code == 403
    assert (await _row(db_session, biz, pid)).status == "open"
    rejected = await client.post(
        f"{_url(biz, agent_id)}/proposals/{pid}/reject", headers=biz.headers()
    )
    assert rejected.status_code == 200 and rejected.json()["status"] == "rejected"


async def test_a_siblings_proposal_is_not_found_through_this_agent(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    mine = await _agent(client, biz, fake_redis, "Recepción")
    sibling = await _agent(client, biz, fake_redis, "Ventas")
    spec, _rev = await _state(client, biz, sibling)
    pid = await _propose(db_session, biz, sibling, spec, RULE)
    through_me = await client.post(
        f"{_url(biz, mine)}/proposals/{pid}/apply", headers=biz.headers()
    )
    assert through_me.status_code == 404
    assert (await _row(db_session, biz, pid)).status == "open"


async def test_applying_passes_the_validator_again(
    client: Any, db_session: AsyncSession, biz: Biz, fake_redis: Any
) -> None:
    agent_id = await _agent(client, biz, fake_redis, "Recepción")
    spec, _rev = await _state(client, biz, agent_id)
    bad = [{"op": "add", "path": "/tools/-", "value": "calendar.unknown"}]
    pid = await _propose(db_session, biz, agent_id, spec, bad)
    resp = await client.post(f"{_url(biz, agent_id)}/proposals/{pid}/apply", headers=biz.headers())
    assert resp.status_code == 422
    assert resp.json()["detail"]["problems"][0]["code"] == "tool_unknown"
    # El constructor tampoco puede dejar decidido el aviso de IA.
    decided = [
        {
            "op": "replace",
            "path": "/ai_disclosure",
            "value": {"decided": True, "mode": "first_message"},
        }
    ]
    pid2 = await _propose(db_session, biz, agent_id, spec, decided)
    resp = await client.post(f"{_url(biz, agent_id)}/proposals/{pid2}/apply", headers=biz.headers())
    assert resp.status_code == 422
    assert resp.json()["detail"]["problems"][0]["code"] == "ai_disclosure_decided_by_builder"
