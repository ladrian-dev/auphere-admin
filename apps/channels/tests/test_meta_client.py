"""Tests for :class:`MetaClient` — pure unit tests via ``respx``."""

from __future__ import annotations

import httpx
import pytest
import respx

from nexus_channels.whatsapp_meta.exceptions import (
    MetaAPIError,
    MetaRateLimitedError,
    MetaTransientError,
    TokenInvalidatedError,
)
from nexus_channels.whatsapp_meta.meta_client import META_GRAPH_BASE_URL, MetaClient
from nexus_channels.whatsapp_meta.signature import appsecret_proof

pytestmark = pytest.mark.asyncio

# Defaults shared by the fast paths.
_TOKEN = "EAA-bisuat-demo"
_SECRET = "app-secret-demo"


async def test_send_text_injects_appsecret_proof_and_body() -> None:
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        route = mock.post("/PN_1/messages").respond(
            200,
            json={
                "messaging_product": "whatsapp",
                "contacts": [{"input": "56911", "wa_id": "56911"}],
                "messages": [{"id": "wamid.OUT", "message_status": "accepted"}],
            },
        )
        async with MetaClient(_SECRET) as client:
            result = await client.send_text(
                phone_number_id="PN_1",
                access_token=_TOKEN,
                to="56911",
                body="hola",
            )

        assert result["messages"][0]["id"] == "wamid.OUT"
        assert route.called
        request = route.calls[-1].request
        assert f"access_token={_TOKEN}" in str(request.url)
        expected_proof = appsecret_proof(_TOKEN, _SECRET)
        assert f"appsecret_proof={expected_proof}" in str(request.url)
        body_text = request.content.decode()
        assert '"to":"56911"' in body_text
        assert '"text":{"body":"hola"' in body_text


async def test_send_text_can_disable_appsecret_proof() -> None:
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        route = mock.post("/PN_1/messages").respond(
            200,
            json={"messages": [{"id": "wamid.OUT"}]},
        )
        async with MetaClient(_SECRET, require_appsecret_proof=False) as client:
            await client.send_text(
                phone_number_id="PN_1",
                access_token=_TOKEN,
                to="56911",
                body="x",
            )
        url = str(route.calls[-1].request.url)
        assert f"access_token={_TOKEN}" in url
        assert "appsecret_proof=" not in url


async def test_oauth_exception_190_raises_token_invalidated() -> None:
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        mock.post("/PN_1/messages").respond(
            401,
            json={
                "error": {
                    "message": "Session has expired",
                    "type": "OAuthException",
                    "code": 190,
                    "error_subcode": 463,
                    "fbtrace_id": "trace-1",
                }
            },
        )
        async with MetaClient(_SECRET) as client:
            with pytest.raises(TokenInvalidatedError) as exc:
                await client.send_text(
                    phone_number_id="PN_1",
                    access_token=_TOKEN,
                    to="56911",
                    body="x",
                )
        assert exc.value.code == 190
        assert exc.value.subcode == 463
        assert exc.value.fbtrace_id == "trace-1"


async def test_http_429_raises_rate_limited_after_retries() -> None:
    # Three 429s in a row → tenacity exhausts; the last one surfaces.
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        mock.post("/PN_1/messages").respond(
            429,
            json={"error": {"message": "throttled", "code": 80004}},
        )
        async with MetaClient(_SECRET, max_retries=3) as client:
            with pytest.raises(MetaRateLimitedError):
                await client.send_text(
                    phone_number_id="PN_1",
                    access_token=_TOKEN,
                    to="56911",
                    body="x",
                )


async def test_500_raises_transient_after_retries() -> None:
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        mock.post("/PN_1/messages").respond(502, json={"error": {"message": "bad gateway"}})
        async with MetaClient(_SECRET, max_retries=2) as client:
            with pytest.raises(MetaTransientError):
                await client.send_text(
                    phone_number_id="PN_1",
                    access_token=_TOKEN,
                    to="56911",
                    body="x",
                )


async def test_400_raises_generic_meta_api_error_no_retry() -> None:
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        route = mock.post("/PN_1/messages").respond(
            400,
            json={
                "error": {
                    "message": "param 'to' invalid",
                    "code": 100,
                }
            },
        )
        async with MetaClient(_SECRET, max_retries=3) as client:
            with pytest.raises(MetaAPIError) as exc:
                await client.send_text(
                    phone_number_id="PN_1",
                    access_token=_TOKEN,
                    to="???",
                    body="x",
                )
        assert exc.value.status_code == 400
        assert exc.value.code == 100
        assert not isinstance(exc.value, MetaRateLimitedError)
        assert not isinstance(exc.value, MetaTransientError)
        # 4xx (other than 429) must not be retried.
        assert route.call_count == 1


