"""DB helper for MCP tools — opens a tenant-scoped session bound to the
active contextvar.

Tools assume the contextvar is already set by the caller (the pipeline
node opens ``tenant_context`` before invoking the registry). Each tool
opens a short transaction, does its work, and exits. The caller never
provides the session — that contract makes sure no tool can be invoked
outside a tenant-scoped run.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from nexus_api.core.tenant_context import require_current_tenant, tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def tool_session() -> AsyncIterator[AsyncSession]:
    """Open a session and run inside ``tenant_scoped_session`` for the
    active tenant. Commits on clean exit, rolls back on exception."""
    tenant_id = require_current_tenant()
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        yield session
