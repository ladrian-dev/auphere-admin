"""Requisito 7.3 — una aprobación que caduca sin respuesta **deniega**.

Deny-on-silence, nunca allow-on-silence. La diferencia entre las dos es todo:
con la segunda, dejar de mirar el móvil aprueba.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from nexus_api.db.models.companion import CompanionAction
from nexus_api.services.action_scope import APPROVAL_TTL_SECONDS, decide_pending


def _action(*, minutes_ago: float, status: str = "proposed") -> CompanionAction:
    return CompanionAction(
        id=uuid.uuid4(),
        thread_id=uuid.uuid4(),
        kind="console.clients.archive",
        payload={},
        status=status,
        proposed_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
    )


def test_a_fresh_proposal_is_still_pending():
    assert decide_pending(_action(minutes_ago=1)) == "pendiente"


def test_silence_past_the_ttl_denies():
    assert decide_pending(_action(minutes_ago=APPROVAL_TTL_SECONDS / 60 + 1)) == "denegada"


def test_the_ttl_is_the_fifteen_minutes_the_constitution_names():
    assert APPROVAL_TTL_SECONDS == 15 * 60


def test_an_already_decided_action_is_not_re_decided():
    """Caducar no puede revertir un sí que ya se dio: sería reescribir historia."""
    assert decide_pending(_action(minutes_ago=999, status="approved")) == "decidida"
