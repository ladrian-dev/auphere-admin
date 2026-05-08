from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class TenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    plan: str
    status: str
    market: str | None
    timezone: str
    business_hours: dict[str, Any] | None
    owner_phone: str | None
    owner_email: str | None
    created_at: datetime
    updated_at: datetime
