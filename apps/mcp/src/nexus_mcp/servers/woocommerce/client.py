"""WooCommerce REST API v3 client — thin wrapper over the shared base.

Why a per-call client (not a process-wide pool):

- Credentials are per-tenant. A pooled client keyed by tenant
  ID would need an eviction policy and a way to invalidate when the
  operator rotates the Consumer Secret. None of that is worth it for
  the latency we save (~50ms reconnect cost).
- ``httpx.AsyncClient`` is constructed inside the base's ``request``
  call, so each call already opens and closes a fresh connection.
  Keep-alive within a single call is fine.

Error mapping mirrors the base class but reraises as
``WooCommerce*Error`` so callers depending on the WooCommerce flavour
don't catch unrelated errors from other connectors.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from nexus_mcp.http import BaseHTTPConnectorClient, PaginationMeta
from nexus_mcp.servers.woocommerce.errors import (
    WooCommerceAuthError,
    WooCommerceNotFound,
    WooCommerceRateLimited,
    WooCommerceUnavailable,
    WooCommerceValidationError,
)

log = structlog.get_logger(__name__)


class WooCommerceClient(BaseHTTPConnectorClient):
    """REST client for one tenant's WooCommerce store.

    Construct with the store URL and the tenant's Consumer Key /
    Secret. All methods are thin wrappers over the shared base.

    Vendor specifics:

    - Pagination uses the WP family headers ``X-WP-Total`` /
      ``X-WP-TotalPages`` instead of the base's defaults.
    - Errors are remapped to ``WooCommerce*Error`` subclasses.
    - The store URL is normalised to strip a trailing slash before
      we append ``/wp-json/wc/v3``.
    """

    API_PREFIX = "/wp-json/wc/v3"

    def __init__(
        self,
        *,
        store_url: str,
        consumer_key: str,
        consumer_secret: str,
        timeout_s: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        if not consumer_key or not consumer_secret:
            msg = "consumer_key and consumer_secret are required"
            raise ValueError(msg)
        base = f"{store_url.rstrip('/')}{self.API_PREFIX}"
        super().__init__(
            base_url=base,
            timeout_s=timeout_s,
            max_retries=max_retries,
        )
        self._consumer_key = consumer_key
        self._consumer_secret = consumer_secret

    # ── overrides ────────────────────────────────────────────────────────

    def _auth(self) -> httpx.Auth:
        # Basic Auth over HTTPS — the base already refuses http:// in
        # the constructor, so we can be confident the secret won't be
        # sent in plaintext.
        return httpx.BasicAuth(self._consumer_key, self._consumer_secret)

    def _pagination_from_response(
        self, response: httpx.Response, *, page: int, per_page: int
    ) -> PaginationMeta:
        total_count_raw = response.headers.get("X-WP-Total")
        total_pages_raw = response.headers.get("X-WP-TotalPages")
        total_count = int(total_count_raw) if total_count_raw else None
        total_pages = int(total_pages_raw) if total_pages_raw else None
        has_more = bool(total_pages and page < total_pages)
        return PaginationMeta(
            page=page,
            per_page=per_page,
            total_count=total_count,
            total_pages=total_pages,
            has_more=has_more,
        )

    def _extract_error_message(self, response: httpx.Response) -> str:
        """WooCommerce returns ``{"code": "...", "message": "...", "data": {...}}``."""
        try:
            body = response.json()
            if isinstance(body, dict):
                msg = body.get("message")
                if isinstance(msg, str) and msg:
                    code = body.get("code")
                    return f"{msg} (code={code})" if code else msg
        except (ValueError, UnicodeDecodeError):
            pass
        return response.text[:300] or f"HTTP {response.status_code}"

    def _raise_for_status(self, response: httpx.Response) -> None:
        """Remap to WooCommerce*Error subclasses."""
        status = response.status_code
        message = self._extract_error_message(response)
        if status in (401, 403):
            raise WooCommerceAuthError(message, status_code=status)
        if status == 404:
            raise WooCommerceNotFound(message, status_code=status)
        if status == 429:
            raise WooCommerceRateLimited(message, status_code=status)
        if 400 <= status < 500:
            raise WooCommerceValidationError(message, status_code=status)
        raise WooCommerceUnavailable(message, status_code=status)

    # ── high-level helpers used by tools ─────────────────────────────────

    async def list_paginated(
        self,
        path: str,
        *,
        page: int,
        per_page: int,
        extra_params: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], PaginationMeta]:
        """GET a paginated list endpoint and return ``(items, meta)``.

        ``path`` is relative to ``/wp-json/wc/v3``.
        """
        params: dict[str, Any] = {"page": page, "per_page": per_page}
        if extra_params:
            # Filter None to avoid sending empty query params Woo
            # interprets as "any" with surprising semantics.
            params.update({k: v for k, v in extra_params.items() if v is not None})
        response, body = await self.get(path, params=params)
        if not isinstance(body, list):
            # WooCommerce list endpoints always return a JSON array on
            # success. A dict here usually means an error envelope —
            # but _raise_for_status would have fired already on non-2xx.
            # Treat as empty + log to flag the schema drift.
            log.warning(
                "woocommerce.list_response_not_array",
                path=path,
                got_type=type(body).__name__,
            )
            items: list[dict[str, Any]] = []
        else:
            items = [item for item in body if isinstance(item, dict)]
        meta = self._pagination_from_response(
            response, page=page, per_page=per_page
        )
        return items, meta

    async def get_resource(
        self, path: str, *, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """GET a single-resource endpoint. Raises ``WooCommerceNotFound``
        on 404, ``WooCommerceValidationError`` if the body is not a JSON
        object."""
        _response, body = await self.get(path, params=params)
        if not isinstance(body, dict):
            raise WooCommerceValidationError(
                f"expected JSON object from {path}, got {type(body).__name__}"
            )
        return body

    async def post_resource(
        self,
        path: str,
        *,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """POST and return the created resource as a dict."""
        _response, body = await self.post(path, json=payload)
        if not isinstance(body, dict):
            raise WooCommerceValidationError(
                f"expected JSON object from POST {path}, got {type(body).__name__}"
            )
        return body

    async def put_resource(
        self,
        path: str,
        *,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """PUT and return the updated resource as a dict."""
        _response, body = await self.put(path, json=payload)
        if not isinstance(body, dict):
            raise WooCommerceValidationError(
                f"expected JSON object from PUT {path}, got {type(body).__name__}"
            )
        return body


__all__ = ["WooCommerceClient"]
