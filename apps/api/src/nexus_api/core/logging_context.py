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

import logging
import re
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

log = structlog.get_logger()

#: Un tramo de ruta con forma de token: ``secrets.token_urlsafe(32)`` son 43
#: caracteres. Por su forma y no por una lista de rutas, para que una ruta nueva
#: con un token quede cubierta sin que nadie se acuerde
#: (``tests/isolation/test_tokens_stay_out_of_request_logs.py`` las barre). Un
#: identificador larguísimo también cae: se pierde un dato de diagnóstico, no un
#: secreto.
_TOKEN_SEGMENT = re.compile(r"(?<=/)[A-Za-z0-9_-]{40,}(?=[/?]|$)")
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def safe_path(path: str) -> str:
    """La ruta sin los tokens que lleve: se puede registrar.

    Abrir un enlace de invitación es un ``GET`` con el token en la ruta. Quien
    lee ese registro puede abrir el enlace, y si la dirección aún no tiene cuenta,
    elegir la contraseña y quedarse como propietario (spec 052, CE-005). Lo mismo
    vale para el alta y para restablecer la contraseña.
    """
    return _TOKEN_SEGMENT.sub(
        lambda m: m.group(0) if _UUID.match(m.group(0)) else "[token]",
        path,
    )


class RedactAccessLog(logging.Filter):
    """Lo mismo para la línea de acceso de ``uvicorn``, que no pasa por structlog.

    Su mensaje es ``'%s - "%s %s HTTP/%s" %d'``, con la ruta en el tercer argumento.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) == 5 and isinstance(args[2], str):
            record.args = (args[0], args[1], safe_path(args[2]), args[3], args[4])
        return True


class LoggingContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=safe_path(request.url.path),
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
