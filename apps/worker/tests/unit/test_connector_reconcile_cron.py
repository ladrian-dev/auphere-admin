"""Regression: the reconcile cron must not commit inside the scoped session.

``tenant_scoped_session`` wraps the body in ``async with session.begin()``
and commits on clean exit. An extra ``await session.commit()`` closed that
transaction early, so the context manager's own commit then raised
"Can't operate on closed transaction inside context manager" on every tick.
"""

from __future__ import annotations

import contextlib
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from nexus_worker.streams import connector_reconcile_cron as cron

pytestmark = [pytest.mark.unit]


@pytest.fixture
def _patched(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    monkeypatch.setattr(cron, "get_composio_client", lambda: MagicMock())

    session = MagicMock()
    session.commit = AsyncMock()
    # No oauth_composio connectors this tenant → empty result set.
    result = MagicMock()
    result.all.return_value = []
    session.execute = AsyncMock(return_value=result)

    @contextlib.asynccontextmanager
    async def _sm_cm():  # type: ignore[no-untyped-def]
        yield session

    monkeypatch.setattr(cron, "get_sessionmaker", lambda: lambda: _sm_cm())

    @contextlib.asynccontextmanager
    async def _scoped(_session, _tenant_id):  # type: ignore[no-untyped-def]
        yield _session

    monkeypatch.setattr(cron, "tenant_scoped_session", _scoped)
    return session


async def test_reconcile_tenant_does_not_commit(_patched: MagicMock) -> None:
    sm = cron.get_sessionmaker()
    await cron._reconcile_tenant(sm, uuid.uuid4())
    # The scoped-session context manager owns the commit — the cron must not.
    _patched.commit.assert_not_called()
