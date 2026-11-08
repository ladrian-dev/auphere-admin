"""Spec 056, T041 — el partner decide de una vez el lote de «Todo el negocio»
(requisitos 9.1 y 9.2; ``contracts/api.md``, rutas del requisito 9).

- En las mejoras de cada agente, la corrección dice que viene de un lote y a
  cuántos agentes llegó (``batch {id, agents_count}``).
- ``POST /console/clients/{ref}/corrections/{batch_id}/accept`` aplica todas las
  del lote en una transacción, cada una en el borrador de su agente con su
  prueba, y lo audita una vez (``correction.batch_accepted``).
- ``…/discard`` las rechaza todas con su motivo (``correction.batch_discarded``).
- Un lote decidido no se vuelve a decidir; uno de otro cliente no existe; quien
  no puede escribir agentes no decide.
"""

# ruff: noqa: F811 — ``inbox`` y ``fake_paraphraser`` son fixtures de test_corrections

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import AuditLog, InboxCorrection
from nexus_api.db.models.agent_spec import Proposal

from .test_corrections import (  # noqa: F401 — fixtures y ayudas del mismo mundo
    QUESTION,
    FakeParaphraser,
    Inbox,
    _draft,
    _rows,
    _send,
    _team,
    fake_paraphraser,
    inbox,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _batch(client: Any, inbox: Inbox, rule: str) -> str:
    draft = await _draft(client, inbox, rule, scope="business")
    await _send(client, inbox, draft)
    return str(draft["id"])


def _url(inbox: Inbox, batch_id: str, action: str) -> str:
    return f"/console/clients/{inbox.biz.ref}/corrections/{batch_id}/{action}"


async def test_the_partner_sees_the_batch_and_accepts_it_at_once(
    client: Any, db_session: AsyncSession, inbox: Inbox
) -> None:
    team = await _team(db_session, inbox)
    batch_id = await _batch(client, inbox, "No des citas los festivos.")

    for name in ("Recepción", "Ventas", "Noches"):
        listed = await client.get(
            f"/console/clients/{inbox.biz.ref}/agents/{team[name]}/improvements",
            headers=inbox.biz.headers(),
        )
        assert listed.status_code == 200, listed.text
        (item,) = [i for i in listed.json()["items"] if i["kind"] == "correction"]
        assert item["batch"] == {"id": batch_id, "agents_count": 3}, name
        assert QUESTION not in listed.text

    accepted = await client.post(_url(inbox, batch_id, "accept"), headers=inbox.biz.headers())
    assert accepted.status_code == 200, accepted.text
    assert accepted.json() == {"batch_id": batch_id, "applied": 3, "skipped": []}

    tid = inbox.biz.tenant_id
    rows = await _rows(db_session, tid, sa.select(InboxCorrection))
    assert {r.status for r in rows} == {"accepted"}
    proposals = await _rows(
        db_session, tid, sa.select(Proposal).where(Proposal.author == "correction")
    )
    assert {p.status for p in proposals} == {"applied"}
    (audit,) = await _rows(
        db_session, tid, sa.select(AuditLog).where(AuditLog.action == "correction.batch_accepted")
    )
    assert audit.target == f"correction_batch:{batch_id}"
    assert audit.actor.startswith("console:")
    assert audit.after_json is not None
    assert sorted(audit.after_json["agents"]) == sorted(
        str(team[n]) for n in ("Recepción", "Ventas", "Noches")
    )
    assert audit.after_json["skipped"] == []

    again = await client.post(_url(inbox, batch_id, "accept"), headers=inbox.biz.headers())
    assert again.status_code == 409, "un lote decidido está cerrado"
    assert again.json()["detail"]["code"] == "improvement_closed"


async def test_the_partner_discards_the_batch_with_its_reason(
    client: Any, db_session: AsyncSession, inbox: Inbox
) -> None:
    await _team(db_session, inbox)
    batch_id = await _batch(client, inbox, "Siempre saluda por el nombre.")

    missing = await client.post(_url(inbox, batch_id, "discard"), headers=inbox.biz.headers())
    assert missing.status_code == 422, "el motivo es obligatorio"
    discarded = await client.post(
        _url(inbox, batch_id, "discard"), json={"reason": "No aplica"}, headers=inbox.biz.headers()
    )
    assert discarded.status_code == 200, discarded.text
    assert discarded.json() == {"batch_id": batch_id, "applied": 0, "skipped": []}

    tid = inbox.biz.tenant_id
    rows = await _rows(db_session, tid, sa.select(InboxCorrection))
    assert {r.status for r in rows} == {"rejected"}
    (audit,) = await _rows(
        db_session, tid, sa.select(AuditLog).where(AuditLog.action == "correction.batch_discarded")
    )
    assert audit.after_json is not None
    assert audit.after_json["discard_reason"] == "No aplica"
    assert len(audit.after_json["agents"]) == 3


async def test_a_batch_is_only_its_clients_and_only_for_who_writes_agents(
    client: Any, db_session: AsyncSession, inbox: Inbox, console_world: dict[str, Any]
) -> None:
    from tests.conftest import add_console_member

    await _team(db_session, inbox)
    batch_id = await _batch(client, inbox, "No des citas los festivos.")

    unknown = await client.post(
        _url(inbox, str(uuid.uuid4()), "accept"), headers=inbox.biz.headers()
    )
    assert unknown.status_code == 404
    # Una corrección suelta no es un lote.
    single = await _draft(client, inbox, "Nunca prometas aparcamiento.", scope="agent")
    await _send(client, inbox, single)
    loose = await client.post(_url(inbox, single["id"], "accept"), headers=inbox.biz.headers())
    assert loose.status_code == 404

    # Otro partner con su propio cliente: el lote de este no existe para él.
    b = console_world["b"]
    foreign = await client.post(
        f"/console/clients/{b['ref']}/corrections/{batch_id}/accept", headers=b["headers"]()
    )
    assert foreign.status_code == 404

    analyst = await add_console_member(db_session, partner_id=inbox.biz.partner_id, role="analyst")
    denied = await client.post(_url(inbox, batch_id, "accept"), headers=analyst["headers"]())
    assert denied.status_code == 403
    rows = await _rows(db_session, inbox.biz.tenant_id, sa.select(InboxCorrection))
    assert {r.status for r in rows if r.batch_id is not None} == {"proposed"}
