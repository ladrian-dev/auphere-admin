"""Process-wide Composio client singleton — shared between the API admin
endpoints and the worker runtime.

Originally this lived in ``api/admin/connectors.py``. The Block N runtime
proxy needs to call ``execute_tool`` from the worker process too, which
must not import the admin module (it would pull in FastAPI route deps
and Pydantic models the worker doesn't need). Moving the factory here
gives both call-sites a single canonical accessor without crossing
package boundaries.

In tests the worker can swap the singleton via ``set_composio_client``.
"""

from __future__ import annotations

import logging

from nexus_api.config import get_settings
from nexus_api.services.connectors.composio_client import (
    ComposioClientProtocol,
    FakeComposioClient,
    LiveComposioClient,
)

log = logging.getLogger(__name__)


_singleton: ComposioClientProtocol | None = None


def get_composio_client() -> ComposioClientProtocol:
    """Return the process-wide Composio client.

    Returns ``LiveComposioClient`` when ``settings.composio_api_key`` is
    populated; otherwise falls back to ``FakeComposioClient`` so dev /
    test environments can exercise the catalog and runtime paths without
    a Composio account. The fake is *not* safe for production — the
    catalog endpoint logs a warning when it kicks in.
    """
    global _singleton
    if _singleton is not None:
        return _singleton
    settings = get_settings()
    if settings.composio_api_key:
        _singleton = LiveComposioClient(api_key=settings.composio_api_key)
    else:
        log.warning("connectors.composio.fallback_fake_client")
        _singleton = FakeComposioClient()
    return _singleton


def set_composio_client(client: ComposioClientProtocol | None) -> None:
    """Test hook to inject a fake client or reset the singleton."""
    global _singleton
    _singleton = client
