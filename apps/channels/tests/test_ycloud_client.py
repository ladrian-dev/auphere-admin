"""Tests for :class:`YCloudClient` using respx (httpx mock transport).

These are pure unit tests — they never hit the real YCloud endpoint.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from nexus_channels.whatsapp_ycloud.ycloud_client import (
    YCLOUD_BASE_URL,
    YCloudAPIError,
    YCloudClient,
)

pytestmark = pytest.mark.asyncio


async def test_send_text_includes_x_api_key_header_and_payload():
    async with respx.mock(base_url=YCLOUD_BASE_URL) as mock:
        route = mock.post("/whatsapp/messages/sendDirectly").respond(
            200,
            json={
                "id": "ycl_1",
                "status": "queued",
                "whatsappMessage": {"wamid": "wamid.HBg1"},
            },
        )
        async with YCloudClient(api_key="key-123") as client:
            result = await client.send_text(
                from_phone="+56933334444", to="+56911112222", body="hola"
            )
        assert result["whatsappMessage"]["wamid"] == "wamid.HBg1"
        assert route.called
        request = route.calls[-1].request
        assert request.headers["X-API-Key"] == "key-123"
        assert "authorization" not in request.headers
        sent_payload = route.calls[-1].request.content.decode()
        assert '"from":"+56933334444"' in sent_payload
        assert '"to":"+56911112222"' in sent_payload
        assert '"text":{"body":"hola"}' in sent_payload


async def test_send_template_builds_components():
    async with respx.mock(base_url=YCLOUD_BASE_URL) as mock:
        route = mock.post("/whatsapp/messages/sendDirectly").respond(
            200, json={"id": "ycl_2", "status": "queued"}
        )
        async with YCloudClient(api_key="k") as client:
            await client.send_template(
                from_phone="+5693",
                to="+5691",
                template_name="reminder_24h",
                language="es_CL",
                body_params=["Juan", "viernes 10", "15:00", "Luis"],
            )
        body = route.calls[-1].request.content.decode()
        assert '"name":"reminder_24h"' in body
        assert '"code":"es_CL"' in body
        assert body.count('"type":"text"') == 4  # one per body param


async def test_4xx_raises_ycloud_api_error():
    async with respx.mock(base_url=YCLOUD_BASE_URL) as mock:
        mock.post("/whatsapp/messages/sendDirectly").respond(
            422, json={"message": "invalid template name"}
        )
        async with YCloudClient(api_key="k") as client:
            with pytest.raises(YCloudAPIError) as ei:
                await client.send_text(from_phone="+5693", to="+5691", body="x")
        assert ei.value.status_code == 422


async def test_transport_error_raises_with_status_zero():
    async with respx.mock(base_url=YCLOUD_BASE_URL) as mock:
        mock.post("/whatsapp/messages/sendDirectly").mock(side_effect=httpx.ConnectError("boom"))
        async with YCloudClient(api_key="k") as client:
            with pytest.raises(YCloudAPIError) as ei:
                await client.send_text(from_phone="+5693", to="+5691", body="x")
        assert ei.value.status_code == 0


async def test_bind_waba_hits_tp_endpoint_by_default():
    async with respx.mock(base_url=YCLOUD_BASE_URL) as mock:
        route = mock.post("/whatsapp/businessAccounts/W123/tp/bind").respond(200, json={})
        async with YCloudClient(api_key="k") as client:
            await client.bind_waba("W123")
        assert route.called


async def test_bind_waba_coexistence_hits_smb_endpoint():
    async with respx.mock(base_url=YCLOUD_BASE_URL) as mock:
        route = mock.post("/whatsapp/businessAccounts/W123/smb/bind").respond(200, json={})
        async with YCloudClient(api_key="k") as client:
            await client.bind_waba("W123", coexistence=True)
        assert route.called


async def test_register_phone_number():
    async with respx.mock(base_url=YCLOUD_BASE_URL) as mock:
        route = mock.post("/whatsapp/phoneNumbers/W1/P1/register").respond(200, json={})
        async with YCloudClient(api_key="k") as client:
            await client.register_phone_number(waba_id="W1", phone_number_id="P1")
        assert route.called


async def test_empty_api_key_rejected():
    with pytest.raises(ValueError):
        YCloudClient(api_key="")
