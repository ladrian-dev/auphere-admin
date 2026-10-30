"""Spec 050 — the WhatsApp parser against Meta's 2026 payloads.

Complete batches (one envelope per element, so no element is lost), BSUID
and username identity, ``system`` identity changes, template buttons,
contacts, referral and errors. Fixtures: ``fixtures/meta_webhooks``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nexus_channels.base import InboundMessageKind
from nexus_channels.whatsapp_meta.webhook_adapter import (
    iter_identity_changes,
    iter_inbound_messages,
    iter_status_callbacks,
    split_into_elements,
)

FIXTURES = Path(__file__).parent / "fixtures" / "meta_webhooks"


def load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text())


# ── batches ──────────────────────────────────────────────────────────────────


def test_a_batch_of_messages_splits_into_one_envelope_per_message() -> None:
    parts = list(split_into_elements(load("batch_messages")))
    assert [p.field for p in parts] == ["messages"] * 5
    ids = [p.payload["entry"][0]["changes"][0]["value"]["messages"][0]["id"] for p in parts]
    assert ids == [f"wamid.BATCH{i}" for i in range(1, 6)]
    # Each part keeps what the handler needs to resolve the business.
    first = parts[0].payload["entry"][0]["changes"][0]["value"]
    assert first["metadata"]["display_phone_number"] == "34600000001"
    assert first["contacts"][0]["user_id"] == "ES.100000000000000001"


def test_a_batch_of_statuses_splits_too() -> None:
    parts = list(split_into_elements(load("batch_statuses")))
    assert len(parts) == 5
    assert all("statuses" in p.payload["entry"][0]["changes"][0]["value"] for p in parts)


def test_every_message_and_status_of_a_batch_parses() -> None:
    assert [m.provider_message_id for m in iter_inbound_messages(load("batch_messages"))] == [
        f"wamid.BATCH{i}" for i in range(1, 6)
    ]
    statuses = list(iter_status_callbacks(load("batch_statuses")))
    assert [s.wamid for s in statuses] == [f"wamid.OUT{i}" for i in range(1, 6)]


def test_non_message_fields_pass_through_whole() -> None:
    parts = list(split_into_elements(load("template_status_paused")))
    assert [p.field for p in parts] == ["message_template_status_update"]


# ── identity ────────────────────────────────────────────────────────────────


def test_a_message_without_phone_parses_with_its_bsuid() -> None:
    [msg] = list(iter_inbound_messages(load("message_bsuid_only")))
    assert msg.sender_phone is None
    assert msg.sender_bsuid == "ES.200000000000000002"
    assert msg.sender_identifier == "ES.200000000000000002"
    assert msg.username == "@sheena"
    assert msg.sender_name == "Sheena"
    assert msg.text == "hola, sin número"


def test_a_message_with_phone_and_bsuid_keeps_both() -> None:
    [msg] = list(iter_inbound_messages(load("message_phone_and_bsuid")))
    assert msg.sender_phone == "34611000001"
    assert msg.sender_bsuid == "ES.100000000000000001"
    # Today's key stays the phone: nothing that already exists changes.
    assert msg.sender_identifier == "34611000001"


def test_status_carries_the_recipient_bsuid_and_pricing() -> None:
    status = next(iter_status_callbacks(load("batch_statuses")))
    assert status.recipient_user_id == "ES.100000000000000001"
    assert status.pricing_billable is True
    assert status.pricing_type == "regular"
    assert status.pricing_category == "utility"


def test_system_messages_are_identity_changes_not_turns() -> None:
    assert list(iter_inbound_messages(load("system_user_changed_number"))) == []
    [change] = list(iter_identity_changes(load("system_user_changed_number")))
    assert change.kind == "user_changed_number"
    assert change.user_id == "ES.100000000000000001"
    assert change.new_phone == "34622000002"

    [change] = list(iter_identity_changes(load("system_user_changed_user_id")))
    assert change.kind == "user_changed_user_id"
    assert change.previous_user_id == "ES.100000000000000001"
    assert change.user_id == "ES.300000000000000003"


# ── message types ───────────────────────────────────────────────────────────


def test_template_button_reaches_the_agent_with_its_template() -> None:
    [msg] = list(iter_inbound_messages(load("template_button_reply")))
    assert msg.kind == InboundMessageKind.INTERACTIVE
    assert msg.interactive is not None
    assert msg.interactive.kind == "template_button"
    assert msg.interactive.payload_id == "CONFIRMAR"
    assert msg.interactive.title == "Confirmar"
    assert msg.context_message_id == "wamid.TPL1"


def test_contacts_become_readable_text() -> None:
    [msg] = list(iter_inbound_messages(load("message_contacts")))
    assert msg.kind == InboundMessageKind.CONTACTS
    assert msg.text is not None
    assert "Luis Pérez" in msg.text and "+34 633 000 003" in msg.text


def test_referral_is_parsed_as_data() -> None:
    [msg] = list(iter_inbound_messages(load("message_with_referral")))
    assert msg.referral is not None
    assert msg.referral["source_id"] == "120200000000000"
    assert msg.referral["headline"] == "Corte + barba"
    assert msg.text == "Vi su anuncio"


def test_unsupported_with_errors_keeps_the_code() -> None:
    [msg] = list(iter_inbound_messages(load("message_unsupported_error")))
    assert msg.kind == InboundMessageKind.UNSUPPORTED
    assert msg.error_codes == [131051]


# ── sending to a BSUID ──────────────────────────────────────────────────────


def test_a_phone_goes_in_to_and_a_bsuid_in_recipient() -> None:
    from nexus_channels.whatsapp_meta.meta_client import recipient_field

    assert recipient_field("34611000001") == {"to": "34611000001"}
    assert recipient_field("ES.200000000000000002") == {"recipient": "ES.200000000000000002"}


async def test_the_client_sends_a_bsuid_as_recipient() -> None:
    import httpx

    from nexus_channels.whatsapp_meta.meta_client import MetaClient

    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"messages": [{"id": "wamid.X"}]})

    client = MetaClient("secret", transport=httpx.MockTransport(handler))
    await client.send_text(
        phone_number_id="PN", access_token="T", to="ES.200000000000000002", body="hola"
    )
    await client.send_text(phone_number_id="PN", access_token="T", to="34611000001", body="hola")
    assert "recipient" in bodies[0] and "to" not in bodies[0]
    assert bodies[1]["to"] == "34611000001" and "recipient" not in bodies[1]


def test_only_unambiguous_words_are_an_opt_out() -> None:
    """QA 2026-10-30 (INC-19): «Cancelar» answering a booking reminder was an
    opt-out of marketing and never reached the agent."""
    from nexus_channels.whatsapp_meta.webhook_adapter import is_opt_out_text

    assert is_opt_out_text("STOP") == (True, "stop")
    assert is_opt_out_text("Baja.") == (True, "baja")
    assert is_opt_out_text("darme de baja")[0] is True
    for answer in ("Cancelar", "cancela!", "Salir", "quiero cancelar mi cita"):
        assert is_opt_out_text(answer) == (False, None), answer
