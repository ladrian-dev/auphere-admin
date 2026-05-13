"""Async httpx wrapper around the YCloud REST API.

Endpoints exercised in Phase 1:

- ``POST /v2/whatsapp/messages/sendDirectly`` — text, template, interactive.
- ``POST /v2/whatsapp/businessAccounts/{wabaId}/tp/bind`` — Tech Provider.
- ``POST /v2/whatsapp/businessAccounts/{wabaId}/smb/bind`` — SMB coexistence.
- ``POST /v2/whatsapp/phoneNumbers/{wabaId}/{phoneNumberId}/register``.
- ``GET  /v2/whatsapp/businessAccounts/{wabaId}`` — read after bind.
- ``GET  /v2/whatsapp/phoneNumbers/{wabaId}/{phoneNumberId}`` — read after register.

Auth header is ``X-API-Key`` (NOT Bearer). Single global key for Auphere as
the BSP customer; per-tenant key is a Phase 4+ white-label concern.

Retries: handled by the *outbound dispatcher*, not this client. The client is
a thin transport — failures bubble up so the dispatcher can decide whether
to backoff, mark failed, or escalate.
"""

from __future__ import annotations

from typing import Any

import httpx

YCLOUD_BASE_URL = "https://api.ycloud.com/v2"


class YCloudAPIError(Exception):
    """Non-2xx response from YCloud."""

    def __init__(self, status_code: int, message: str, *, body: str | None = None) -> None:
        super().__init__(f"YCloud API error {status_code}: {message}")
        self.status_code = status_code
        self.message = message
        self.body = body


