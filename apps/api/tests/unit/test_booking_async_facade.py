"""Block O — booking.create_appointment async path (unit).

Validates that the tenant-detection helper distinguishes between
public-link and local-only tenants without touching the network.
The full booking facade ``run()`` is exercised via integration
tests (DB required) elsewhere.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from nexus_mcp.servers.booking.tools import _tenant_uses_public_link

pytestmark = pytest.mark.asyncio


async def test_tenant_uses_public_link_true_when_url_set():
    session = MagicMock()
    tenant = MagicMock()
    tenant.agendapro_public_url = "https://cultorbarber.site.agendapro.com/cl/sucursal/481889"
    session.get = AsyncMock(return_value=tenant)
    assert await _tenant_uses_public_link(session, uuid.uuid4()) is True


async def test_tenant_uses_public_link_false_when_url_blank():
    session = MagicMock()
    tenant = MagicMock()
    tenant.agendapro_public_url = "   "
    session.get = AsyncMock(return_value=tenant)
    assert await _tenant_uses_public_link(session, uuid.uuid4()) is False


async def test_tenant_uses_public_link_false_when_url_none():
    session = MagicMock()
    tenant = MagicMock()
    tenant.agendapro_public_url = None
    session.get = AsyncMock(return_value=tenant)
    assert await _tenant_uses_public_link(session, uuid.uuid4()) is False


async def test_tenant_uses_public_link_false_when_tenant_missing():
    session = MagicMock()
    session.get = AsyncMock(return_value=None)
    assert await _tenant_uses_public_link(session, uuid.uuid4()) is False
