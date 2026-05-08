"""Structlog binding middleware.

Each request binds:
  - request_id (uuid4 — generated if no `X-Request-Id` header)
  - tenant_id (set later by the tenant-context middleware once the tenant resolves)
  - channel_id (set by webhook handlers post-resolution)
  - trace_id (OTel span id, if available)

The bindings live in `structlog.contextvars` so any logger in any module emits
them automatically. Garantía 6 of architecture/agent-isolation.md.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

log = structlog.get_logger()


class LoggingContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )
        try:
            response = await call_next(request)
            response.headers["x-request-id"] = request_id
            return response
        finally:
            structlog.contextvars.clear_contextvars()


def bind_tenant(
    tenant_id: uuid.UUID | str | None, channel_id: uuid.UUID | str | None = None
) -> None:
    """Helper called from middlewares/handlers once the tenant has been resolved."""
    bindings: dict[str, str] = {}
    if tenant_id is not None:
        bindings["tenant_id"] = str(tenant_id)
    if channel_id is not None:
        bindings["channel_id"] = str(channel_id)
    if bindings:
        structlog.contextvars.bind_contextvars(**bindings)
