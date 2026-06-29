"""Amigable Cobro-specific error aliases.

Each is a subclass of the shared HTTP base exception so tools catch the
Amigable-Cobro-flavoured name and future endpoint swaps don't ripple
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


class AmigableCobroError(HTTPConnectorError):
    """Base for every Amigable Cobro client error."""


class AmigableCobroAuthError(HTTPConnectorAuthError, AmigableCobroError):
    """401 / 403 — bad entity-id or token; invalidates the connector."""


class AmigableCobroNotFound(HTTPConnectorNotFound, AmigableCobroError):
    """404 — referenced business / account does not exist."""


class AmigableCobroValidationError(HTTPConnectorValidationError, AmigableCobroError):
    """4xx other than 401/403/404 — usually a missing/invalid param."""


class AmigableCobroRateLimited(HTTPConnectorRateLimited, AmigableCobroError):
    """429 — persistent rate limit past bounded retry."""


class AmigableCobroUnavailable(HTTPConnectorUnavailable, AmigableCobroError):
    """5xx / transport failure after exhausted retries."""


__all__ = [
    "AmigableCobroAuthError",
    "AmigableCobroError",
    "AmigableCobroNotFound",
    "AmigableCobroRateLimited",
    "AmigableCobroUnavailable",
    "AmigableCobroValidationError",
]
