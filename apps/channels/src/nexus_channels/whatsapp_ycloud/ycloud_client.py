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
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "from": from_phone,
            "to": to,
            "type": "text",
            "text": {"body": body},
        }
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
        payload = {
            "from": from_phone,
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language, "policy": "deterministic"},
                "components": components,
            },
        }
        return await self._post("/whatsapp/messages/sendDirectly", payload)

    async def send_interactive(
        self,
        *,
        from_phone: str,
        to: str,
        interactive: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "from": from_phone,
            "to": to,
            "type": "interactive",
            "interactive": interactive,
        }
        return await self._post("/whatsapp/messages/sendDirectly", payload)

    # ── account / embedded signup ────────────────────────────────────────────

    async def bind_waba(self, waba_id: str, *, coexistence: bool = False) -> dict[str, Any]:
        suffix = "smb/bind" if coexistence else "tp/bind"
        return await self._post(f"/whatsapp/businessAccounts/{waba_id}/{suffix}", {})

    async def register_phone_number(self, *, waba_id: str, phone_number_id: str) -> dict[str, Any]:
        return await self._post(
            f"/whatsapp/phoneNumbers/{waba_id}/{phone_number_id}/register",
            {},
        )

    async def get_phone_number(self, *, waba_id: str, phone_number_id: str) -> dict[str, Any]:
        return await self._get(f"/whatsapp/phoneNumbers/{waba_id}/{phone_number_id}")

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
