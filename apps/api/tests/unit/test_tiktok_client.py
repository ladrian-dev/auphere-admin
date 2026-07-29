"""TikTok API client — envelope handling, error classification, retries.

The single most important behaviour under test: **TikTok answers HTTP 200
when the call failed.** A client that trusts the status code reports "message
sent" while the tenant's token is dead. Every error case below arrives with a
200 on purpose.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from nexus_channels.tiktok_bm.exceptions import (
    TikTokAPIError,
    TikTokRateLimitedError,
    TikTokTokenExchangeError,
    TikTokTokenInvalidatedError,
    TikTokTokenRefreshError,
    TikTokTransientError,
)
from nexus_channels.tiktok_bm.tiktok_client import TikTokClient

pytestmark = pytest.mark.asyncio

APP_ID = "app-1"
APP_SECRET = "secret-1"
TOKEN = "act.token"
BUSINESS_ID = "7123"
CONVERSATION_ID = "conv_1"
REDIRECT_URI = "https://api.auphere.com/admin/integrations/tiktok/callback"


def envelope(data: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"code": 0, "message": "OK", "request_id": "req-1", "data": data or {}}


def client_with(handler: Any, *, max_retries: int = 3) -> TikTokClient:
    return TikTokClient(
        APP_ID,
        APP_SECRET,
        max_retries=max_retries,
        transport=httpx.MockTransport(handler),
    )


async def test_success_returns_the_data_block() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=envelope({"message_id": "msg_1"}))

    async with client_with(handler) as client:
        result = await client.send_text(
            access_token=TOKEN,
            business_id=BUSINESS_ID,
            conversation_id=CONVERSATION_ID,
            text="hola",
        )

    assert result == {"message_id": "msg_1"}


async def test_http_200_with_nonzero_code_is_an_error_not_a_success() -> None:
    """The whole reason this client exists. A naive status-code check would
    return ``{}`` here and the caller would mark the message as sent."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"code": 40002, "message": "invalid conversation_id", "request_id": "req-2"},
        )

    async with client_with(handler) as client:
        with pytest.raises(TikTokAPIError) as excinfo:
            await client.send_text(
                access_token=TOKEN,
                business_id=BUSINESS_ID,
                conversation_id="bogus",
                text="hola",
            )

    assert excinfo.value.code == 40002
    assert excinfo.value.status_code == 200
    assert excinfo.value.request_id == "req-2"
    assert "invalid conversation_id" in excinfo.value.message


async def test_auth_failure_classifies_as_token_invalidated() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 40100, "message": "access token expired"})

    async with client_with(handler) as client:
        with pytest.raises(TikTokTokenInvalidatedError):
            await client.send_text(
                access_token=TOKEN,
                business_id=BUSINESS_ID,
                conversation_id=CONVERSATION_ID,
                text="hola",
            )


async def test_send_carries_the_access_token_header() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["token"] = request.headers.get("Access-Token")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=envelope({"message_id": "msg_1"}))

    async with client_with(handler) as client:
        await client.send_text(
            access_token=TOKEN,
            business_id=BUSINESS_ID,
            conversation_id=CONVERSATION_ID,
            text="hola",
        )

    assert seen["token"] == TOKEN
    assert seen["body"]["business_id"] == BUSINESS_ID
    assert seen["body"]["conversation_id"] == CONVERSATION_ID
    assert seen["body"]["content"] == {"text": "hola"}


async def test_exchange_uses_the_tiktok_account_holder_endpoint() -> None:
    """TikTok has two authorisation families and they are not interchangeable.

    Advertiser / Business Center accounts get long-term tokens from
    ``/oauth2/access_token/`` with ``app_id``/``secret``. TikTok **account
    holders** — which is what Business Messaging uses — get short-term tokens
    from ``/tt_user/oauth2/token/`` with ``client_id``/``client_secret`` and a
    ``redirect_uri`` that TikTok re-validates. Hitting the wrong family fails
    with an opaque error.
    """
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["has_token_header"] = "Access-Token" in request.headers
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=envelope({"access_token": "act.new"}))

    async with client_with(handler) as client:
        await client.exchange_auth_code(auth_code="code-1", redirect_uri=REDIRECT_URI)

    assert seen["path"].endswith("/tt_user/oauth2/token/")
    # The oauth endpoints authenticate with the app credentials in the body;
    # a stale Access-Token header alongside makes TikTok reject the call.
    assert seen["has_token_header"] is False
    assert seen["body"]["client_id"] == APP_ID
    assert seen["body"]["client_secret"] == APP_SECRET
    assert seen["body"]["grant_type"] == "authorization_code"
    assert seen["body"]["auth_code"] == "code-1"
    assert seen["body"]["redirect_uri"] == REDIRECT_URI


