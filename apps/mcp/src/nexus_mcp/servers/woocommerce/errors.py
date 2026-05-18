"""WooCommerce-specific error aliases.

Each one is a subclass of the shared HTTP base exception. Tools catch
the WooCommerce-flavoured name so future swaps (e.g. moving to a
GraphQL endpoint) don't ripple through every tool's ``except`` block.
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


class WooCommerceError(HTTPConnectorError):
    """Base for every WooCommerce client error."""


class WooCommerceAuthError(HTTPConnectorAuthError, WooCommerceError):
    """401 / 403 — invalidates ``tenant_connectors.status``."""


class WooCommerceNotFound(HTTPConnectorNotFound, WooCommerceError):
    """404 — referenced product / order / customer does not exist."""


class WooCommerceValidationError(HTTPConnectorValidationError, WooCommerceError):
    """4xx other than 401/403/404 — usually a malformed payload."""


class WooCommerceRateLimited(HTTPConnectorRateLimited, WooCommerceError):
    """429 — persistent rate limit past bounded retry."""


class WooCommerceUnavailable(HTTPConnectorUnavailable, WooCommerceError):
    """5xx / transport failure after exhausted retries."""


__all__ = [
    "WooCommerceAuthError",
    "WooCommerceError",
    "WooCommerceNotFound",
    "WooCommerceRateLimited",
    "WooCommerceUnavailable",
    "WooCommerceValidationError",
]
