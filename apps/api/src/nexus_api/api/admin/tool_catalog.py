from __future__ import annotations

import uuid

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session, scoped_session_from_path
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import Connector, TenantConnector, ToolCatalog, ToolStatus
from nexus_api.repositories import ToolCatalogRepository
from nexus_api.schemas.tool_catalog import ToolCatalogOut, ToolWithInstallStatusOut

router = APIRouter()


@router.get(
    "/tool-catalog",
    response_model=list[ToolCatalogOut],
    dependencies=[Depends(require_admin_token)],
)
async def list_tools(
    include_deprecated: bool = Query(default=False),
    session: AsyncSession = Depends(get_db_session),
) -> list[ToolCatalogOut]:
    repo = ToolCatalogRepository(session)
    return [
        ToolCatalogOut.model_validate(t)
        for t in await repo.list_all(include_deprecated=include_deprecated)
    ]


def _logo_from_provider_meta(provider_meta: dict[str, object] | None) -> str | None:
    """Pull the connector logo URL out of the loose ``provider_meta`` JSONB.

    The shape varies by ``auth_kind``: Composio toolkits store ``logo``
    at the top level; custom seeds use ``logo_url`` for the same purpose
    (whatsapp_ycloud, agendapro). Front-end already has a fallback chain
    in ``ConnectorLogo`` — we just hand it the best URL we have here.
    """
    if not provider_meta:
        return None
    for key in ("logo_url", "logo", "icon_url"):
        v = provider_meta.get(key)
        if isinstance(v, str) and v:
            return v
    return None


@router.get(
    "/tenants/{tenant_id}/tool-catalog",
    response_model=list[ToolWithInstallStatusOut],
)
async def list_tools_for_tenant(
    tenant_id: uuid.UUID,
    include_deprecated: bool = Query(default=False),
    session: AsyncSession = Depends(scoped_session_from_path),
    _: str = Depends(require_admin_token),
) -> list[ToolWithInstallStatusOut]:
    """Block M.2 — tenant-aware tool catalog.

    Returns every public tool (status != INTERNAL) joined with the
    tenant's connector install status. The editor uses this to disable
    tools whose connector is not connected and to surface a CTA inline
    instead of letting the operator whitelist a tool that will fail at
    runtime.

    The session is tenant-scoped so the LEFT JOIN to ``tenant_connectors``
    naturally returns at most one row per (tool, tenant). Tools without
    a connector binding (``connector_id IS NULL``) come back with all
    install fields as ``None``.
    """
    stmt = (
        sa.select(
            ToolCatalog,
            Connector.slug,
            Connector.display_name,
            Connector.provider_meta,
            TenantConnector.status,
        )
        .select_from(ToolCatalog)
        .outerjoin(Connector, Connector.id == ToolCatalog.connector_id)
        .outerjoin(
            TenantConnector,
            TenantConnector.connector_id == Connector.id,
        )
        .where(ToolCatalog.status != ToolStatus.INTERNAL)
        .order_by(ToolCatalog.name)
    )
    if not include_deprecated:
        stmt = stmt.where(ToolCatalog.status != ToolStatus.DEPRECATED)

    result = await session.execute(stmt)
    rows: list[ToolWithInstallStatusOut] = []
    for tool, slug, display_name, provider_meta, install_status in result.all():
        rows.append(
            ToolWithInstallStatusOut(
                id=tool.id,
                name=tool.name,
                description=tool.description,
                mcp_server=tool.mcp_server,
                input_schema=tool.input_schema,
                output_schema=tool.output_schema,
                side_effects=list(tool.side_effects),
                capability_tags=list(tool.capability_tags),
                cost_estimate=tool.cost_estimate,
                status=tool.status.value if hasattr(tool.status, "value") else str(tool.status),
                connector_id=tool.connector_id,
                read_only=tool.read_only,
                destructive=tool.destructive,
                requires_consent=tool.requires_consent,
                connector_slug=slug,
                connector_display_name=display_name,
                connector_logo_url=_logo_from_provider_meta(provider_meta),
                tenant_connector_status=install_status,
            )
        )
    return rows
