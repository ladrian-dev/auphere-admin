"""Amigable Venta-specific error aliases.

Each is a subclass of the shared HTTP base exception so tools catch the
Amigable-Venta-flavoured name and future endpoint swaps don't ripple
through every ``except`` block.
"""

from __future__ import annotations

from nexus_mcp.http import (
    HTTPConnectorAuthError,
    HTTPConnectorError,
    HTTPConnectorNotFound,
    HTTPConnectorRateLimited,
    HTTPConnectorUnavailable,
    HTTPConnectorValidationError,
)


class AmigableVentaError(HTTPConnectorError):
    """Base for every Amigable Venta client error."""


class AmigableVentaAuthError(HTTPConnectorAuthError, AmigableVentaError):
    """401 / 403 — missing, invalid or expired API key."""


class AmigableVentaNotFound(HTTPConnectorNotFound, AmigableVentaError):
    """404 — the endpoint does not exist on this deployment."""


class AmigableVentaValidationError(HTTPConnectorValidationError, AmigableVentaError):
    """4xx other than 401/403/404 — typically a missing ``q``."""


class AmigableVentaRateLimited(HTTPConnectorRateLimited, AmigableVentaError):
    """429 — persistent rate limit past bounded retry."""


class AmigableVentaUnavailable(HTTPConnectorUnavailable, AmigableVentaError):
    """5xx / transport failure after exhausted retries."""


__all__ = [
    "AmigableVentaAuthError",
    "AmigableVentaError",
    "AmigableVentaNotFound",
    "AmigableVentaRateLimited",
    "AmigableVentaUnavailable",
    "AmigableVentaValidationError",
]