async def test_transport_error_promotes_to_transient() -> None:
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        mock.post("/PN_1/messages").mock(side_effect=httpx.ConnectError("boom"))
        async with MetaClient(_SECRET, max_retries=2) as client:
            with pytest.raises(MetaTransientError):
                await client.send_text(
                    phone_number_id="PN_1",
                    access_token=_TOKEN,
                    to="56911",
                    body="x",
                )


@pytest.mark.parametrize(
    "transport_exc",
    [
        httpx.PoolTimeout("pool exhausted"),
        httpx.ConnectTimeout("connect timed out"),
        httpx.ReadTimeout("read timed out"),
        httpx.ConnectError("refused"),
        httpx.RemoteProtocolError("peer closed"),
    ],
    ids=["pool", "connect_timeout", "read_timeout", "connect_error", "protocol"],
)
async def test_every_transport_error_promotes_to_transient(
    transport_exc: Exception,
) -> None:
    """No httpx error may escape raw.

    Callers map ``MetaAPIError`` to a clean 4xx/502; anything else reaches
    FastAPI as a 500. ``PoolTimeout`` escaping this way is what aborted the
    New Air campaign mid-batch, so the guarantee is per transport class,
    not per the two that happened to be listed.
    """
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        mock.get("/WABA_1/message_templates").mock(side_effect=transport_exc)
        async with MetaClient(_SECRET, max_retries=2) as client:
            with pytest.raises(MetaTransientError):
                await client.list_templates(waba_id="WABA_1", access_token=_TOKEN)


async def test_send_template_builds_payload() -> None:
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        route = mock.post("/PN_1/messages").respond(200, json={"messages": [{"id": "wamid.T"}]})
        async with MetaClient(_SECRET) as client:
            await client.send_template(
                phone_number_id="PN_1",
                access_token=_TOKEN,
                to="56911",
                template_name="reminder_24h",
                language="es_CL",
                components=[
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": "Juan"},
                            {"type": "text", "text": "viernes"},
                        ],
                    }
                ],
            )
        body = route.calls[-1].request.content.decode()
        assert '"name":"reminder_24h"' in body
        assert '"code":"es_CL"' in body
        assert body.count('"type":"text"') == 2


async def test_subscribe_app_payload_optional_fields() -> None:
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        route = mock.post("/WABA_1/subscribed_apps").respond(200, json={"success": True})
        async with MetaClient(_SECRET) as client:
            await client.subscribe_app(
                waba_id="WABA_1",
                access_token=_TOKEN,
                override_callback_uri="https://webhooks.auphere.com/webhook/meta",
                verify_token="vt-12345",
            )
        body = route.calls[-1].request.content.decode()
        assert "override_callback_uri" in body
        assert "verify_token" in body


async def test_exchange_code_does_not_use_appsecret_proof() -> None:
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        route = mock.get("/oauth/access_token").respond(
            200, json={"access_token": "EAA-bisuat", "expires_in": 5_184_000}
        )
        async with MetaClient(_SECRET) as client:
            result = await client.exchange_code(
                app_id="957213733862330",
                code="OAUTH_CODE_XYZ",
            )
        assert result["access_token"] == "EAA-bisuat"
        url = str(route.calls[-1].request.url)
        assert "client_secret=" in url
        assert "code=OAUTH_CODE_XYZ" in url
        assert "appsecret_proof=" not in url


async def test_get_phone_number_passes_fields_param() -> None:
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        route = mock.get("/PN_1").respond(
            200,
            json={
                "display_phone_number": "+56933334444",
                "verified_name": "Cultor Barber",
                "quality_rating": "GREEN",
                "messaging_limit_tier": "TIER_1K",
            },
        )
        async with MetaClient(_SECRET) as client:
            info = await client.get_phone_number(phone_number_id="PN_1", access_token=_TOKEN)
        assert info["quality_rating"] == "GREEN"
        assert "fields=" in str(route.calls[-1].request.url)


async def test_get_media_url_then_download_media() -> None:
    cdn_url = "https://lookaside.fbsbx.com/whatsapp_business/attachments/?mid=media-1"
    async with respx.mock() as mock:
        mock.get(f"{META_GRAPH_BASE_URL}/media-1").respond(
            200,
            json={
                "url": cdn_url,
                "mime_type": "image/jpeg",
                "sha256": "abc123",
                "file_size": 12345,
            },
        )
        mock.get(cdn_url).respond(
            200,
            content=b"\xff\xd8\xff",
            headers={"content-type": "image/jpeg"},
        )
        async with MetaClient(_SECRET) as client:
            meta = await client.get_media_url(media_id="media-1", access_token=_TOKEN)
            content, content_type = await client.download_media(url=cdn_url, access_token=_TOKEN)
        assert meta["url"] == cdn_url
        assert content[:3] == b"\xff\xd8\xff"
        assert content_type == "image/jpeg"
