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
    # Block L additions (migration 0013) — exposed in M.2 so the editor
    # can render the connector binding next to each tool.
    connector_id: uuid.UUID | None = None
    read_only: bool = False
    destructive: bool = False
    requires_consent: bool = False


class ToolWithInstallStatusOut(ToolCatalogOut):
    """Block M.2 — per-tenant view that joins tool_catalog with the
    tenant's connector install status.

    The fields below are derived from the join, not from tool_catalog
    itself. They are ``None`` for tools that don't bind to a connector
    (internal helpers, or pre-Block-L tools with ``connector_id IS NULL``).

    ``tenant_connector_status`` answers the operator's question "can the
    agent actually use this tool right now?" — the editor disables the
    checkbox unless the status is ``connected`` (or ``partial`` / ``paused``
    with an explicit warning).
    """

    connector_slug: str | None = None
    connector_display_name: str | None = None
    connector_logo_url: str | None = None
    tenant_connector_status: str | None = None
