"""``BaseHTTPConnectorClient`` — shared scaffolding for REST-API connectors.

Every ``api_key``-style connector (WooCommerce now, Shopify / Stripe / etc.
next) needs the same four pieces:

1. An ``httpx.AsyncClient`` configured with the vendor's base URL,
   timeout, retry policy, and auth.
2. A vendor-agnostic ``request()`` that re-raises HTTP errors as one of
   the typed exceptions below (the tool layer maps these to the
   ``tenant_connectors.status`` lifecycle: 401/403 → needs_reauth,
   etc.).
3. Bounded retries on transient failures only — never on 4xx, and
   never on the *result* of a destructive call (the caller decides
   idempotency on the way down).
4. Optional pagination helpers that extract ``total_count`` /
   ``has_more`` from response headers (vendor-specific subclass tells
   us the header names).

This module deliberately does NOT touch tenant context. Tools resolve
the active tenant via ``require_current_tenant`` before constructing
the client; the client itself is per-call and stateless. That keeps
the tenant boundary at the tool layer where ``ToolBase.invoke``
already asserts it.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, ClassVar

import httpx
import structlog

log = structlog.get_logger(__name__)


# ── exceptions ───────────────────────────────────────────────────────────


class HTTPConnectorError(Exception):
    """Base class. Vendor clients subclass for vendor-specific names."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class HTTPConnectorAuthError(HTTPConnectorError):
    """401 / 403 from the vendor. Tools must trip
    ``tenant_connectors.status='needs_reauth'`` so the operator panel
    surfaces it."""


class HTTPConnectorNotFound(HTTPConnectorError):
    """404 — the resource the LLM asked for does not exist. Surfaced as
    a clean result to the LLM, not a runtime failure."""


class HTTPConnectorValidationError(HTTPConnectorError):
    """4xx other than 401/403/404 — the request was rejected by the
    vendor. Usually a programming bug or LLM hallucinating field
    values; surfaced verbatim so it is visible in the conversation."""


class HTTPConnectorRateLimited(HTTPConnectorError):
    """429. The base client already honours ``Retry-After`` once before
    re-raising; this exception only fires if the limit persists past
    the bounded retry."""


class HTTPConnectorUnavailable(HTTPConnectorError):
    """5xx or transport failure after exhausting retries. Distinct from
    auth errors so the panel can show a different banner."""


# ── pagination meta ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class PaginationMeta:
    """What every paginated list endpoint reports back.

    Tools wrap this into the public ``OutputEnvelope`` so the LLM sees
    ``total_count`` + ``has_more`` and won't claim "there are 3 X"
    when there are actually 300. Page is 1-indexed (matches WP / Woo).
    """

    page: int
    per_page: int
    total_count: int | None
    total_pages: int | None
    has_more: bool


# ── base client ──────────────────────────────────────────────────────────


