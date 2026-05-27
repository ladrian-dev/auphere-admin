"""Block N additions to YCloudClient — media outbound, reactions, context
message id, and mark_as_read."""

from __future__ import annotations

import pytest
import respx

from nexus_channels.whatsapp_ycloud.ycloud_client import (
    YCLOUD_BASE_URL,
    YCloudAPIError,
    YCloudClient,
)

pytestmark = pytest.mark.asyncio


async def test_send_text_with_context_message_id_includes_context():
    async with respx.mock(base_url=YCLOUD_BASE_URL) as mock:
        route = mock.post("/whatsapp/messages/sendDirectly").respond(
            200, json={"id": "y1", "whatsappMessage": {"wamid": "w_out"}}
        )
        async with YCloudClient(api_key="k") as client:
            await client.send_text(
                from_phone="+5693",
                to="+5691",
                body="ok",
                context_message_id="wamid.previous",
            )
        body = route.calls[-1].request.content.decode()
        assert '"context":{"message_id":"wamid.previous"}' in body


async def test_send_image_link_and_caption():
    async with respx.mock(base_url=YCLOUD_BASE_URL) as mock:
        route = mock.post("/whatsapp/messages/sendDirectly").respond(200, json={"id": "y1"})
        async with YCloudClient(api_key="k") as client:
            await client.send_image(
                from_phone="+5693",
                to="+5691",
                link="https://bucket.s3/img.jpg",
                caption="el corte",
            )
        body = route.calls[-1].request.content.decode()
        assert '"type":"image"' in body
        assert '"link":"https://bucket.s3/img.jpg"' in body
        assert '"caption":"el corte"' in body


async def test_send_document_filename_persisted():
    async with respx.mock(base_url=YCLOUD_BASE_URL) as mock:
        route = mock.post("/whatsapp/messages/sendDirectly").respond(200, json={"id": "y1"})
        async with YCloudClient(api_key="k") as client:
            await client.send_document(
                from_phone="+5693",
                to="+5691",
                link="https://bucket.s3/doc.pdf",
                filename="precios.pdf",
            )
        body = route.calls[-1].request.content.decode()
        assert '"filename":"precios.pdf"' in body


async def test_send_reaction_payload_shape():
    async with respx.mock(base_url=YCLOUD_BASE_URL) as mock:
        route = mock.post("/whatsapp/messages/sendDirectly").respond(200, json={"id": "y1"})
        async with YCloudClient(api_key="k") as client:
            await client.send_reaction(
                from_phone="+5693",
                to="+5691",
                target_message_id="wamid.prev",
                emoji="🙏",
            )
        body = route.calls[-1].request.content.decode()
        assert '"type":"reaction"' in body
        assert '"message_id":"wamid.prev"' in body
        assert '"emoji":"🙏"' in body or "\\ud83d" in body  # emoji may be json-escaped


async def test_send_location_serialisation():
    async with respx.mock(base_url=YCLOUD_BASE_URL) as mock:
        route = mock.post("/whatsapp/messages/sendDirectly").respond(200, json={"id": "y1"})
        async with YCloudClient(api_key="k") as client:
            await client.send_location(
                from_phone="+5693",
                to="+5691",
                latitude=-33.45,
                longitude=-70.66,
                name="Cultor",
                address="Av. Providencia 123",
            )
        body = route.calls[-1].request.content.decode()
        assert '"type":"location"' in body
        assert '"latitude":-33.45' in body
        assert '"longitude":-70.66' in body
        assert '"address":"Av. Providencia 123"' in body


async def test_mark_as_read_calls_correct_endpoint():
    async with respx.mock(base_url=YCLOUD_BASE_URL) as mock:
        route = mock.post("/whatsapp/messages/markAsRead").respond(200, json={})
        async with YCloudClient(api_key="k") as client:
            await client.mark_as_read(from_phone="+5693", wamid="wamid.in")
        assert route.called
        body = route.calls[-1].request.content.decode()
        assert '"message_id":"wamid.in"' in body
        assert '"status":"read"' in body


async def test_get_phone_number_uses_e164_as_lookup_path_segment():
    """YCloud SMB doesn't expose a listing endpoint — the WABA-only
    ``GET /whatsapp/phoneNumbers/{wabaId}`` returns 404 — so the client
    always sends the second path segment. It can be either the Meta
    phone_number_id (numeric) or the E.164 phone number (YCloud
    soft-matches it)."""
    async with respx.mock(base_url=YCLOUD_BASE_URL) as mock:
        route = mock.get("/whatsapp/phoneNumbers/waba1/+56933334444").respond(
            200,
            json={
                "phoneNumber": "+56933334444",
                "displayName": "Cultor",
                "qualityRating": "GREEN",
                "id": "987654321098765",
            },
        )
        async with YCloudClient(api_key="k") as client:
            result = await client.get_phone_number(
                waba_id="waba1", phone_lookup="+56933334444"
            )
        assert route.called
        assert result["phoneNumber"] == "+56933334444"
        assert result["id"] == "987654321098765"
