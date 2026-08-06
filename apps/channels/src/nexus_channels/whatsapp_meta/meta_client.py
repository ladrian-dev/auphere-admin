"""Async ``httpx`` wrapper around the Meta Graph API for WhatsApp Cloud API.

Endpoints exercised in Phase 1 (Embedded Signup + steady-state messaging):

- ``POST /{phone_number_id}/messages`` — text, template, interactive, media.
- ``POST /{phone_number_id}/register`` — re-register a number under the
  Auphere Tech Provider after Embedded Signup.
- ``POST /{waba_id}/subscribed_apps`` — subscribe the app to a WABA's
  webhooks, optionally overriding the callback URL per-tenant.
- ``DELETE /{waba_id}/subscribed_apps`` — unsubscribe on tenant offboarding.
- ``GET /{phone_number_id}`` — display name, quality rating, messaging tier.
- ``GET /{waba_id}/message_templates`` — list templates.
- ``POST /{waba_id}/message_templates`` — create a template.
- ``DELETE /{waba_id}/message_templates`` — delete by name.
- ``GET /{media_id}`` — resolve media id to a (short-lived) download URL.
- ``GET <signed_url>`` — download media bytes; the URL is the one returned
  from the previous step. Auth header is required even on the CDN URL.
- ``GET /oauth/access_token`` — exchange OAuth code for a BISUAT.
- ``GET /debug_token`` — introspect a BISUAT (scopes, expiry).

Auth model:

- Every call (except token exchange) takes ``access_token`` as a kwarg.
  No token is held internally — the BISUAT lives in
  ``tenant_credentials.encrypted_payload`` and is resolved per request by
  the caller. The token-exchange call uses ``client_secret`` instead.
- When ``require_appsecret_proof=True`` (the default; matches the app
  setting since 2026-05-21), the client appends
  ``appsecret_proof = HMAC_SHA256(token, app_secret)`` to every
  authenticated request.

Retry policy:

- Lives inside the client (vs adapters where retries could live in the
  outbound dispatcher). Reason: the dispatcher is only the outbound path;
  webhook handlers, signup orchestrator, and background jobs all use
  ``MetaClient`` too, and they need a uniform retry policy without
  duplicating tenacity decorators on every callsite. Retries:

  * HTTP 5xx, 429, ``ConnectError``, ``ReadTimeout`` → up to 3 attempts
    with exponential backoff (0.5s, 1s, 2s).
  * 4xx (other than 429), ``OAuthException`` 190 → no retry; surface
    immediately.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any, Final, cast

import httpx
import structlog
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from nexus_channels.whatsapp_meta.exceptions import (
    MetaAPIError,
    MetaRateLimitedError,
    MetaTransientError,
    TokenExchangeError,
    TokenInvalidatedError,
)
from nexus_channels.whatsapp_meta.signature import appsecret_proof

META_GRAPH_VERSION: Final = "v22.0"
META_GRAPH_BASE_URL: Final = f"https://graph.facebook.com/{META_GRAPH_VERSION}"

# OAuthException subcodes / codes that mean "user must re-authenticate".
# https://developers.facebook.com/docs/graph-api/guides/error-handling/
_TOKEN_INVALIDATED_CODES: Final = frozenset({102, 190, 463, 467})

# Code 4: Application request limit reached.
# Code 80004: Throttled — too many calls.
_RATE_LIMIT_CODES: Final = frozenset({4, 80004})

log = structlog.get_logger(__name__)


class MetaClient:
    """Thin async client. Reuse one instance per worker process — it owns
    an ``httpx`` connection pool. Construct with :func:`build_meta_client`
    when wiring from FastAPI dependencies so settings come from the
    central config rather than the call site.
    """

    def __init__(
        self,
        app_secret: str,
        *,
        require_appsecret_proof: bool = True,
        max_retries: int = 3,
        timeout: float = 15.0,
        base_url: str = META_GRAPH_BASE_URL,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not app_secret:
            raise ValueError("MetaClient.app_secret must be non-empty")
        self._app_secret = app_secret
        self._require_appsecret_proof = require_appsecret_proof
        self._max_retries = max_retries
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            transport=transport,
            headers={
                "Accept": "application/json",
                "User-Agent": "auphere-nexus-meta/0.1",
            },
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> MetaClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    # ── messages ───────────────────────────────────────────────────────────

    async def send_text(
        self,
        *,
        phone_number_id: str,
        access_token: str,
        to: str,
        body: str,
        context_message_id: str | None = None,
        preview_url: bool = False,
    ) -> dict[str, Any]:
        """Send a text message. Cloud API contract — see
        https://developers.facebook.com/docs/whatsapp/cloud-api/reference/messages
        """
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"body": body, "preview_url": preview_url},
        }
        if context_message_id:
            payload["context"] = {"message_id": context_message_id}
        return await self._post(
            f"/{phone_number_id}/messages",
            access_token=access_token,
            json_body=payload,
        )

    async def send_template(
        self,
        *,
        phone_number_id: str,
        access_token: str,
        to: str,
        template_name: str,
        language: str,
        components: list[dict[str, Any]] | None = None,
        context_message_id: str | None = None,
    ) -> dict[str, Any]:
        """Send a template message.

        ``components`` is the Cloud API native shape — list of dicts each
        with ``type`` in ``{"header","body","footer","button"}`` and a
        ``parameters`` array. The adapter layer builds these from the YAML
        templates registered on the WABA.
        """
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language, "policy": "deterministic"},
                "components": components or [],
            },
        }
        if context_message_id:
            payload["context"] = {"message_id": context_message_id}
        return await self._post(
            f"/{phone_number_id}/messages",
            access_token=access_token,
            json_body=payload,
        )

    async def send_interactive(
        self,
        *,
        phone_number_id: str,
        access_token: str,
        to: str,
        interactive: dict[str, Any],
        context_message_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": interactive,
        }
        if context_message_id:
            payload["context"] = {"message_id": context_message_id}
        return await self._post(
            f"/{phone_number_id}/messages",
            access_token=access_token,
            json_body=payload,
        )

    async def send_media(
        self,
        *,
        phone_number_id: str,
        access_token: str,
        to: str,
        media_type: str,
        link: str,
        caption: str | None = None,
        filename: str | None = None,
        context_message_id: str | None = None,
    ) -> dict[str, Any]:
        """Send image/video/audio/document/sticker via a public ``link``.

        Meta fetches the URL synchronously — keep TTL > the few seconds it
        takes them to download. Presigned S3 URLs valid for 5 minutes are
        ample.
        """
        if media_type not in {"image", "video", "audio", "document", "sticker"}:
            raise ValueError(f"unsupported media type: {media_type!r}")
        media: dict[str, Any] = {"link": link}
        if caption and media_type in {"image", "video", "document"}:
            media["caption"] = caption
        if filename and media_type == "document":
            media["filename"] = filename
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": media_type,
            media_type: media,
        }
        if context_message_id:
            payload["context"] = {"message_id": context_message_id}
        return await self._post(
            f"/{phone_number_id}/messages",
            access_token=access_token,
            json_body=payload,
        )

    async def send_reaction(
        self,
        *,
        phone_number_id: str,
        access_token: str,
        to: str,
        target_message_id: str,
        emoji: str,
    ) -> dict[str, Any]:
        """Set or remove a reaction. Empty ``emoji`` removes a previous one."""
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "reaction",
            "reaction": {"message_id": target_message_id, "emoji": emoji},
        }
        return await self._post(
            f"/{phone_number_id}/messages",
            access_token=access_token,
            json_body=payload,
        )

    async def mark_as_read(
        self,
        *,
        phone_number_id: str,
        access_token: str,
        message_id: str,
    ) -> dict[str, Any]:
        return await self._post(
            f"/{phone_number_id}/messages",
            access_token=access_token,
            json_body={"messaging_product": "whatsapp", "status": "read", "message_id": message_id},
        )

    # ── media inbound ──────────────────────────────────────────────────────

    async def get_media_url(
        self,
        *,
        media_id: str,
        access_token: str,
    ) -> dict[str, Any]:
        """Resolve a ``media_id`` to ``{url, mime_type, sha256, file_size}``.

        The returned ``url`` is short-lived (~5 min). Authenticated GET to
        the URL returns the bytes — use :meth:`download_media`.
        """
        return await self._get(f"/{media_id}", access_token=access_token)

    async def download_media(
        self,
        *,
        url: str,
        access_token: str,
    ) -> tuple[bytes, str | None]:
        """Fetch the media bytes. The CDN URL still requires the BISUAT.

        Returns ``(content, content_type)``. Use :meth:`get_media_url` to
        obtain the URL first.
        """
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            response = await self._client.get(url, headers=headers)
        except (httpx.ConnectError, httpx.ReadTimeout) as exc:
            raise MetaTransientError(str(exc), status_code=0, body=None) from exc
        if response.status_code >= 400:
            raise MetaAPIError(
                f"media download failed: {response.text[:200]}",
                status_code=response.status_code,
                body=response.text,
            )
        return response.content, response.headers.get("content-type")

    # ── phone numbers ──────────────────────────────────────────────────────

    async def register_phone(
        self,
        *,
        phone_number_id: str,
        access_token: str,
        pin: str,
    ) -> dict[str, Any]:
        """Re-register a phone number under our app after Embedded Signup.

        Must run before the WABA can send/receive messages through us.
        Idempotent — Meta returns 200 if the number is already registered
        under the same app with the same PIN.
        """
        return await self._post(
            f"/{phone_number_id}/register",
            access_token=access_token,
            json_body={"messaging_product": "whatsapp", "pin": pin},
        )

    async def get_phone_number(
        self,
        *,
        phone_number_id: str,
        access_token: str,
        fields: str = (
            "display_phone_number,verified_name,quality_rating,"
            "messaging_limit_tier,name_status,code_verification_status"
        ),
    ) -> dict[str, Any]:
        return await self._get(
            f"/{phone_number_id}",
            access_token=access_token,
            params={"fields": fields},
        )

    async def list_phone_numbers(
        self,
        *,
        waba_id: str,
        access_token: str,
        fields: str = ("id,display_phone_number,verified_name,quality_rating,messaging_limit_tier"),
    ) -> dict[str, Any]:
        """``GET /{waba_id}/phone_numbers``.

        Returns ``{"data": [{"id": ..., "display_phone_number": ...}, ...]}``.
        Used by the Coexistence branch of the signup orchestrator: the
        ``FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING`` postMessage event only
        carries ``waba_id``, so the phone number id must be discovered
        before the channel row can be written.
        """
        return await self._get(
            f"/{waba_id}/phone_numbers",
            access_token=access_token,
            params={"fields": fields},
        )

    # ── subscribed apps (webhook) ──────────────────────────────────────────

    async def subscribe_app(
        self,
        *,
        waba_id: str,
        access_token: str,
        override_callback_uri: str | None = None,
        verify_token: str | None = None,
    ) -> dict[str, Any]:
        """``POST /{waba_id}/subscribed_apps``.

        When ``override_callback_uri`` is set, this WABA emits webhooks to
        that URL instead of the app-level default. Auphere uses this to
        route per-environment (dev/staging/prod) without juggling the
        app-level config. ``verify_token`` is the secret Meta echoes back
        on the GET handshake — generate one per-tenant and persist it
        alongside the BISUAT.
        """
        body: dict[str, Any] = {}
        if override_callback_uri is not None:
            body["override_callback_uri"] = override_callback_uri
        if verify_token is not None:
            body["verify_token"] = verify_token
        return await self._post(
            f"/{waba_id}/subscribed_apps",
            access_token=access_token,
            json_body=body or None,
        )

    async def unsubscribe_app(
        self,
        *,
        waba_id: str,
        access_token: str,
    ) -> dict[str, Any]:
        return await self._delete(
            f"/{waba_id}/subscribed_apps",
            access_token=access_token,
        )

    async def list_subscribed_apps(
        self,
        *,
        waba_id: str,
        access_token: str,
    ) -> dict[str, Any]:
        return await self._get(
            f"/{waba_id}/subscribed_apps",
            access_token=access_token,
        )

    # ── templates ──────────────────────────────────────────────────────────

    async def list_templates(
        self,
        *,
        waba_id: str,
        access_token: str,
        limit: int = 100,
    ) -> dict[str, Any]:
        return await self._get(
            f"/{waba_id}/message_templates",
            access_token=access_token,
            params={"limit": limit},
        )

    async def create_template(
        self,
        *,
        waba_id: str,
        access_token: str,
        name: str,
        language: str,
        category: str,
        components: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return await self._post(
            f"/{waba_id}/message_templates",
            access_token=access_token,
            json_body={
                "name": name,
                "language": language,
                "category": category,
                "components": components,
            },
        )

    async def delete_template(
        self,
        *,
        waba_id: str,
        access_token: str,
        name: str,
    ) -> dict[str, Any]:
        return await self._delete(
            f"/{waba_id}/message_templates",
            access_token=access_token,
            params={"name": name},
        )

    # ── OAuth / tokens ─────────────────────────────────────────────────────

    async def exchange_code(
        self,
        *,
        app_id: str,
        code: str,
        redirect_uri: str | None = None,
    ) -> dict[str, Any]:
        """Exchange an OAuth ``code`` (from Embedded Signup) for a BISUAT.

        Uses the App Secret (held by :attr:`_app_secret`) — does NOT use a
        BISUAT, so ``appsecret_proof`` is irrelevant here.
        """
        params: dict[str, Any] = {
            "client_id": app_id,
            "client_secret": self._app_secret,
            "code": code,
        }
        if redirect_uri:
            params["redirect_uri"] = redirect_uri
        try:
            response = await self._client.get("/oauth/access_token", params=params)
        except (httpx.ConnectError, httpx.ReadTimeout) as exc:
            raise TokenExchangeError(f"transport error: {exc}") from exc
        if response.status_code >= 400:
            raise TokenExchangeError(
                f"code exchange failed ({response.status_code}): {response.text[:200]}"
            )
        return cast(dict[str, Any], response.json())

    async def debug_token(
        self,
        *,
        input_token: str,
        admin_access_token: str,
    ) -> dict[str, Any]:
        """``GET /debug_token`` — inspect scopes, expiry, app_id.

        Note: ``admin_access_token`` is an app or system-user token (NOT
        the token being inspected). For Auphere we pass the system-user
        token of the Tech Provider system user.
        """
        return await self._get(
            "/debug_token",
            access_token=admin_access_token,
            params={"input_token": input_token},
        )

    # ── HTTP primitives ────────────────────────────────────────────────────

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
                params=self._with_auth(params or {}, access_token),
            )
            return self._handle_response(resp)

        return await self._with_retries(attempt)

    async def _post(
        self,
        path: str,
        *,
        access_token: str,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        async def attempt() -> dict[str, Any]:
            resp = await self._client.post(
                path,
                params=self._with_auth(params or {}, access_token),
                json=json_body,
            )
            return self._handle_response(resp)

        return await self._with_retries(attempt)

    async def _delete(
        self,
        path: str,
        *,
        access_token: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        async def attempt() -> dict[str, Any]:
            resp = await self._client.delete(
                path,
                params=self._with_auth(params or {}, access_token),
            )
            return self._handle_response(resp)

        return await self._with_retries(attempt)

    def _with_auth(
        self,
        params: dict[str, Any],
        access_token: str,
    ) -> dict[str, Any]:
        params = dict(params)
        params["access_token"] = access_token
        if self._require_appsecret_proof:
            params["appsecret_proof"] = appsecret_proof(access_token, self._app_secret)
        return params

    def _handle_response(self, response: httpx.Response) -> dict[str, Any]:
        if response.status_code < 400:
            if not response.content:
                return {}
            try:
                return cast(dict[str, Any], response.json())
            except json.JSONDecodeError:
                return {"raw": response.text}
        # Error branch — try to parse Graph API error envelope.
        body_text = response.text
        err: dict[str, Any] = {}
        try:
            envelope = response.json()
            if isinstance(envelope, dict):
                maybe_err = envelope.get("error", envelope)
                if isinstance(maybe_err, dict):
                    err = maybe_err
        except json.JSONDecodeError:
            pass
        code_raw = err.get("code")
        code: int | None = code_raw if isinstance(code_raw, int) else None
        subcode_raw = err.get("error_subcode")
        subcode: int | None = subcode_raw if isinstance(subcode_raw, int) else None
        fbtrace_raw = err.get("fbtrace_id")
        fbtrace: str | None = fbtrace_raw if isinstance(fbtrace_raw, str) else None
        message_raw = err.get("message")
        message: str = (
            message_raw if isinstance(message_raw, str) else f"HTTP {response.status_code}"
        )
        if code is not None and code in _TOKEN_INVALIDATED_CODES:
            raise TokenInvalidatedError(
                message,
                status_code=response.status_code,
                code=code,
                subcode=subcode,
                fbtrace_id=fbtrace,
                body=body_text,
            )
        if response.status_code == 429 or (code is not None and code in _RATE_LIMIT_CODES):
            raise MetaRateLimitedError(
                message,
                status_code=response.status_code,
                code=code,
                subcode=subcode,
                fbtrace_id=fbtrace,
                body=body_text,
            )
        if response.status_code >= 500:
            raise MetaTransientError(
                message,
                status_code=response.status_code,
                code=code,
                subcode=subcode,
                fbtrace_id=fbtrace,
                body=body_text,
            )
        raise MetaAPIError(
            message,
            status_code=response.status_code,
            code=code,
            subcode=subcode,
            fbtrace_id=fbtrace,
            body=body_text,
        )

    async def _with_retries(
        self,
        attempt: Callable[[], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        # Tenacity wraps the awaitable; non-retriable exceptions (the bulk
        # of 4xx and TokenInvalidatedError) escape immediately.
        #
        # ``httpx.TransportError`` — NOT the two leaf classes it is tempting
        # to list — is the base of every failure that happens before a
        # response exists: connect/read/write/pool timeouts, connection and
        # protocol errors. Naming leaves instead let ``PoolTimeout`` and
        # ``ConnectTimeout`` escape raw, and a raw httpx error is not a
        # ``MetaAPIError``, so every caller that maps Meta failures to a
        # clean 4xx/502 missed it and FastAPI turned it into a 500. That is
        # exactly what broke the New Air campaign: a burst of template
        # lookups exhausted the pool and the 500 aborted the whole run.
        try:
            async for retry_state in AsyncRetrying(
                stop=stop_after_attempt(self._max_retries),
                wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
                retry=retry_if_exception_type(
                    (
                        MetaTransientError,
                        MetaRateLimitedError,
                        httpx.TransportError,
                    )
                ),
                reraise=True,
            ):
                with retry_state:
                    try:
                        return await attempt()
                    except httpx.TransportError as exc:
                        # Promote transport errors to MetaTransientError so
                        # callers don't have to know about httpx internals.
                        raise MetaTransientError(
                            f"transport error: {type(exc).__name__}: {exc}",
                            status_code=0,
                        ) from exc
        except RetryError as exc:
            inner = exc.last_attempt.exception() if exc.last_attempt else None
            if isinstance(inner, MetaAPIError):
                raise inner from exc
            raise MetaTransientError(
                f"retries exhausted: {inner!r}",
                status_code=0,
            ) from exc
        # AsyncRetrying either returns inside the loop or raises; reaching
        # here is impossible but mypy needs an explicit return / raise.
        raise RuntimeError("unreachable: _with_retries fell through")
