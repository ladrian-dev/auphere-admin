"""Pydantic schemas for the prompt library + seed metrics (Block Q)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class PromptSnippetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    category: str
    description: str
    body: str
    verticals: list[str]
    tags: list[str]


class SeedTemplateMetricsOut(BaseModel):
    """Aggregate signal for the operator before applying a seed.

    Phase 1 numbers will be sparse (only Cultor is in prod). This is
    forward-looking infrastructure — operators see a badge that says
    "3 tenants · 94% avg eval pass rate" once the platform has more
    data.
    """

    name: str
    tenant_count: int
    active_count: int
    eval_pass_rate_avg: Decimal | None
    eval_pass_rate_count: int
    last_used_at: datetime | None
