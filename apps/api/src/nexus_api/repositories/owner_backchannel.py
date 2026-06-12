"""Repositories for the owner backchannel."""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import OwnerConsultation, OwnerPhoneIndex


def generate_correlation_id() -> str:
    """8-char URL-safe correlation id. ~64^8 ≈ 281T combinations, plus a
    UNIQUE constraint on the column makes accidental collisions a hard
    failure rather than a silent cross-tenant resolve."""
    return secrets.token_urlsafe(6)[:8]


class OwnerConsultationRepository:
    """RLS-scoped — every method runs under the active ``app.tenant_id``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        conversation_id: uuid.UUID,
        question_text: str,
        urgency: str,
        expected_reply_kind: str,
        template_name: str,
        template_params: dict[str, Any],
        context_summary: str | None = None,
        created_by: str = "agent",
        correlation_id: str | None = None,
    ) -> OwnerConsultation:
        tenant_id = require_current_tenant()
        row = OwnerConsultation(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            correlation_id=correlation_id or generate_correlation_id(),
            asked_at=datetime.now(UTC),
            question_text=question_text,
            context_summary=context_summary,
            urgency=urgency,
            expected_reply_kind=expected_reply_kind,
            template_name=template_name,
            template_params_json=template_params,
            status="pending",
            created_by=created_by,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, consultation_id: uuid.UUID) -> OwnerConsultation | None:
        require_current_tenant()
        return await self._session.get(OwnerConsultation, consultation_id)

    async def get_by_correlation(self, correlation_id: str) -> OwnerConsultation | None:
        """Lookup by correlation_id under the active tenant. RLS still
        applies — a hypothetical collision across tenants resolves to the
        active tenant's row, not the other tenant's."""
        require_current_tenant()
        stmt = select(OwnerConsultation).where(OwnerConsultation.correlation_id == correlation_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_by_provider_message_id(self, provider_message_id: str) -> OwnerConsultation | None:
        require_current_tenant()
        stmt = select(OwnerConsultation).where(
            OwnerConsultation.provider_message_id == provider_message_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_open_for_tenant(self, *, limit: int = 10) -> Sequence[OwnerConsultation]:
        """Open = pending or sent. Most-recent-first."""
        require_current_tenant()
        stmt = (
            select(OwnerConsultation)
            .where(OwnerConsultation.status.in_(("pending", "sent")))
            .order_by(desc(OwnerConsultation.asked_at))
            .limit(limit)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def count_in_window(self, *, since: datetime) -> int:
        """Count consultations created since ``since`` for the active
        tenant. Used by the per-hour rate cap."""
        require_current_tenant()
        from sqlalchemy import func

        stmt = select(func.count(OwnerConsultation.id)).where(OwnerConsultation.asked_at >= since)
        return int((await self._session.execute(stmt)).scalar_one())


class OwnerPhoneIndexRepository:
    """Global lookup repo — does NOT call :func:`require_current_tenant`.

    Used by the inbound webhook BEFORE the tenant is known.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lookup(self, phone_e164: str) -> OwnerPhoneIndex | None:
        return await self._session.get(OwnerPhoneIndex, phone_e164)

    async def get_phone_for_tenant(self, tenant_id: uuid.UUID) -> str | None:
        """First active phone associated to ``tenant_id``. The webhook
        and the outbox dispatcher both use this — the dispatcher to find
        the recipient before sending the template."""
        stmt = (
            select(OwnerPhoneIndex.phone_e164)
            .where(OwnerPhoneIndex.tenant_id == tenant_id)
            .where(OwnerPhoneIndex.active.is_(True))
            .order_by(OwnerPhoneIndex.added_at.asc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def register(
        self,
        *,
        phone_e164: str,
        tenant_id: uuid.UUID,
        user_label: str | None = None,
        active: bool = True,
    ) -> OwnerPhoneIndex:
        """Insert a new (phone, tenant) mapping. Caller MUST be prepared
        for ``IntegrityError`` if the phone already maps to a different
        tenant — by design, we never silently overwrite."""
        row = OwnerPhoneIndex(
            phone_e164=phone_e164,
            tenant_id=tenant_id,
            user_label=user_label,
            added_at=datetime.now(UTC),
            active=active,
        )
        self._session.add(row)
        await self._session.flush()
        return row
