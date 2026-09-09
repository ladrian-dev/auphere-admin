"""Requisito 7.1 — lo que toca a un cliente final pasa por la escalera durable.

Y la auditoría nombra a la **persona**, no al agente que ejecutó. Esa distinción
es el punto entero de §IV: un registro que dice «lo hizo el agente» no responde a
la única pregunta que importa en un incidente, que es quién lo autorizó.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from nexus_api.db.models.companion import CompanionAction, CompanionThread
from nexus_api.services.action_scope import (
    ActionScope,
    classify_tool,
    decide_pending,
    requires_durable_approval,
)

pytestmark = pytest.mark.asyncio


def test_an_end_client_action_requires_the_durable_ladder():
    assert classify_tool("console.clients.archive") is ActionScope.END_CLIENT
    assert requires_durable_approval("console.clients.archive") is True


def test_the_audit_names_the_person_not_the_agent():
    """`decided_by` es de quien decidió. El agente que ejecutó no va ahí."""
    action = CompanionAction(
        id=uuid.uuid4(),
        thread_id=uuid.uuid4(),
        kind="console.clients.archive",
        payload={},
        status="approved",
        proposed_at=datetime.now(UTC),
        decided_at=datetime.now(UTC),
        decided_by="user_luis",
    )
    assert decide_pending(action) == "decidida"
    assert action.decided_by == "user_luis"
    assert "agent" not in (action.decided_by or "")


def test_the_durable_action_carries_a_state_hash_column():
    """Sin `state_hash` una aprobación autorizaría un estado que ya cambió."""
    columns = {c.name for c in CompanionAction.__table__.columns}
    assert {"state_hash", "decided_by", "decided_at", "proposed_at"} <= columns


def test_a_thread_exists_to_hang_the_action_from():
    """La acción cuelga de un hilo: una aprobación sin conversación no se audita."""
    assert "thread_id" in {c.name for c in CompanionAction.__table__.columns}
    assert CompanionThread.__tablename__ == "threads"