async def test_refresh_uses_the_account_holder_refresh_endpoint() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=envelope({"access_token": "act.new"}))

    async with client_with(handler) as client:
        await client.refresh_access_token(refresh_token="rft.1")

    assert seen["path"].endswith("/tt_user/oauth2/refresh_token/")
    assert seen["body"]["client_id"] == APP_ID
    assert seen["body"]["client_secret"] == APP_SECRET
    assert seen["body"]["grant_type"] == "refresh_token"
    assert seen["body"]["refresh_token"] == "rft.1"


async def test_exchange_failure_is_not_confused_with_losing_auth() -> None:
    """Onboarding failures must not flag an existing tenant as needing
    re-auth — different hierarchy, different UX."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 40100, "message": "auth_code expired"})

    async with client_with(handler) as client:
        with pytest.raises(TikTokTokenExchangeError):
            await client.exchange_auth_code(auth_code="stale", redirect_uri=REDIRECT_URI)


async def test_refresh_failure_raises_its_own_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 40100, "message": "refresh token expired"})

    async with client_with(handler) as client:
        with pytest.raises(TikTokTokenRefreshError):
            await client.refresh_access_token(refresh_token="rft.dead")


async def test_retries_transient_failures_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, text="upstream unavailable")
        return httpx.Response(200, json=envelope({"message_id": "msg_1"}))

    async with client_with(handler) as client:
        result = await client.send_text(
            access_token=TOKEN,
            business_id=BUSINESS_ID,
            conversation_id=CONVERSATION_ID,
            text="hola",
        )

    assert calls["n"] == 3
    assert result == {"message_id": "msg_1"}


async def test_gives_up_after_max_retries_on_sustained_5xx() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, text="boom")

    async with client_with(handler, max_retries=3) as client:
        with pytest.raises(TikTokTransientError):
            await client.send_text(
                access_token=TOKEN,
                business_id=BUSINESS_ID,
                conversation_id=CONVERSATION_ID,
                text="hola",
            )

    assert calls["n"] == 3


async def test_rate_limiting_is_retried() -> None:
    """Business Messaging caps around 10 QPS, which a reminder fan-out can
    brush against — a 429 is backpressure, not a contract error."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"code": 50002, "message": "service busy"})
        return httpx.Response(200, json=envelope({"message_id": "msg_1"}))

    async with client_with(handler) as client:
        result = await client.send_text(
            access_token=TOKEN,
            business_id=BUSINESS_ID,
            conversation_id=CONVERSATION_ID,
            text="hola",
        )

    assert calls["n"] == 2
    assert result == {"message_id": "msg_1"}


async def test_rate_limit_surfaces_when_it_never_clears() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"code": 50002, "message": "service busy"})

    async with client_with(handler) as client:
        with pytest.raises(TikTokRateLimitedError):
            await client.send_text(
                access_token=TOKEN,
                business_id=BUSINESS_ID,
                conversation_id=CONVERSATION_ID,
                text="hola",
            )


async def test_a_contract_error_is_not_retried() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"code": 40002, "message": "bad param"})

    async with client_with(handler) as client:
        with pytest.raises(TikTokAPIError):
            await client.send_text(
                access_token=TOKEN,
                business_id=BUSINESS_ID,
                conversation_id=CONVERSATION_ID,
                text="hola",
            )

    assert calls["n"] == 1


async def test_unparseable_body_is_an_error_not_an_empty_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>gateway</html>")

    async with client_with(handler) as client:
        with pytest.raises(TikTokAPIError, match="unparseable"):
            await client.send_text(
                access_token=TOKEN,
                business_id=BUSINESS_ID,
                conversation_id=CONVERSATION_ID,
                text="hola",
            )


async def test_download_image_returns_bytes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"\x89PNG-bytes", headers={"content-type": "image/png"})

    async with client_with(handler) as client:
        content, mime = await client.download_image(
            access_token=TOKEN, business_id=BUSINESS_ID, image_id="img_1"
        )

    assert content == b"\x89PNG-bytes"
    assert mime == "image/png"


async def test_download_image_surfaces_a_json_error_envelope() -> None:
    """A JSON body where bytes were expected means the id was rejected;
    returning it as image content would persist a JSON blob to S3."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 40002, "message": "image not found"})

    async with client_with(handler) as client:
        with pytest.raises(TikTokAPIError):
            await client.download_image(
                access_token=TOKEN, business_id=BUSINESS_ID, image_id="ghost"
            )


async def test_transport_errors_become_transient_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("dns failure", request=request)

    async with client_with(handler) as client:
        with pytest.raises(TikTokTransientError, match=r"transport error|retries exhausted"):
            await client.send_text(
                access_token=TOKEN,
                business_id=BUSINESS_ID,
                conversation_id=CONVERSATION_ID,
                text="hola",
            )


async def test_rejects_construction_without_a_secret() -> None:
    with pytest.raises(ValueError, match="app_secret"):
        TikTokClient(APP_ID, "")
