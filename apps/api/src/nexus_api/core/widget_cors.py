"""CORS for the public web chat widget surface (``/v1/widget/*``).

The global ``CORSMiddleware`` allows exactly ``embed_app_origin`` — correct
for the iframe/broadcast surface, but the chat widget is loaded on each
tenant's OWN site (barbersupply.cl, …) and calls the API cross-origin. Those
origins are per-tenant and dynamic (stored in ``tenant_widget_configs``), so
a static CORS allow-list can't cover them.

This middleware reflects the request ``Origin`` for ``/v1/widget/*`` only.
CORS is NOT the security boundary here — authorization is the session JWT +
the server-side origin allow-list check in the endpoints. Reflecting the
origin merely lets the browser make the request; a forbidden origin still
fails the server-side check and gets no token / no data. No credentials
(cookies) are used, so reflecting is safe.

Registered AFTER the global CORS middleware so it is outermost and can
short-circuit the widget preflight before the strict global layer sees it.
Non-widget paths pass straight through untouched.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

_WIDGET_PREFIX = "/v1/widget"
_CORS_METHODS = "GET, POST, OPTIONS"
_CORS_HEADERS = "Authorization, Content-Type"
_CORS_MAX_AGE = "600"


class WidgetCORSMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not request.url.path.startswith(_WIDGET_PREFIX):
            return await call_next(request)

        origin = request.headers.get("origin")

        # Preflight: answer here without touching the route (and without
        # the strict global CORS layer rejecting the foreign origin).
        if request.method == "OPTIONS":
            response: Response = Response(status_code=204)
        else:
            response = await call_next(request)

        if origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Methods"] = _CORS_METHODS
            response.headers["Access-Control-Allow-Headers"] = _CORS_HEADERS
            response.headers["Access-Control-Max-Age"] = _CORS_MAX_AGE
        return response