class YCloudClient:
    """Thin async client. Reuse a single instance — it owns an httpx pool."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = YCLOUD_BASE_URL,
        timeout: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("ycloud api_key must be non-empty")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "X-API-Key": api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=timeout,
            transport=transport,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> YCloudClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    # ── messages ─────────────────────────────────────────────────────────────

    async def send_text(
        self,
        *,
        from_phone: str,
        to: str,
        body: str,
        context_message_id: str | None = None,
    ) -> dict[str, Any]:
        """Send a free-form text message.

        ``context_message_id`` is the wamid of an earlier message to quote
        (Cloud API ``context.message_id``). When set the recipient sees the
        text as a reply attached to the quoted bubble — useful for booking
        confirmations referencing the customer's last question.
        """
        payload: dict[str, Any] = {
            "from": from_phone,
            "to": to,
            "type": "text",
            "text": {"body": body},
        }
        if context_message_id:
            payload["context"] = {"message_id": context_message_id}
        return await self._post("/whatsapp/messages/sendDirectly", payload)

    async def send_template(
        self,
        *,
        from_phone: str,
        to: str,
        template_name: str,
        language: str,
        body_params: list[str] | dict[str, str],
        header_params: list[str] | None = None,
        button_params: list[dict[str, Any]] | None = None,
        context_message_id: str | None = None,
    ) -> dict[str, Any]:
        """Send a template message.

        ``body_params`` accepts two shapes:

        - ``list[str]`` — positional. Renders as ``[{"type": "text",
          "text": v}, ...]`` and binds in template order ({{1}}, {{2}}, ...).
          Used by the legacy ``alert_*`` and ``no_show_followup`` templates.
        - ``dict[str, str]`` — named. Each entry renders as ``{"type":
          "text", "parameter_name": k, "text": v}``. WhatsApp Cloud API
          v18+ binds by name, which is the shape YCloud's template editor
          generates by default. Used by the Auphere ↔ Owner backchannel
          templates (ADR-018).

        Mixing both is not supported — pass exactly one shape.
        """
        components: list[dict[str, Any]] = []
        if header_params:
            components.append(
                {
                    "type": "header",
                    "parameters": [{"type": "text", "text": p} for p in header_params],
                }
            )
        body_parameters: list[dict[str, Any]]
        if isinstance(body_params, dict):
            body_parameters = [
                {"type": "text", "parameter_name": k, "text": v} for k, v in body_params.items()
            ]
        else:
            body_parameters = [{"type": "text", "text": p} for p in body_params]
        components.append(
            {
                "type": "body",
                "parameters": body_parameters,
            }
        )
        if button_params:
            for idx, btn in enumerate(button_params):
                components.append(
                    {
                        "type": "button",
                        "sub_type": btn.get("sub_type", "quick_reply"),
                        "index": str(idx),
                        "parameters": btn.get("parameters", []),
                    }
                )
        payload: dict[str, Any] = {
            "from": from_phone,
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language, "policy": "deterministic"},
                "components": components,
            },
        }
        if context_message_id:
            payload["context"] = {"message_id": context_message_id}
        return await self._post("/whatsapp/messages/sendDirectly", payload)

    async def send_interactive(
        self,
        *,
        from_phone: str,
        to: str,
        interactive: dict[str, Any],
        context_message_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "from": from_phone,
            "to": to,
            "type": "interactive",
            "interactive": interactive,
        }
        if context_message_id:
            payload["context"] = {"message_id": context_message_id}
        return await self._post("/whatsapp/messages/sendDirectly", payload)

    # ── media outbound ───────────────────────────────────────────────────────
    #
    # All media sends accept the WhatsApp Cloud API contract: either a public
    # ``link`` (we host on S3 with a presigned URL or a public bucket) or a
    # ``id`` (a previously uploaded media id from POST /media). Phase 1 uses
    # ``link`` exclusively — the upload-then-id flow is a 2-call dance that
    # buys nothing when the source is already an S3 object with a presigned
    # URL valid for the send window.
    #
    # All media types accept an optional ``caption`` (image/document/video).
    # ``filename`` is documents-only. ``mime`` is rejected by Meta if it
    # disagrees with the file headers — we don't pass it; YCloud derives it.

    async def send_image(
        self,
        *,
        from_phone: str,
        to: str,
        link: str,
        caption: str | None = None,
        context_message_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "from": from_phone,
            "to": to,
            "type": "image",
            "image": _media_block(link=link, caption=caption),
        }
        if context_message_id:
            payload["context"] = {"message_id": context_message_id}
        return await self._post("/whatsapp/messages/sendDirectly", payload)

    async def send_audio(
        self,
        *,
        from_phone: str,
        to: str,
        link: str,
        context_message_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "from": from_phone,
            "to": to,
            "type": "audio",
            "audio": {"link": link},
        }
        if context_message_id:
            payload["context"] = {"message_id": context_message_id}
        return await self._post("/whatsapp/messages/sendDirectly", payload)

    async def send_video(
        self,
        *,
        from_phone: str,
        to: str,
        link: str,
        caption: str | None = None,
        context_message_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "from": from_phone,
            "to": to,
            "type": "video",
            "video": _media_block(link=link, caption=caption),
        }
        if context_message_id:
            payload["context"] = {"message_id": context_message_id}
        return await self._post("/whatsapp/messages/sendDirectly", payload)

    async def send_document(
        self,
        *,
        from_phone: str,
        to: str,
        link: str,
        filename: str | None = None,
        caption: str | None = None,
        context_message_id: str | None = None,
    ) -> dict[str, Any]:
        block: dict[str, Any] = {"link": link}
        if caption:
            block["caption"] = caption
        if filename:
            block["filename"] = filename
        payload: dict[str, Any] = {
            "from": from_phone,
            "to": to,
            "type": "document",
            "document": block,
        }
        if context_message_id:
            payload["context"] = {"message_id": context_message_id}
        return await self._post("/whatsapp/messages/sendDirectly", payload)

    async def send_location(
        self,
        *,
        from_phone: str,
        to: str,
        latitude: float,
        longitude: float,
        name: str | None = None,
        address: str | None = None,
        context_message_id: str | None = None,
    ) -> dict[str, Any]:
        block: dict[str, Any] = {"latitude": latitude, "longitude": longitude}
        if name:
            block["name"] = name
        if address:
            block["address"] = address
        payload: dict[str, Any] = {
            "from": from_phone,
            "to": to,
            "type": "location",
            "location": block,
        }
        if context_message_id:
            payload["context"] = {"message_id": context_message_id}
        return await self._post("/whatsapp/messages/sendDirectly", payload)

    async def send_contacts(
        self,
        *,
        from_phone: str,
        to: str,
        contacts: list[dict[str, Any]],
        context_message_id: str | None = None,
    ) -> dict[str, Any]:
        """Send one or more contacts. ``contacts`` follows the Cloud API
        contract verbatim: each item must have ``name.formatted_name`` and
        may carry ``phones``, ``emails``, ``addresses``, ``org``."""
        payload: dict[str, Any] = {
            "from": from_phone,
            "to": to,
            "type": "contacts",
            "contacts": contacts,
        }
        if context_message_id:
            payload["context"] = {"message_id": context_message_id}
        return await self._post("/whatsapp/messages/sendDirectly", payload)

    async def send_reaction(
        self,
        *,
        from_phone: str,
        to: str,
        target_message_id: str,
        emoji: str,
    ) -> dict[str, Any]:
        """Send a reaction emoji on a previous message.

        Pass an empty-string ``emoji`` to *remove* a previously-set reaction
        (Cloud API quirk). We don't enforce that here; callers can use it
        for the "undo my last reaction" case.
        """
        payload = {
            "from": from_phone,
            "to": to,
            "type": "reaction",
            "reaction": {"message_id": target_message_id, "emoji": emoji},
        }
        return await self._post("/whatsapp/messages/sendDirectly", payload)

    async def mark_as_read(self, *, from_phone: str, wamid: str) -> dict[str, Any]:
        """Mark an inbound message as read (the two blue checkmarks).

        Cloud API ``PUT /messages`` with ``status=read``. Polite, optional,
        and a strong UX signal that the agent is alive. We call it from the
        inbound webhook handler once the message is durably enqueued.
        """
        payload = {
            "from": from_phone,
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": wamid,
        }
        return await self._post("/whatsapp/messages/markAsRead", payload)

    # ── media inbound retrieval ──────────────────────────────────────────────

    async def get_media_url(self, media_id: str) -> dict[str, Any]:
        """Resolve a media_id (from the inbound webhook) to a download URL.

        Meta's two-step protocol: first GET /{media_id} returns
        ``{"url": "...", "mime_type": "...", "sha256": "...", "file_size": ...}``,
        then the caller GETs that URL with the BSP credentials to fetch the
        bytes. YCloud passes the same protocol through. The URL expires
        after ~5 minutes, so download must happen promptly.
        """
        return await self._get(f"/whatsapp/media/{media_id}")

    async def download_media(self, url: str) -> tuple[bytes, str | None]:
        """Fetch the raw media bytes from a URL returned by ``get_media_url``.

        Returns ``(content, content_type)``. The X-API-Key auth header is
        re-used (YCloud proxies Meta's media CDN under the same auth). On
        non-2xx raises ``YCloudAPIError`` so the caller can decide whether
        the media is salvageable or the inbound row is parked
        ``failed:media_unreachable``.
        """
        try:
            # The media URL may be absolute (Meta CDN) or YCloud-relative.
            if url.startswith("http://") or url.startswith("https://"):
                response = await self._client.get(url)
            else:
                response = await self._client.get(url)
        except httpx.HTTPError as exc:
            raise YCloudAPIError(0, f"media download transport error: {exc}") from exc
        if response.status_code >= 400:
            raise YCloudAPIError(
                response.status_code,
                f"media download {response.reason_phrase or 'http error'}",
                body=response.text[:300],
            )
        content_type = response.headers.get("content-type")
        return response.content, content_type

    # ── account / embedded signup ────────────────────────────────────────────

    async def bind_waba(self, waba_id: str, *, coexistence: bool = False) -> dict[str, Any]:
        suffix = "smb/bind" if coexistence else "tp/bind"
        return await self._post(f"/whatsapp/businessAccounts/{waba_id}/{suffix}", {})

    async def register_phone_number(self, *, waba_id: str, phone_number_id: str) -> dict[str, Any]:
        return await self._post(
            f"/whatsapp/phoneNumbers/{waba_id}/{phone_number_id}/register",
            {},
        )

    async def get_phone_number(
        self, *, waba_id: str, phone_number_id: str | None = None
    ) -> dict[str, Any]:
        """Read the WABA phone number metadata.

        YCloud accepts two forms here:

        - ``/v2/whatsapp/phoneNumbers/{wabaId}/{phoneNumberId}`` — the Meta
          GraphAPI form, when the operator copied both IDs from their YCloud
          dashboard. ``phone_number_id`` is a *Meta-side* identifier and is
          surfaced by YCloud as a passthrough; some YCloud workspaces don't
          expose it on the surface UI.
        - ``/v2/whatsapp/phoneNumbers/{wabaId}`` — list endpoint that returns
          all phones registered under the WABA. Used when ``phone_number_id``
          is unknown: we pick the only phone or 4xx if the WABA has more
          than one. This is the path the restaurant-ai project uses because
          phone_number_id isn't reliably surfaced by YCloud's UI for SMB
          customers.

        Returns the same camelCase shape (``phoneNumber``, ``displayName``,
        ``verifiedName``, ``qualityRating``) regardless of which form we
        hit; the ``id`` (or ``phoneNumberId``) field is preserved from the
        upstream response so the caller can persist it if it came back.
        """
        if phone_number_id:
            return await self._get(f"/whatsapp/phoneNumbers/{waba_id}/{phone_number_id}")
        # List form — YCloud returns ``{"data": [{...phone1...}, ...]}``
        # (envelope) or ``[{...}, ...]`` (flat). The wrapper normalises
        # flat → ``{"data": ...}``.
        listing = await self._get(f"/whatsapp/phoneNumbers/{waba_id}")
        items = listing.get("data") if isinstance(listing.get("data"), list) else None
        if items is None:
            items = listing.get("items") if isinstance(listing.get("items"), list) else None
        if not items:
            raise YCloudAPIError(
                404,
                "no phone numbers registered under this WABA",
                body=str(listing)[:300],
            )
        if len(items) > 1:
            raise YCloudAPIError(
                400,
                "multiple phone numbers registered under this WABA; "
                "specify phone_number_id explicitly",
                body=f"count={len(items)}",
            )
        single = items[0]
        if not isinstance(single, dict):
            raise YCloudAPIError(500, "malformed YCloud listing payload")
        return single

    async def get_waba(self, waba_id: str) -> dict[str, Any]:
        return await self._get(f"/whatsapp/businessAccounts/{waba_id}")

    # ── transport ────────────────────────────────────────────────────────────

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._client.post(path, json=payload)
        except httpx.HTTPError as exc:
            raise YCloudAPIError(0, f"transport error: {exc}") from exc
        return self._parse(response)

    async def _get(self, path: str) -> dict[str, Any]:
        try:
            response = await self._client.get(path)
        except httpx.HTTPError as exc:
            raise YCloudAPIError(0, f"transport error: {exc}") from exc
        return self._parse(response)

    @staticmethod
    def _parse(response: httpx.Response) -> dict[str, Any]:
        if response.status_code >= 400:
            text = response.text[:500]
            raise YCloudAPIError(
                response.status_code,
                f"{response.reason_phrase or 'http error'}",
                body=text,
            )
        if not response.content:
            return {}
        try:
            data: Any = response.json()
        except ValueError as exc:
            raise YCloudAPIError(
                response.status_code, f"non-JSON response: {response.text[:300]}"
            ) from exc
        if not isinstance(data, dict):
            return {"data": data}
        return data


def _media_block(*, link: str, caption: str | None) -> dict[str, Any]:
    block: dict[str, Any] = {"link": link}
    if caption:
        block["caption"] = caption
    return block
