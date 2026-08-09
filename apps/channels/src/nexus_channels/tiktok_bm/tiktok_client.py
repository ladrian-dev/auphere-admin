"""Async ``httpx`` wrapper around the TikTok API for Business (v1.3).

Endpoints exercised for Business Messaging:

- ``POST /tt_user/oauth2/token/`` — exchange an ``auth_code`` for a token pair.
- ``POST /tt_user/oauth2/refresh_token/`` — rotate the access token (daily).
- ``GET  /business/get/`` — the authorised Business Account(s): id, name,
  region. Used during authorisation to pick the channel identity.
- ``POST /business/message/send/`` — send a message into a conversation.
- ``GET  /business/message/conversation/list/`` — list conversations.
- ``GET  /business/message/list/`` — list messages in a conversation.
- ``POST /business/message/image/upload/`` — upload an image for sending.
- ``GET  /business/message/image/download/`` — fetch an inbound image.
- ``POST /business/message/webhook/create/`` — register our callback.
- ``GET  /business/message/webhook/get/`` — read the current registration.
- ``POST /business/message/webhook/delete/`` — drop it on offboarding.

Auth model
----------
Every call except the two ``tt_user/oauth2`` ones takes ``access_token`` as a
kwarg and sends it in the ``Access-Token`` header. No token is held
internally — it lives in ``tenant_credentials.encrypted_payload`` and is
resolved per request by the caller, so one client instance safely serves
every tenant.

Note the ``tt_user`` namespace. TikTok has two distinct authorisation
families: advertiser / Business Center accounts issue **long-term** tokens
via ``/oauth2/access_token/``, while **TikTok account holders** issue
**short-term** tokens (one day) via ``/tt_user/oauth2/token/``. Business
Messaging is the account-holder flow. Using the advertiser endpoints here
would fail, and the parameter names differ too (``client_id`` /
``client_secret`` rather than ``app_id`` / ``secret``).

The error contract is the thing to be careful about
---------------------------------------------------
**TikTok answers HTTP 200 on failure.** The envelope is::

    {"code": 0, "message": "OK", "request_id": "...", "data": {...}}

``code == 0`` means success; anything else is an error that arrived with a
200 status. Treating ``resp.status_code < 400`` as success — the reflex from
every other API — would silently turn "your token expired" into "message
sent". :meth:`_handle_response` therefore classifies on ``code`` first and
only falls back to the HTTP status when the envelope is unparseable.

Retry policy
------------
Lives inside the client, same rationale as :class:`MetaClient`: the webhook
route, the authorisation orchestrator and the refresh cron all use it and
need one uniform policy.

- HTTP 5xx, 429, throttling codes, ``ConnectError``, ``ReadTimeout`` → up to
  3 attempts with exponential backoff (0.5s, 1s, 2s).
- Auth failures and other 4xx-equivalent codes → no retry; surface at once.

Business Messaging is rate-limited around 10 QPS, which a reminder fan-out
can brush against, so 429 handling is a live path rather than theory.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any, Final, TypeVar, cast

import httpx
import structlog
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from nexus_channels.tiktok_bm.exceptions import (
    TikTokAPIError,
    TikTokRateLimitedError,
    TikTokTokenExchangeError,
    TikTokTokenInvalidatedError,
    TikTokTokenRefreshError,
    TikTokTransientError,
)

TIKTOK_API_BASE_URL: Final = "https://business-api.tiktok.com"
TIKTOK_API_VERSION: Final = "v1.3"

# Envelope code for success. Everything else is a failure, including on 200.
_OK: Final = 0

# Codes that mean "this token is dead, refreshing won't help" → the tenant
# must re-authorise. TikTok's 40100-range covers authentication failures.
_TOKEN_INVALIDATED_CODES: Final = frozenset({40001, 40100, 40101, 40102, 40105})

# Throttling. 50002 is TikTok's documented "service busy / rate limited".
_RATE_LIMIT_CODES: Final = frozenset({40016, 50002})

# Server-side failures worth retrying.
_TRANSIENT_CODES: Final = frozenset({50000, 50001})

log = structlog.get_logger(__name__)

# Retorno genérico de _with_retries: preserva el tipo del intento.
_R = TypeVar("_R")


class TikTokClient:
    """Thin async client. Reuse one instance per process — it owns an
    ``httpx`` connection pool and holds no per-tenant state.
    """

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        *,
        max_retries: int = 3,
        timeout: float = 15.0,
        base_url: str = TIKTOK_API_BASE_URL,
        api_version: str = TIKTOK_API_VERSION,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not app_secret:
            raise ValueError("TikTokClient.app_secret must be non-empty")
        self._app_id = app_id
        self._app_secret = app_secret
        self._max_retries = max_retries
        self._client = httpx.AsyncClient(
            base_url=f"{base_url.rstrip('/')}/open_api/{api_version}",
            timeout=timeout,
            transport=transport,
            headers={
                "Accept": "application/json",
                "User-Agent": "auphere-nexus-tiktok/0.1",
            },
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> TikTokClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    # ── oauth ──────────────────────────────────────────────────────────────

    async def exchange_auth_code(self, *, auth_code: str, redirect_uri: str) -> dict[str, Any]:
        """Trade the one-shot ``auth_code`` for an access/refresh token pair.

        Uses the **TikTok account holder** flow (``/tt_user/oauth2/token/``),
        not the advertiser flow (``/oauth2/access_token/``). They are separate
        endpoint families with different parameter names, and Business
        Messaging only works with the account-holder one — it is what issues
        the *short-term* token that expires in a day.

        ``auth_code`` is valid for 10 minutes and single-use. ``redirect_uri``
        must match the TikTok account holder redirect URL registered on the
        app, character for character, or TikTok rejects the exchange.

        Returns the ``data`` block: ``access_token``, ``expires_in``,
        ``refresh_token``, ``refresh_token_expires_in``, ``scope``.

        Raises :class:`TikTokTokenExchangeError` rather than the generic API
        error so onboarding failures can't be mistaken for an existing tenant
        losing auth — the two demand very different UX.
        """
        try:
            return await self._post(
                "/tt_user/oauth2/token/",
                json_body={
                    "client_id": self._app_id,
                    "client_secret": self._app_secret,
                    "grant_type": "authorization_code",
                    "auth_code": auth_code,
                    "redirect_uri": redirect_uri,
                },
            )
        except TikTokAPIError as exc:
            raise TikTokTokenExchangeError(
                f"auth_code exchange rejected by TikTok: {exc.message}"
            ) from exc

    async def refresh_access_token(self, *, refresh_token: str) -> dict[str, Any]:
        """Rotate the short-term access token.

        TikTok returns a *new* refresh token too — callers must persist both
        or the next rotation fails.
        """
        try:
            return await self._post(
                "/tt_user/oauth2/refresh_token/",
                json_body={
                    "client_id": self._app_id,
                    "client_secret": self._app_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )
        except TikTokAPIError as exc:
            raise TikTokTokenRefreshError(
                f"refresh_token rejected by TikTok: {exc.message}"
            ) from exc

    # ── business account ───────────────────────────────────────────────────

    async def get_business_accounts(self, *, access_token: str) -> dict[str, Any]:
        """Business Accounts this authorisation covers.

        Used once during authorisation to resolve the ``business_id`` that
        becomes ``channels.provider_identifier``, plus the display name and
        region shown in the panel.
        """
        return await self._get("/business/get/", access_token=access_token)

    # ── messaging ──────────────────────────────────────────────────────────

    async def send_text(
        self,
        *,
        access_token: str,
        business_id: str,
        conversation_id: str,
        text: str,
    ) -> dict[str, Any]:
        """Send a plain-text message into an existing conversation.

        There is no "start a conversation" call — TikTok only permits replies
        inside a window opened by the user. Callers must have a
        ``conversation_id`` from an inbound event.
        """
        return await self._post(
            "/business/message/send/",
            access_token=access_token,
            json_body={
                "business_id": business_id,
                "conversation_id": conversation_id,
                "message_type": "text",
                "content": {"text": text},
            },
        )

    async def send_image(
        self,
        *,
        access_token: str,
        business_id: str,
        conversation_id: str,
        image_id: str,
    ) -> dict[str, Any]:
        """Send a previously-uploaded image. ``image_id`` comes from
        :meth:`upload_image` — TikTok does not accept a bare URL."""
        return await self._post(
            "/business/message/send/",
            access_token=access_token,
            json_body={
                "business_id": business_id,
                "conversation_id": conversation_id,
                "message_type": "image",
                "content": {"image_id": image_id},
            },
        )

    async def upload_image(
        self,
        *,
        access_token: str,
        business_id: str,
        content: bytes,
        filename: str = "image.jpg",
        mime_type: str = "image/jpeg",
    ) -> dict[str, Any]:
        """Upload image bytes and get back an ``image_id`` for sending."""
        return await self._post_multipart(
            "/business/message/image/upload/",
            access_token=access_token,
            data={"business_id": business_id},
            files={"image": (filename, content, mime_type)},
        )

    async def download_image(
        self,
        *,
        access_token: str,
        business_id: str,
        image_id: str,
    ) -> tuple[bytes, str | None]:
        """Fetch inbound image bytes. Returns ``(content, mime_type)``.

        Unlike every other method this one returns raw bytes, so it bypasses
        the JSON envelope handling — but it still has to cope with TikTok
        answering 200-with-an-error-envelope when the id is bad, hence the
        content-type sniff.
        """

        async def attempt() -> tuple[bytes, str | None]:
            resp = await self._client.get(
                "/business/message/image/download/",
                params={"business_id": business_id, "image_id": image_id},
                headers={"Access-Token": access_token},
            )
            content_type = resp.headers.get("content-type")
            if resp.status_code >= 400:
                raise self._classify(
                    status_code=resp.status_code,
                    code=None,
                    message=f"HTTP {resp.status_code}",
                    request_id=None,
                    body=resp.text[:500],
                )
            # A JSON body where bytes were expected means the envelope path:
            # re-run it through the normal handler so the error classifies
            # like every other failure instead of becoming a corrupt image.
            if content_type and "application/json" in content_type:
                self._handle_response(resp)
                raise TikTokAPIError(
                    "image download returned a JSON success envelope, expected bytes",
                    status_code=resp.status_code,
                )
            return resp.content, content_type

        return await self._with_retries(attempt)

    async def list_conversations(
        self,
        *,
        access_token: str,
        business_id: str,
        page_size: int = 20,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"business_id": business_id, "page_size": page_size}
        if cursor:
            params["cursor"] = cursor
        return await self._get(
            "/business/message/conversation/list/",
            access_token=access_token,
            params=params,
        )

    async def list_messages(
        self,
        *,
        access_token: str,
        business_id: str,
        conversation_id: str,
        page_size: int = 20,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "business_id": business_id,
            "conversation_id": conversation_id,
            "page_size": page_size,
        }
        if cursor:
            params["cursor"] = cursor
        return await self._get(
            "/business/message/list/",
            access_token=access_token,
            params=params,
        )

    # ── webhooks ───────────────────────────────────────────────────────────

    async def create_webhook_config(
        self,
        *,
        access_token: str,
        business_id: str,
        callback_url: str,
    ) -> dict[str, Any]:
        """Point this Business Account's messaging events at our endpoint."""
        return await self._post(
            "/business/message/webhook/create/",
            access_token=access_token,
            json_body={"business_id": business_id, "callback_url": callback_url},
        )

    async def get_webhook_config(
        self,
        *,
        access_token: str,
        business_id: str,
    ) -> dict[str, Any]:
        return await self._get(
            "/business/message/webhook/get/",
            access_token=access_token,
            params={"business_id": business_id},
        )

    async def delete_webhook_config(
        self,
        *,
        access_token: str,
        business_id: str,
    ) -> dict[str, Any]:
        """Called on offboarding so TikTok stops delivering to a channel we
        no longer own."""
        return await self._post(
            "/business/message/webhook/delete/",
            access_token=access_token,
            json_body={"business_id": business_id},
        )

    # ── transport ──────────────────────────────────────────────────────────

    async def _get(
        self,
        path: str,
        *,
        access_token: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        async def attempt() -> dict[str, Any]:
            resp = await self._client.get(
                path,
                params=params or {},
                headers={"Access-Token": access_token},
            )
            return self._handle_response(resp)

        return await self._with_retries(attempt)

    async def _post(
        self,
        path: str,
        *,
        access_token: str | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        async def attempt() -> dict[str, Any]:
            resp = await self._client.post(
                path,
                json=json_body,
                headers=self._auth_headers(access_token),
            )
            return self._handle_response(resp)

        return await self._with_retries(attempt)

    async def _post_multipart(
        self,
        path: str,
        *,
        access_token: str,
        data: dict[str, Any],
        files: dict[str, Any],
    ) -> dict[str, Any]:
        async def attempt() -> dict[str, Any]:
            resp = await self._client.post(
                path,
                data=data,
                files=files,
                headers=self._auth_headers(access_token),
            )
            return self._handle_response(resp)

        return await self._with_retries(attempt)

    def _auth_headers(self, access_token: str | None) -> dict[str, str]:
        # The two oauth2 endpoints authenticate with app_id/secret in the
        # body and must NOT carry an Access-Token header.
        return {"Access-Token": access_token} if access_token else {}

    def _handle_response(self, response: httpx.Response) -> dict[str, Any]:
        """Return the ``data`` block, or raise the right exception.

        Reminder: a 200 here proves nothing. The envelope's ``code`` is the
        real status, and it is checked first.
        """
        body_text = response.text
        envelope: dict[str, Any] = {}
        try:
            parsed = response.json()
            if isinstance(parsed, dict):
                envelope = parsed
        except json.JSONDecodeError:
            envelope = {}

        code_raw = envelope.get("code")
        code: int | None = code_raw if isinstance(code_raw, int) else None
        message_raw = envelope.get("message")
        message: str = (
            message_raw if isinstance(message_raw, str) else f"HTTP {response.status_code}"
        )
        request_id_raw = envelope.get("request_id")
        request_id: str | None = request_id_raw if isinstance(request_id_raw, str) else None

        if code == _OK:
            data = envelope.get("data")
            return cast(dict[str, Any], data) if isinstance(data, dict) else {}

        # No parseable envelope: fall back to the HTTP status. A 2xx with an
        # unreadable body is treated as an error rather than an empty success,
        # because every documented endpoint returns an envelope.
        if code is None and response.status_code < 400 and not envelope:
            raise TikTokAPIError(
                "unparseable response body (expected a TikTok envelope)",
                status_code=response.status_code,
                body=body_text[:500],
            )

        raise self._classify(
            status_code=response.status_code,
            code=code,
            message=message,
            request_id=request_id,
            body=body_text[:500],
        )

    def _classify(
        self,
        *,
        status_code: int,
        code: int | None,
        message: str,
        request_id: str | None,
        body: str | None,
    ) -> TikTokAPIError:
        kwargs: dict[str, Any] = {
            "status_code": status_code,
            "code": code,
            "request_id": request_id,
            "body": body,
        }
        if code is not None and code in _TOKEN_INVALIDATED_CODES:
            return TikTokTokenInvalidatedError(message, **kwargs)
        if status_code == 429 or (code is not None and code in _RATE_LIMIT_CODES):
            return TikTokRateLimitedError(message, **kwargs)
        if status_code >= 500 or (code is not None and code in _TRANSIENT_CODES):
            return TikTokTransientError(message, **kwargs)
        return TikTokAPIError(message, **kwargs)

    async def _with_retries(
        self,
        attempt: Callable[[], Awaitable[_R]],
    ) -> _R:
        try:
            async for retry_state in AsyncRetrying(
                stop=stop_after_attempt(self._max_retries),
                wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
                retry=retry_if_exception_type(
                    (
                        TikTokTransientError,
                        TikTokRateLimitedError,
                        httpx.ConnectError,
                        httpx.ReadTimeout,
                    )
                ),
                reraise=True,
            ):
                with retry_state:
                    try:
                        return await attempt()
                    except (httpx.ConnectError, httpx.ReadTimeout) as exc:
                        # Promote transport errors so callers never have to
                        # know about httpx internals.
                        raise TikTokTransientError(
                            f"transport error: {exc}", status_code=0
                        ) from exc
        except RetryError as exc:
            inner = exc.last_attempt.exception() if exc.last_attempt else None
            if isinstance(inner, TikTokAPIError):
                raise inner from exc
            raise TikTokTransientError(
                f"retries exhausted: {inner!r}",
                status_code=0,
            ) from exc
        raise RuntimeError("unreachable: _with_retries fell through")
