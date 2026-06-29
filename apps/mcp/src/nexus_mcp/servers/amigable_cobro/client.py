"""Amigable Cobro REST client — thin wrapper over the shared HTTP base.

Amigable Cobro (https://api-amigablecobro.amacruxlab.com/api/v1) is the
debt-management platform that owns the accounts-receivable ("cuentas y
cobros") the cobranza agent reminds about.

Auth is two headers on every call (no httpx.Auth object):

    X-Entity-ID:   <entity uuid>          # the authorised agent/entity
    Authorization: Bearer <token>

Per-tenant: each tenant's connector carries its own entity-id + token +
``business_uuid``. The client is constructed per call (cheap) with the
tenant's credentials already resolved, and ``business_uuid`` baked in so
the tools just ask for a page.

Response envelope (GET /cuentas-y-cobros):

    {
      "success": true,
      "message": "...",
      "data": {
        "data": [ {account…}, … ],
        "meta": {"total": N, "current_page": 1, "last_page": 5}
      }
    }
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from nexus_mcp.http import BaseHTTPConnectorClient
from nexus_mcp.servers.amigable_cobro.errors import (
    AmigableCobroAuthError,
    AmigableCobroNotFound,
    AmigableCobroRateLimited,
    AmigableCobroUnavailable,
    AmigableCobroValidationError,
)

log = structlog.get_logger(__name__)

DEFAULT_BASE_URL = "https://api-amigablecobro.amacruxlab.com/api/v1"


class AmigableCobroClient(BaseHTTPConnectorClient):
    """REST client scoped to one tenant's Amigable Cobro business."""

    def __init__(
        self,
        *,
        entity_id: str,
        token: str,
        business_uuid: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout_s: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        if not (entity_id and token and business_uuid):
            msg = "entity_id, token and business_uuid are required"
            raise ValueError(msg)
        super().__init__(base_url=base_url, timeout_s=timeout_s, max_retries=max_retries)
        self._entity_id = entity_id
        self._token = token
        self.business_uuid = business_uuid

    # ── overrides ────────────────────────────────────────────────────────

    def _default_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "User-Agent": self.user_agent,
            "X-Entity-ID": self._entity_id,
            "Authorization": f"Bearer {self._token}",
        }

    def _extract_error_message(self, response: httpx.Response) -> str:
        """Amigable Cobro returns ``{"success": false, "message": ...,
        "error_code": ..., "details": {...}}``."""
        try:
            body = response.json()
            if isinstance(body, dict):
                msg = body.get("message")
                code = body.get("error_code")
                details = body.get("details")
                parts = [p for p in (msg, f"code={code}" if code else None) if p]
                base = " ".join(parts) if parts else None
                if base and details:
                    return f"{base} — {details}"
                if base:
                    return base
        except (ValueError, UnicodeDecodeError):
            pass
        return response.text[:300] or f"HTTP {response.status_code}"

    def _raise_for_status(self, response: httpx.Response) -> None:
        status = response.status_code
        message = self._extract_error_message(response)
        if status in (401, 403):
            raise AmigableCobroAuthError(message, status_code=status)
        if status == 404:
            raise AmigableCobroNotFound(message, status_code=status)
        if status == 429:
            raise AmigableCobroRateLimited(message, status_code=status)
        if 400 <= status < 500:
            raise AmigableCobroValidationError(message, status_code=status)
        raise AmigableCobroUnavailable(message, status_code=status)

    # ── high-level helpers used by tools ─────────────────────────────────

    async def list_cuentas(
        self,
        *,
        page: int = 1,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """GET one page of accounts-receivable for this business.

        Returns ``(records, meta)`` where ``meta`` is
        ``{"total", "current_page", "last_page"}``. Unwraps the nested
        ``data.data`` / ``data.meta`` envelope.
        """
        params: dict[str, Any] = {"business_uuid": self.business_uuid, "page": page}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        _response, body = await self.get("/cuentas-y-cobros", params=params)
        if not isinstance(body, dict):
            raise AmigableCobroValidationError(
                f"expected JSON object from /cuentas-y-cobros, got {type(body).__name__}"
            )
        inner = body.get("data")
        if not isinstance(inner, dict):
            # Some deployments may return data as a bare list; tolerate it.
            bare: list[dict[str, Any]] = [r for r in (inner or []) if isinstance(r, dict)]
            return bare, {"total": len(bare), "current_page": page, "last_page": page}
        records: list[dict[str, Any]] = [
            r for r in (inner.get("data") or []) if isinstance(r, dict)
        ]
        meta_raw = inner.get("meta")
        meta: dict[str, Any] = meta_raw if isinstance(meta_raw, dict) else {}
        return records, meta


__all__ = ["DEFAULT_BASE_URL", "AmigableCobroClient"]
