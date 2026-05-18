"""Reusable HTTP scaffolding for ``api_key``-style MCP connectors.

Born with WooCommerce (Bloque L+1) — first connector talking REST API
directly (no Composio, no browser, no SDK). Designed to be reused by
the next ``api_key`` connectors (Shopify, Stripe, custom REST APIs)
without copying retry / auth / error-mapping code.

Anything specific to a vendor (paths, response shape, error semantics)
lives in the vendor's own ``client.py`` subclass.
"""

from nexus_mcp.http.base_client import (
    BaseHTTPConnectorClient,
    HTTPConnectorAuthError,
    HTTPConnectorError,
    HTTPConnectorNotFound,
    HTTPConnectorRateLimited,
    HTTPConnectorUnavailable,
    HTTPConnectorValidationError,
    PaginationMeta,
)

__all__ = [
    "BaseHTTPConnectorClient",
    "HTTPConnectorAuthError",
    "HTTPConnectorError",
    "HTTPConnectorNotFound",
    "HTTPConnectorRateLimited",
    "HTTPConnectorUnavailable",
    "HTTPConnectorValidationError",
    "PaginationMeta",
]
