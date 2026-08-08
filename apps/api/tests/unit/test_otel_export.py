"""WP-01 (plataforma v2, Fase 0): trace context must survive the Redis queue.

The end-to-end guarantee is "one WhatsApp message → one trace". The API half
of that contract is: whatever span is active when the webhook publishes to
``nexus:inbound``, its W3C ``traceparent`` rides the stream entry's fields so
the worker can join the trace instead of starting a fresh one.

These tests pin both layers:

- ``inject_trace_fields`` stamps the *current* span context into a fields
  dict (and stays a no-op with no active span, so producers never publish a
  bogus ``traceparent``);
- a real POST to ``/webhook/meta`` produces a stream entry whose
  ``traceparent`` carries the caller's trace id (ASGITransport runs the app
  in the test's context, standing in for the FastAPI auto-instrumentation
  span that plays this role in production).
"""

from __future__ import annotations

import json
import uuid

import pytest
from nexus_channels.whatsapp_meta.signature import sign_meta_request
from opentelemetry.sdk.trace import TracerProvider
from sqlalchemy import text

from nexus_api.core.otel import inject_trace_fields

META_APP_SECRET = "dev-meta-app-secret-change-me"


def test_inject_trace_fields_stamps_current_span() -> None:
    provider = TracerProvider()
    tracer = provider.get_tracer("test")
    fields = {"tenant_id": "some-tenant"}
    with tracer.start_as_current_span("webhook") as span:
        inject_trace_fields(fields)
    trace_id_hex = f"{span.get_span_context().trace_id:032x}"
    assert "traceparent" in fields
    # W3C format: version-traceid-spanid-flags
    assert fields["traceparent"].split("-")[1] == trace_id_hex
    # The business payload is untouched.
    assert fields["tenant_id"] == "some-tenant"


def test_inject_trace_fields_noop_without_active_span() -> None:
    fields = {"tenant_id": "some-tenant"}
    inject_trace_fields(fields)
    assert "traceparent" not in fields


@pytest.mark.asyncio
async def test_webhook_inbound_entry_carries_traceparent(
    client, db_session, fake_redis, seed_tenants
) -> None:
    from nexus_api.db.models import Channel, ChannelStatus, ChannelType

    tenant_id = seed_tenants["a"]
    business_phone = "+56999911111"
    sender = "56922224444"

    async with db_session.begin():
        await db_session.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"),
            {"t": str(tenant_id)},
        )
        await db_session.execute(text("SET LOCAL ROLE nexus_app"))
        db_session.add(
            Channel(
                tenant_id=tenant_id,
                type=ChannelType.WHATSAPP,
                provider="meta",
                provider_identifier=business_phone,
                status=ChannelStatus.ACTIVE,
                config={"waba_id": "WABA-OTEL", "phone_number_id": "PN-OTEL"},
            )
        )

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA-OTEL",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": business_phone.lstrip("+"),
                                "phone_number_id": "PN-OTEL",
                            },
                            "contacts": [{"profile": {"name": "Cliente"}, "wa_id": sender}],
                            "messages": [
                                {
                                    "from": sender,
                                    "id": f"wamid.otel-{uuid.uuid4().hex[:8]}",
                                    "timestamp": "1716300000",
                                    "type": "text",
                                    "text": {"body": "hola trazas"},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }
    body = json.dumps(payload).encode()

    provider = TracerProvider()
    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("test-webhook-request") as span:
        r = await client.post(
            "/webhook/meta",
            content=body,
            headers={"X-Hub-Signature-256": sign_meta_request(META_APP_SECRET, body)},
        )
    assert r.status_code == 200, r.text

    entries = await fake_redis.xrange("nexus:inbound:standard", count=50)
    assert entries, "webhook did not enqueue the inbound message"
    decoded = [
        {
            (k.decode() if isinstance(k, bytes) else k): (
                v.decode() if isinstance(v, bytes) else v
            )
            for k, v in fields.items()
        }
        for _id, fields in entries
    ]
    mine = [e for e in decoded if e.get("tenant_id") == str(tenant_id)]
    assert mine, "no entry for the seeded tenant"
    trace_id_hex = f"{span.get_span_context().trace_id:032x}"
    assert mine[-1].get("traceparent", "").split("-")[1] == trace_id_hex
