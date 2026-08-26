"""Admin F5 impersonation. Body is reason + ttl only; partner is the path."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from nexus_api.db.models.admin_impersonation import (
    REASON_MIN_LEN,
    TTL_DEFAULT_SECONDS,
    TTL_MAX_SECONDS,
    TTL_MIN_SECONDS,
)


class AdminImpersonateIn(BaseModel):
    """Start overlay. Partner comes from the path, operator from X-Operator-Id."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=REASON_MIN_LEN, max_length=500)
    ttl_seconds: int = Field(default=TTL_DEFAULT_SECONDS, ge=TTL_MIN_SECONDS, le=TTL_MAX_SECONDS)

    @field_validator("reason")
    @classmethod
    def _strip_reason(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < REASON_MIN_LEN:
            raise ValueError(f"reason must be at least {REASON_MIN_LEN} characters")
        return stripped


class AdminImpersonateOut(BaseModel):
    id: uuid.UUID
    partner_id: uuid.UUID
    operator_id: uuid.UUID
    reason: str
    ttl_seconds: int
    expires_at: datetime
    revoked_at: datetime | None
    created_at: datetime