class BaseHTTPConnectorClient:
    """Per-call REST client. Construct, use, discard.

    Subclass and override:

    - ``_auth_for(method, url)`` — return ``httpx.Auth`` or modify
      headers. For Basic auth (WooCommerce), the subclass returns an
      ``httpx.BasicAuth``.
    - ``_pagination_from_response(response, page, per_page)`` — read
      vendor-specific headers. Default reads
      ``X-Total-Count`` / ``X-Total-Pages`` because WP family uses
      ``X-WP-Total`` / ``X-WP-TotalPages`` — Woo subclass overrides.
    - ``_map_status_to_error(status, body)`` — vendors return error
      shapes differently; subclass extracts the human message.

    Construction is intentionally cheap so tools can build one per
    invocation. If we later need keep-alive pools, that lives in a
    process-wide cache layer above this class — not inside it.
    """

    # ``base_url`` is set per-instance in ``__init__`` (each tenant has
    # a different store URL) — declared on ``self`` below, not here, so
    # mypy --strict can see the assignment unambiguously.

    # Defaults — subclasses can override or pass through ctor.
    DEFAULT_TIMEOUT_S: ClassVar[float] = 20.0
    DEFAULT_MAX_RETRIES: ClassVar[int] = 2
    DEFAULT_BACKOFF_BASE_S: ClassVar[float] = 0.5

    def __init__(
        self,
        *,
        base_url: str,
        timeout_s: float | None = None,
        max_retries: int | None = None,
        user_agent: str = "Auphere-Nexus/1.0 (+https://auphere.com)",
    ) -> None:
        if not base_url.startswith("https://"):
            # Security: refuse plaintext. WooCommerce Basic Auth over
            # http would leak Consumer Secret on the wire.
            msg = f"base_url must be https://; got {base_url!r}"
            raise ValueError(msg)
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s if timeout_s is not None else self.DEFAULT_TIMEOUT_S
        self.max_retries = max_retries if max_retries is not None else self.DEFAULT_MAX_RETRIES
        self.user_agent = user_agent

    # ── extension hooks (subclasses override) ────────────────────────────

    def _auth(self) -> httpx.Auth | None:
        """Return the auth callable for httpx. Default: no auth."""
        return None

    def _default_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "User-Agent": self.user_agent,
        }

    def _pagination_from_response(
        self, response: httpx.Response, *, page: int, per_page: int
    ) -> PaginationMeta:
        """Vendor-default. WordPress/WooCommerce uses ``X-WP-Total`` /
        ``X-WP-TotalPages``; subclass overrides accordingly."""
        total_count_raw = response.headers.get("X-Total-Count")
        total_pages_raw = response.headers.get("X-Total-Pages")
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
        """Default best-effort extractor. Subclasses tighten it."""
        try:
            body = response.json()
            if isinstance(body, dict):
                for key in ("message", "error", "detail"):
                    val = body.get(key)
                    if isinstance(val, str):
                        return val
        except (ValueError, UnicodeDecodeError):
            pass
        return response.text[:300] or f"HTTP {response.status_code}"

    # ── public surface ───────────────────────────────────────────────────

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
    ) -> tuple[httpx.Response, dict[str, Any] | list[Any] | None]:
        """Send ``method path``. Returns ``(response, parsed_body)``.

        ``parsed_body`` is the JSON-decoded body, or ``None`` if the
        response had no body or non-JSON content type. The raw
        response is also returned so paginated callers can read
        headers.

        Raises one of the typed exceptions on non-2xx.
        """
        url = self._full_url(path)
        attempt = 0
        while True:
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout_s,
                    headers=self._default_headers(),
                    auth=self._auth(),
                ) as client:
                    response = await client.request(
                        method=method,
                        url=url,
                        params=params,
                        json=json,
                    )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                # Bounded retry on transport failures only.
                if attempt < self.max_retries:
                    delay = self._backoff_delay(attempt)
                    log.warning(
                        "http_connector.transport_retry",
                        method=method,
                        url=url,
                        attempt=attempt,
                        delay_s=delay,
                        error=str(exc),
                    )
                    await asyncio.sleep(delay)
                    attempt += 1
                    continue
                raise HTTPConnectorUnavailable(
                    f"transport failed after {attempt} retries: {exc}"
                ) from exc

            # 2xx — success.
            if 200 <= response.status_code < 300:
                return response, self._safe_json(response)

            # 429 — one shot at Retry-After, then re-raise.
            if response.status_code == 429 and attempt < self.max_retries:
                retry_after = self._parse_retry_after(response.headers.get("Retry-After"))
                delay = retry_after or self._backoff_delay(attempt)
                log.warning(
                    "http_connector.rate_limited",
                    method=method,
                    url=url,
                    attempt=attempt,
                    delay_s=delay,
                )
                await asyncio.sleep(delay)
                attempt += 1
                continue

            # 5xx — retry transient server errors, but not 501/505 etc.
            if response.status_code in {500, 502, 503, 504} and attempt < self.max_retries:
                delay = self._backoff_delay(attempt)
                log.warning(
                    "http_connector.5xx_retry",
                    method=method,
                    url=url,
                    status=response.status_code,
                    attempt=attempt,
                    delay_s=delay,
                )
                await asyncio.sleep(delay)
                attempt += 1
                continue

            # Exhausted retries (or non-retryable 4xx) — raise.
            self._raise_for_status(response)

    async def get(
        self, path: str, *, params: dict[str, Any] | None = None
    ) -> tuple[httpx.Response, dict[str, Any] | list[Any] | None]:
        return await self.request("GET", path, params=params)

    async def post(
        self,
        path: str,
        *,
        json: Any | None = None,
        params: dict[str, Any] | None = None,
    ) -> tuple[httpx.Response, dict[str, Any] | list[Any] | None]:
        return await self.request("POST", path, params=params, json=json)

    async def put(
        self,
        path: str,
        *,
        json: Any | None = None,
        params: dict[str, Any] | None = None,
    ) -> tuple[httpx.Response, dict[str, Any] | list[Any] | None]:
        return await self.request("PUT", path, params=params, json=json)

    async def delete(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> tuple[httpx.Response, dict[str, Any] | list[Any] | None]:
        return await self.request("DELETE", path, params=params)

    # ── internals ────────────────────────────────────────────────────────

    def _full_url(self, path: str) -> str:
        if path.startswith("https://"):
            return path
        return f"{self.base_url}/{path.lstrip('/')}"

    def _backoff_delay(self, attempt: int) -> float:
        # Exponential, no jitter (intentional: tests deterministic).
        return float(self.DEFAULT_BACKOFF_BASE_S * (2**attempt))

    @staticmethod
    def _parse_retry_after(raw: str | None) -> float | None:
        if not raw:
            return None
        try:
            # WooCommerce / WP return seconds as integer string.
            value = float(raw)
            # Clamp to avoid sleeping forever on a hostile / buggy
            # response. 30s is the cap; beyond that we re-raise.
            if value < 0 or value > 30:
                return None
            return value
        except ValueError:
            return None

    @staticmethod
    def _safe_json(response: httpx.Response) -> dict[str, Any] | list[Any] | None:
        ctype = response.headers.get("content-type", "")
        if "application/json" not in ctype:
            return None
        if not response.content:
            return None
        try:
            parsed = response.json()
        except ValueError:
            return None
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list):
            return parsed
        return None

    def _raise_for_status(self, response: httpx.Response) -> None:
        status = response.status_code
        message = self._extract_error_message(response)
        if status in (401, 403):
            raise HTTPConnectorAuthError(message, status_code=status)
        if status == 404:
            raise HTTPConnectorNotFound(message, status_code=status)
        if status == 429:
            raise HTTPConnectorRateLimited(message, status_code=status)
        if 400 <= status < 500:
            raise HTTPConnectorValidationError(message, status_code=status)
        raise HTTPConnectorUnavailable(message, status_code=status)
