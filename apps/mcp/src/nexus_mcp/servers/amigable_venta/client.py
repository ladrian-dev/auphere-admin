"""Amigable Venta REST client — thin wrapper over the shared HTTP base.

Amigable Venta (https://venta-api.amigable.app/api/v1) is the POS platform
that owns the product catalogue and stock the inventory agent reports on.

Auth is a single header (no httpx.Auth object). The API accepts either
form; we send the Bearer one:

    Authorization: Bearer amk_<key>        # (X-Api-Key is equivalent)

Per-tenant: each tenant's connector carries its own API key, which is what
scopes the response to that business — there is no business id to pass.

Response envelope (GET /public/products?q=…):

    {
      "success": true,
      "query": "acetaminofen",
      "data": [ {product…}, … ],
      "total": N            # absent on some responses; len(data) is the truth
    }

Known limits of the public surface, verified against the live API on
2026-08-24 — the tools are shaped around them, not around what we wish
existed:

- ``q`` is REQUIRED (422 otherwise) and matches ``nombre`` and ``sku``
  only. It does NOT match ``categoria`` nor ``tipo``.
- Matching is case- and accent-insensitive, and substring-based.
- There is no pagination and no per-page control: one call returns the
  whole match set, hard-capped at ``RESULT_CAP`` rows.
- There is no product-by-id endpoint (``/public/products/7`` is 405) and
  no categories endpoint (404).
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from nexus_mcp.http import BaseHTTPConnectorClient
from nexus_mcp.servers.amigable_venta.errors import (
    AmigableVentaAuthError,
    AmigableVentaNotFound,
    AmigableVentaRateLimited,
    AmigableVentaUnavailable,
    AmigableVentaValidationError,
)

log = structlog.get_logger(__name__)

DEFAULT_BASE_URL = "https://venta-api.amigable.app/api/v1"

# The API returns at most this many rows for a single query and gives no
# way to page past it. When a search hits exactly this number we cannot
# know what was dropped, so every tool reports ``truncado=True`` instead
# of implying the list is complete.
RESULT_CAP = 1000


class AmigableVentaClient(BaseHTTPConnectorClient):
    """REST client scoped to one tenant's Amigable Venta catalogue."""

    def __init__(
        self,
        *,
        token: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout_s: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        if not token:
            msg = "token is required"
            raise ValueError(msg)
        super().__init__(base_url=base_url, timeout_s=timeout_s, max_retries=max_retries)
        self._token = token

    # ── overrides ────────────────────────────────────────────────────────

    def _default_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "User-Agent": self.user_agent,
            "Authorization": f"Bearer {self._token}",
        }

    def _extract_error_message(self, response: httpx.Response) -> str:
        """Amigable Venta returns ``{"success": false, "message": …,
        "code": …}``."""
        try:
            body = response.json()
            if isinstance(body, dict):
                msg = body.get("message")
                code = body.get("code")
                parts = [p for p in (msg, f"code={code}" if code else None) if p]
                if parts:
                    return " ".join(str(p) for p in parts)
        except (ValueError, UnicodeDecodeError):
            pass
        return response.text[:300] or f"HTTP {response.status_code}"

    def _raise_for_status(self, response: httpx.Response) -> None:
        status = response.status_code
        message = self._extract_error_message(response)
        if status in (401, 403):
            raise AmigableVentaAuthError(message, status_code=status)
        if status == 404:
            raise AmigableVentaNotFound(message, status_code=status)
        if status == 429:
            raise AmigableVentaRateLimited(message, status_code=status)
        if 400 <= status < 500:
            raise AmigableVentaValidationError(message, status_code=status)
        raise AmigableVentaUnavailable(message, status_code=status)

    # ── high-level helpers used by tools ─────────────────────────────────

    async def search_products(self, query: str) -> tuple[list[dict[str, Any]], bool]:
        """Search the catalogue by product name or SKU.

        Returns ``(rows, truncated)``. ``truncated`` is True when the
        response came back at :data:`RESULT_CAP`, meaning the real match
        set is at least that large and the caller must not present the
        list as exhaustive.
        """
        term = (query or "").strip()
        if not term:
            # The API answers 422 for this; failing here saves a round trip
            # and gives the tool a message worth showing.
            raise AmigableVentaValidationError(
                'el parametro "q" es obligatorio para buscar productos'
            )
        _response, body = await self.get("/public/products", params={"q": term})
        if not isinstance(body, dict):
            raise AmigableVentaValidationError(
                f"expected JSON object from /public/products, got {type(body).__name__}"
            )
        rows: list[dict[str, Any]] = [r for r in (body.get("data") or []) if isinstance(r, dict)]
        return rows, len(rows) >= RESULT_CAP
