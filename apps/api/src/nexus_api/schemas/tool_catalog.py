from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict


class ToolCatalogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    mcp_server: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    side_effects: list[str]
    capability_tags: list[str]
    cost_estimate: dict[str, Any]
    status: str
