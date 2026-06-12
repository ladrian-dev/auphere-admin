"""Pin the Cloud API components shape returned by
:func:`nexus_worker.streams.owner_outbox._template_components`.

The two backchannel templates ``auphere_owner_consult`` and
``auphere_owner_action_request`` are registered on the Auphere WABA with
**named** variables (``tenant_name``, ``question``, ``urgency``,
``correlation_id``). The dispatcher MUST emit ``parameter_name`` entries
matching those names — otherwise Meta rejects the send with a binding
error (132xxx family).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from nexus_worker.streams.owner_outbox import _template_components

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


def _named(components: list[dict[str, Any]]) -> dict[str, str]:
    """Flatten the components list into ``{parameter_name: text}``."""
    assert len(components) == 1
    body = components[0]
    assert body["type"] == "body"
    out: dict[str, str] = {}
    for param in body["parameters"]:
        assert param["type"] == "text"
        out[param["parameter_name"]] = param["text"]
    return out


def test_emits_single_body_component_with_named_text_parameters() -> None:
    row = _make_row(
        template_params={
            "tenant_name": "Cultor Barber",
            "question": "Cancelar la cita de María",
            "urgency": "high",
        }
    )
    components = _named(_template_components(row, tenant_name="Cultor Barber"))
    assert components == {
        "tenant_name": "Cultor Barber",
        "question": "Cancelar la cita de María",
        "urgency": "high",
        "correlation_id": "abcd1234",
    }


def test_falls_back_to_row_fields_when_template_params_missing() -> None:
    """If ``template_params_json`` is empty (defensive — should not
    happen post Phase-1 schema) the dispatcher falls back to the
    canonical row columns + the tenant name passed by the drain loop."""
    row = _make_row(template_params={})
    components = _named(_template_components(row, tenant_name="Backup Tenant"))
    assert components == {
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
    components = _named(_template_components(row, tenant_name="X"))
    assert components["correlation_id"] == "abcd1234"


def test_all_parameters_are_strings() -> None:
    """Cloud API rejects non-string ``text`` values — coercion happens in
    the renderer, not at send time."""
    row = _make_row(template_params={"urgency": "high"})
    for param in _template_components(row, tenant_name="T")[0]["parameters"]:
        assert isinstance(param["text"], str)
