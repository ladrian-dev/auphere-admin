"""Admin endpoints for external integrations.

AgendaPro (ADR-017): public-link only. The agent uses the tenant's
public AgendaPro URL (e.g. ``cultorbarber.site.agendapro.com``) to
check availability and create appointments via the new public browser
MCP. Modify / cancel / get_appointments are escalated to the owner via
the backchannel (ADR-018) — the public flow doesn't support them.

The legacy admin/credential-based flow (browser automation of the
AgendaPro admin panel) was deprecated and removed in migration 0021.
No production tenant was using it.

WhatsApp connects via Meta Embedded Signup (``admin/meta_signup.py``)
— the YCloud manual wizard was removed with the provider (2026-06-12).

All flows require Bearer admin token.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import scoped_session_from_path
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import (
    AuditLog,
    Tenant,
)

router = APIRouter()
log = structlog.get_logger()


# ── AgendaPro public-link setup ────────────────────────────────────────────


class AgendaProPublicUrlIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Empty string clears the field; ``null`` does the same. Pydantic
    # coerces both via the validator below.
    public_url: str | None = Field(default=None, max_length=500)


class AgendaProPublicUrlOut(BaseModel):
    integration: str
    public_url: str | None
    updated_at: datetime
    audit_log_id: uuid.UUID


@router.patch(
    "/tenants/{tenant_id}/integrations/agendapro/public-url",
    response_model=AgendaProPublicUrlOut,
)
async def set_agendapro_public_url(
    tenant_id: uuid.UUID,
    body: AgendaProPublicUrlIn,
    session: AsyncSession = Depends(scoped_session_from_path),
    actor: str = Depends(require_admin_token),
) -> AgendaProPublicUrlOut:
    """Set (or clear) the tenant's public AgendaPro URL.

    The new public browser MCP reads this column when invoking
    ``booking.check_availability`` and ``booking.create_appointment``.
    Cancel / modify / get_appointments are out of scope for the public
    flow and the agent escalates them to the owner via the backchannel.
    """
    tenant = (
        await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    ).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"tenant {tenant_id} not found",
        )

    raw = (body.public_url or "").strip() or None
    # Minimal sanity check — the public browser MCP will probe the URL
    # itself before scraping. Reject anything that doesn't look like an
    # http(s) URL up front so the operator sees the typo here.
    if raw is not None and not raw.startswith(("https://", "http://")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL pública debe arrancar con https:// o http://",
        )

    before = tenant.agendapro_public_url
    tenant.agendapro_public_url = raw
    audit = AuditLog(
        tenant_id=tenant_id,
        actor=f"admin:{actor[:8]}",
        action="integration.agendapro.public_url",
        target=f"tenant:{tenant_id}",
        before_json={"public_url": before},
        after_json={"public_url": raw},
    )
    session.add(audit)
    await session.flush()
    return AgendaProPublicUrlOut(
        integration="agendapro",
        public_url=raw,
        updated_at=datetime.now(UTC),
        audit_log_id=audit.id,
    )
