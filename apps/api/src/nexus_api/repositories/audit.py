from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import AuditLog


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        actor: str,
        action: str,
        target: str,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> AuditLog:
        tenant_id = require_current_tenant()
        entry = AuditLog(
            tenant_id=tenant_id,
            actor=actor,
            action=action,
            target=target,
            before_json=before,
            after_json=after,
        )
        self._session.add(entry)
        await self._session.flush()
        return entry
