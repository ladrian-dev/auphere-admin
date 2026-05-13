"""Pin the named-dict shape returned by
:func:`nexus_worker.streams.owner_outbox._body_params_for_template`.

The two YCloud templates ``auphere_owner_consult`` and
``auphere_owner_action_request`` were registered with named variables
(``tenant_name``, ``question``, ``urgency``, ``correlation_id``). The
dispatcher MUST produce a dict whose keys match those names — otherwise
YCloud rejects the send with a binding error.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from nexus_worker.streams.owner_outbox import _body_params_for_template

from nexus_api.db.models import OwnerConsultation


def _make_row(
    *,
    template_params: dict[str, str] | None = None,
) -> OwnerConsultation:
    """Build an in-memory :class:`OwnerConsultation` (not persisted)."""
    return OwnerConsultation(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        correlation_id="abcd1234",
        asked_at=datetime.now(UTC),
        question_text="¿Puedo agendar a Juan el sábado?",
        urgency="normal",
        expected_reply_kind="free_text",
        template_name="auphere_owner_consult",
        template_params_json=template_params or {},
        status="pending",
        created_by="agent",
    )


def test_returns_dict_with_named_keys_matching_ycloud_template() -> None:
    row = _make_row(
        template_params={
            "tenant_name": "Cultor Barber",
            "question": "Cancelar la cita de María",
            "urgency": "high",
        }
    )
    params = _body_params_for_template(row, tenant_name="Cultor Barber")
    assert params == {
        "tenant_name": "Cultor Barber",
        "question": "Cancelar la cita de María",
        "urgency": "high",
        "correlation_id": "abcd1234",
    }


def test_falls_back_to_row_fields_when_template_params_missing() -> None:
    """If ``template_params_json`` is empty (defensive — should not
    happen post Phase-1 schema) the dispatcher falls back to the
    canonical row columns."""
    row = _make_row(template_params={})
    params = _body_params_for_template(row, tenant_name="Backup Tenant")
    assert params == {
        "tenant_name": "Backup Tenant",
        "question": "¿Puedo agendar a Juan el sábado?",
        "urgency": "normal",
        "correlation_id": "abcd1234",
    }


def test_correlation_id_always_from_row_not_template_params() -> None:
    """``correlation_id`` is the unique handle the owner uses to reply;
    it MUST come from the immutable column, not the JSONB blob. A drifted
    JSONB value would route the owner's response to the wrong row."""
    row = _make_row(
        template_params={
            "tenant_name": "X",
            "question": "Q",
            "urgency": "low",
            "correlation_id": "WRONG-VALUE",
        }
    )
    params = _body_params_for_template(row, tenant_name="X")
    assert params["correlation_id"] == "abcd1234"
