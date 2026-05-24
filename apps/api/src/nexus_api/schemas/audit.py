"""Schemas for the audit_log surface (Bloque B4).

The audit_log table grows monotonically — every promote, every
runtime-flag toggle, every connector connect, every takeover. The
operator panel surfaces it as a filterable timeline so the Auphere
team can answer "who changed what, when" without psql.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditLogOut(BaseModel):
    """One row of ``audit_log`` as returned to the admin panel.

    ``before_json`` and ``after_json`` carry whatever snapshot the
    writer chose to record — agent_config diffs, connector status,
    runtime flag toggles. The UI renders them as a compact diff when
    present; when both are absent the row is still useful as a
    timeline entry (e.g. connector reconnected, conversation
    escalated).
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    actor: str
    action: str
    target: str
    before_json: dict[str, Any] | None = None
    after_json: dict[str, Any] | None = None
    created_at: datetime


class AuditLogPageOut(BaseModel):
    """Paginated audit-log response.

    ``next_cursor`` is opaque — the client passes it back as-is on the
    next request. Format documented in :class:`AuditRepository`.
    Cursor-based (vs offset-based) so a tenant with 10k audit rows
    doesn't pay the cost of skipping rows on every page navigation.
    """

    items: list[AuditLogOut]
    next_cursor: str | None
