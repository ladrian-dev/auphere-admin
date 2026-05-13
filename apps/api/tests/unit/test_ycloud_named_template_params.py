"""Pin :meth:`YCloudClient.send_template` payload shape for both
positional and named body parameters.

YCloud's template editor (used in the manual Auphere ↔ Owner flow per
ADR-018) generates **named** variables — ``{{tenant_name}}`` rather than
``{{1}}``. Meta's Cloud API binds those by attaching ``parameter_name``
to each text parameter. Existing ``alert_*`` and ``no_show_followup``
templates still use positional binding, so the client must accept both
without callers having to pick a flag.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from nexus_channels.whatsapp_ycloud.ycloud_client import YCloudClient


class _CapturingTransport(httpx.AsyncBaseTransport):
    """Records every outgoing request body and returns a YCloud-shaped 200."""

    def __init__(self) -> None:
        self.last_payload: dict[str, Any] | None = None

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        import json

        self.last_payload = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={
                "id": "msg_001",
                "status": "sent",
                "whatsappMessage": {"wamid": "wamid.fake.1"},
            },
        )


@pytest.mark.asyncio
async def test_positional_body_params_render_without_parameter_name() -> None:
    transport = _CapturingTransport()
    client = YCloudClient("test-key", transport=transport)
    try:
        await client.send_template(
            from_phone="+56999990001",
            to="+56911112222",
            template_name="alert_cost_threshold_v1",
            language="es_CL",
            body_params=["USD 42.50", "USD 40.00"],
        )
    finally:
        await client.close()

    assert transport.last_payload is not None
    body_component = next(
        c for c in transport.last_payload["template"]["components"] if c["type"] == "body"
    )
    assert body_component["parameters"] == [
        {"type": "text", "text": "USD 42.50"},
        {"type": "text", "text": "USD 40.00"},
    ]


@pytest.mark.asyncio
async def test_named_body_params_render_with_parameter_name() -> None:
    """ADR-018 templates use named binding — every body parameter must
    carry ``parameter_name`` matching the variable registered in YCloud."""
    transport = _CapturingTransport()
    client = YCloudClient("test-key", transport=transport)
    try:
        await client.send_template(
            from_phone="+56000000000",
            to="+56911113333",
            template_name="auphere_owner_consult",
            language="es",
            body_params={
                "tenant_name": "Cultor Barber",
                "question": "¿Puedo agendar a Juan el sábado 17 a las 16:00?",
                "urgency": "normal",
                "correlation_id": "xK7mP2qR",
            },
        )
    finally:
        await client.close()

    assert transport.last_payload is not None
    body_component = next(
        c for c in transport.last_payload["template"]["components"] if c["type"] == "body"
    )
    rendered = body_component["parameters"]
    # Order is insertion order (Python dicts preserve), and every entry
    # carries both ``parameter_name`` and ``text``.
    assert rendered == [
        {
            "type": "text",
            "parameter_name": "tenant_name",
            "text": "Cultor Barber",
        },
        {
            "type": "text",
            "parameter_name": "question",
            "text": "¿Puedo agendar a Juan el sábado 17 a las 16:00?",
        },
        {
            "type": "text",
            "parameter_name": "urgency",
            "text": "normal",
        },
        {
            "type": "text",
            "parameter_name": "correlation_id",
            "text": "xK7mP2qR",
        },
    ]


@pytest.mark.asyncio
async def test_empty_named_dict_renders_empty_body_parameters() -> None:
    """Defensive — a tenant misconfigured with zero params shouldn't
    crash the dispatcher. The Meta API will reject the message, which
    is the right loud failure mode."""
    transport = _CapturingTransport()
    client = YCloudClient("test-key", transport=transport)
    try:
        await client.send_template(
            from_phone="+56000000000",
            to="+56911114444",
            template_name="auphere_owner_consult",
            language="es",
            body_params={},
        )
    finally:
        await client.close()

    assert transport.last_payload is not None
    body_component = next(
        c for c in transport.last_payload["template"]["components"] if c["type"] == "body"
    )
    assert body_component["parameters"] == []
