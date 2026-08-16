"""``/console/clients/{ref}/tools`` + ``/connectors`` — what the agent may
call and what it is connected to (CP-13).

Tools: the global ``tool_catalog`` (public entries only) joined with the
client's whitelist (``agent_configs.tools`` of the draft/active), the
required connector's install status and the effective gating mode.
``PUT`` replaces the whitelist ON THE DRAFT (created on demand,
``agent_drafts.ensure_draft``); publishing is CP-12.

Connectors: catalogue + install status, reusing the same
``services/connectors/service.py`` functions the backoffice uses. What
never leaves: ``credentials_ref``, consent tokens (the signed URL is
returned ONCE to the caller that asked for it), API-key secrets (input
only). TikTok (``tiktok_bm``) and other ``channel_only`` connectors are
channels, not tools — the Channels tab owns them.
"""

from __future__ import annotations

from typing import Any, cast

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.config import get_settings
from nexus_api.core.errors import AgentConfigConflict
from nexus_api.db.models import (
    AuditLog,
    Connector,
    ConnectorToolMode,
    TenantConnector,
    TenantConnectorStatus,
    TenantConnectorToolOverride,
    ToolCatalog,
    ToolStatus,
)
from nexus_api.services.agent_config_service import AgentConfigService
from nexus_api.services.connectors import catalog as connector_catalog
from nexus_api.services.connectors import service as connector_service
from nexus_api.services.connectors.composio_client import (
    ComposioAuthConfigAmbiguous,
    ComposioAuthConfigMissing,
    ComposioAuthExpired,
    ComposioClientProtocol,
    ComposioError,
    ComposioUnavailable,
)
from nexus_api.services.connectors.gating import ToolNotInCatalog
from nexus_api.services.connectors.runtime import get_composio_client
from nexus_api.services.connectors.service import (
    ConnectorAlreadyConnected,
    ConnectorNotConfigured,
    ConnectorNotFound,
    IncompatibleAuthKind,
)

from .agent_drafts import DraftView, ensure_draft, load_view
from .deps import ClientScope, client_scope
from .schemas_agent_tools import (
    ConnectApiKeyIn,
    ConnectorOut,
    ConnectorSyncOut,
    ConsentOut,
    ToolCatalogOut,
    ToolMode,
    ToolModeIn,
    ToolModeOut,
    ToolOut,
    ToolsIn,
    ToolsSaved,
)

router = APIRouter(prefix="/clients/{ref}")

EXCLUDED_CONNECTOR_SLUGS = frozenset({"tiktok_bm"})
_CONNECTED = frozenset({TenantConnectorStatus.CONNECTED.value, TenantConnectorStatus.PARTIAL.value})


def _is_channel_only(slug: str | None, provider_meta: dict[str, Any] | None) -> bool:
    if slug in EXCLUDED_CONNECTOR_SLUGS:
        return True
    return bool((provider_meta or {}).get("channel_only"))


def _logo(provider_meta: dict[str, Any] | None) -> str | None:
    for key in ("logo_url", "logo", "icon_url"):
        v = (provider_meta or {}).get(key)
        if isinstance(v, str) and v:
            return v
    return None


# ── tools ──────────────────────────────────────────────────────────────


async def _tool_rows(session: AsyncSession) -> list[sa.Row[Any]]:
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
        .outerjoin(TenantConnector, TenantConnector.connector_id == Connector.id)
        .where(ToolCatalog.status.notin_([ToolStatus.INTERNAL, ToolStatus.DEPRECATED]))
        .order_by(Connector.display_name.nulls_first(), ToolCatalog.name)
    )
    return list((await session.execute(stmt)).all())


async def _overrides(session: AsyncSession) -> dict[str, str]:
    rows = (await session.scalars(sa.select(TenantConnectorToolOverride))).all()
    return {r.tool_name: r.mode for r in rows}


async def _catalog(scope: ClientScope, view: DraftView) -> ToolCatalogOut:
    target = view.target
    enabled = set(target.tools or []) if target else set()
    active_enabled = set(view.active.tools or []) if view.active else set()
    overrides = await _overrides(scope.session)
    tools: list[ToolOut] = []
    for tool, slug, display_name, provider_meta, install_status in await _tool_rows(scope.session):
        if slug is not None and _is_channel_only(slug, provider_meta):
            continue
        override = overrides.get(tool.name)
        default_mode = cast(ToolMode, tool.default_mode)
        effective = cast(ToolMode, override) if override else default_mode
        connector_required = slug is not None
        connected = install_status in _CONNECTED
        tools.append(
            ToolOut(
                name=tool.name,
                description=tool.description,
                capability_tags=list(tool.capability_tags or []),
                read_only=tool.read_only,
                destructive=tool.destructive,
                status=tool.status.value,
                enabled=tool.name in enabled,
                enabled_in_active=tool.name in active_enabled,
                connector_slug=slug,
                connector_display_name=display_name,
                connector_status=install_status,
                connector_required=connector_required,
                usable=(tool.name in enabled) and (not connector_required or connected),
                default_mode=default_mode,
                override_mode=cast(ToolMode, override) if override else None,
                effective_mode=effective,
            )
        )
    return ToolCatalogOut(
        version=target.version if target else None,
        version_status=cast(Any, target.status.value) if target else None,
        active_version=view.active.version if view.active else None,
        has_draft=view.has_draft,
        tools=tools,
    )


@router.get("/tools", response_model=ToolCatalogOut)
async def list_tools(scope: ClientScope = Depends(client_scope("agents:read"))) -> ToolCatalogOut:
    return await _catalog(scope, await load_view(scope))


@router.put(
    "/tools",
    response_model=ToolsSaved,
    responses={422: {"description": "Unknown or internal tool."}},
)
async def put_tools(
    body: ToolsIn,
    scope: ClientScope = Depends(client_scope("agents:write")),
) -> ToolsSaved:
    """Replace the whitelist on the draft. Names must exist in the public
    catalogue (the service validates; internal tools are refused)."""
    names = list(dict.fromkeys(body.tools))
    service = AgentConfigService(scope.session)
    try:
        await service._validate_tools(names)
    except AgentConfigConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    draft, created = await ensure_draft(scope)
    draft.tools = names
    await scope.session.flush()
    out = await _catalog(scope, await load_view(scope))
    return ToolsSaved(**out.model_dump(), draft_created=created)


@router.put("/tools/{tool_name}/mode", response_model=ToolModeOut)
async def put_tool_mode(
    tool_name: str,
    body: ToolModeIn,
    scope: ClientScope = Depends(client_scope("agents:write")),
) -> ToolModeOut:
    """Per-client gating override (``always`` / ``needs_approval`` /
    ``blocked``). Takes effect immediately — it is not part of a version."""
    try:
        row = await connector_service.upsert_override(
            scope.session,
            tenant=scope.tenant,
            tool_name=tool_name,
            mode=ConnectorToolMode(body.mode),
            reason=None,
            actor=scope.principal.actor,
        )
    except ToolNotInCatalog as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await scope.session.refresh(row)
    return ToolModeOut(
        tool_name=row.tool_name,
        mode=cast(ToolMode, row.mode),
        set_by=row.set_by_actor,
        updated_at=row.updated_at,
    )


@router.delete("/tools/{tool_name}/mode", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tool_mode(
    tool_name: str,
    scope: ClientScope = Depends(client_scope("agents:write")),
) -> None:
    deleted = await connector_service.delete_override(
        scope.session, tenant=scope.tenant, tool_name=tool_name, actor=scope.principal.actor
    )
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no override")


# ── connectors ─────────────────────────────────────────────────────────


async def _connectors(
    scope: ClientScope, composio: ComposioClientProtocol, view: DraftView
) -> list[ConnectorOut]:
    entries = await connector_catalog.list_catalog(scope.session, composio)
    installs = {
        c.slug: tc
        for tc, c in (
            await scope.session.execute(
                sa.select(TenantConnector, Connector).join(
                    Connector, TenantConnector.connector_id == Connector.id
                )
            )
        ).all()
    }
    tool_counts: dict[str, tuple[int, int]] = {}
    enabled = set(view.target.tools or []) if view.target else set()
    for tool, slug, _dn, _pm, _st in await _tool_rows(scope.session):
        if slug is None:
            continue
        total, on = tool_counts.get(slug, (0, 0))
        tool_counts[slug] = (total + 1, on + (1 if tool.name in enabled else 0))
    out: list[ConnectorOut] = []
    for e in entries:
        if _is_channel_only(e.slug, e.provider_meta):
            continue
        tc = installs.get(e.slug)
        total, on = tool_counts.get(e.slug, (0, 0))
        form = e.provider_meta.get("credentials_form") if e.auth_kind == "api_key" else None
        out.append(
            ConnectorOut(
                slug=e.slug,
                display_name=e.display_name,
                vendor=e.vendor,
                category=e.category,
                auth_kind=e.auth_kind,
                logo_url=_logo(e.provider_meta),
                capabilities=list(e.capabilities or []),
                installed=tc is not None,
                status=tc.status if tc else None,
                scopes_granted=list(tc.scopes_granted or []) if tc else [],
                connected_at=tc.connected_at if tc else None,
                last_synced_at=tc.last_synced_at if tc else None,
                last_health_check_at=tc.last_health_check_at if tc else None,
                consent_expires_at=tc.consent_token_expires_at if tc else None,
                credentials_form=[dict(f) for f in form] if isinstance(form, list) else [],
                tools_total=total,
                tools_enabled=on,
            )
        )
    return out


@router.get("/connectors", response_model=list[ConnectorOut])
async def list_connectors(
    scope: ClientScope = Depends(client_scope("agents:read")),
    composio: ComposioClientProtocol = Depends(get_composio_client),
) -> list[ConnectorOut]:
    return await _connectors(scope, composio, await load_view(scope))


async def _one(scope: ClientScope, composio: ComposioClientProtocol, slug: str) -> ConnectorOut:
    rows = await _connectors(scope, composio, await load_view(scope))
    row = next((r for r in rows if r.slug == slug), None)
    if row is None:  # pragma: no cover - the write above guarantees the install
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown connector")
    return row


def _guard_slug(slug: str) -> str:
    slug = slug.lower()
    if slug in EXCLUDED_CONNECTOR_SLUGS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown connector")
    return slug


@router.post(
    "/connectors/{slug}/consent",
    response_model=ConsentOut,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "Already connected."}, 503: {"description": "Provider down."}},
)
async def start_consent(
    slug: str,
    scope: ClientScope = Depends(client_scope("agents:write")),
    composio: ComposioClientProtocol = Depends(get_composio_client),
) -> ConsentOut:
    """Start (or re-issue) the OAuth consent of an ``oauth_composio``
    connector. The signed URL is returned once, to this caller."""
    slug = _guard_slug(slug)
    settings = get_settings()
    try:
        connector = await connector_catalog.ensure_composio_connector_persisted(
            scope.session, composio, slug
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ComposioUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    if connector.auth_kind != "oauth_composio":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"connector {slug} uses {connector.auth_kind}; consent does not apply",
        )
    toolkit = connector.mcp_server_ref.split(":", 1)[1]
    try:
        auth_config_id = await composio.find_auth_config_id(toolkit)
    except ComposioAuthConfigMissing as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except ComposioAuthConfigAmbiguous as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ComposioUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    callback_url = f"{settings.public_api_base_url.rstrip('/')}/connectors/oauth-callback"
    try:
        result = await connector_service.initiate_consent(
            scope.session,
            tenant=scope.tenant,
            connector_slug=slug,
            composio=composio,
            callback_url=callback_url,
            auth_config_id=auth_config_id,
            consent_secret=settings.connector_consent_secret,
            actor=scope.principal.actor,
        )
    except ConnectorAlreadyConnected as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ConnectorNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except IncompatibleAuthKind as exc:  # pragma: no cover - gated above
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ComposioUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except ComposioError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    sep = "&" if "?" in result.redirect_url else "?"
    return ConsentOut(
        slug=slug,
        signed_consent_url=f"{result.redirect_url}{sep}consent_token={result.consent_token}",
        expires_at=result.expires_at,
    )


@router.post("/connectors/{slug}/sync", response_model=ConnectorSyncOut)
async def sync_connector(
    slug: str,
    scope: ClientScope = Depends(client_scope("agents:write")),
    composio: ComposioClientProtocol = Depends(get_composio_client),
) -> ConnectorSyncOut:
    slug = _guard_slug(slug)
    connector = await scope.session.scalar(sa.select(Connector).where(Connector.slug == slug))
    if connector is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown connector")
    tc = await scope.session.scalar(
        sa.select(TenantConnector).where(TenantConnector.connector_id == connector.id)
    )
    if tc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="connector not installed")
    try:
        reconciled = await connector_service.reconcile_connector_status(
            scope.session,
            tenant_connector=tc,
            connector=connector,
            composio=composio,
            actor=scope.principal.actor,
        )
        if reconciled is not None:
            return ConnectorSyncOut(
                slug=slug,
                added=reconciled.tools_added,
                deprecated=reconciled.tools_deprecated,
                unchanged_count=0,
            )
        result = await connector_service.sync_tools_for(
            scope.session,
            tenant_connector=tc,
            connector=connector,
            composio=composio,
            actor=scope.principal.actor,
        )
    except ComposioUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except ComposioAuthExpired as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return ConnectorSyncOut(
        slug=slug,
        added=result.added,
        deprecated=result.deprecated,
        unchanged_count=len(result.unchanged),
    )


@router.post("/connectors/{slug}/disconnect", response_model=ConnectorOut)
async def disconnect_connector(
    slug: str,
    scope: ClientScope = Depends(client_scope("agents:write")),
    composio: ComposioClientProtocol = Depends(get_composio_client),
) -> ConnectorOut:
    slug = _guard_slug(slug)
    try:
        await connector_service.disconnect_connector(
            scope.session,
            tenant=scope.tenant,
            connector_slug=slug,
            composio=composio,
            actor=scope.principal.actor,
        )
    except ConnectorNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return await _one(scope, composio, slug)


_PAUSABLE_FROM = frozenset(
    {
        TenantConnectorStatus.CONNECTED.value,
        TenantConnectorStatus.PARTIAL.value,
        TenantConnectorStatus.NEEDS_REAUTH.value,
    }
)


async def _set_status(
    scope: ClientScope,
    composio: ComposioClientProtocol,
    *,
    slug: str,
    from_statuses: frozenset[str],
    to_status: str,
    action: str,
) -> ConnectorOut:
    tc = await scope.session.scalar(
        sa.select(TenantConnector)
        .join(Connector, TenantConnector.connector_id == Connector.id)
        .where(Connector.slug == slug)
    )
    if tc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="connector not installed")
    if tc.status not in from_statuses:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"cannot {action.split('.')[1]} from status {tc.status!r}",
        )
    before = tc.status
    tc.status = to_status
    scope.session.add(
        AuditLog(
            tenant_id=scope.tenant.id,
            actor=scope.principal.actor,
            action=action,
            target=f"tenant_connector:{tc.id}",
            before_json={"status": before},
            after_json={"status": to_status},
        )
    )
    await scope.session.flush()
    return await _one(scope, composio, slug)


@router.post("/connectors/{slug}/pause", response_model=ConnectorOut)
async def pause_connector(
    slug: str,
    scope: ClientScope = Depends(client_scope("agents:write")),
    composio: ComposioClientProtocol = Depends(get_composio_client),
) -> ConnectorOut:
    return await _set_status(
        scope,
        composio,
        slug=_guard_slug(slug),
        from_statuses=_PAUSABLE_FROM,
        to_status=TenantConnectorStatus.PAUSED.value,
        action="connector.pause",
    )


@router.post("/connectors/{slug}/resume", response_model=ConnectorOut)
async def resume_connector(
    slug: str,
    scope: ClientScope = Depends(client_scope("agents:write")),
    composio: ComposioClientProtocol = Depends(get_composio_client),
) -> ConnectorOut:
    return await _set_status(
        scope,
        composio,
        slug=_guard_slug(slug),
        from_statuses=frozenset({TenantConnectorStatus.PAUSED.value}),
        to_status=TenantConnectorStatus.CONNECTED.value,
        action="connector.resume",
    )


@router.post(
    "/connectors/{slug}/api-key",
    response_model=ConnectorOut,
    status_code=status.HTTP_201_CREATED,
)
async def connect_api_key(
    slug: str,
    body: ConnectApiKeyIn,
    scope: ClientScope = Depends(client_scope("agents:write")),
    composio: ComposioClientProtocol = Depends(get_composio_client),
) -> ConnectorOut:
    """Bootstrap an ``api_key`` connector. ``secrets`` are encrypted into
    ``tenant_credentials`` and never returned."""
    slug = _guard_slug(slug)
    try:
        await connector_service.bootstrap_api_key(
            scope.session,
            tenant=scope.tenant,
            connector_slug=slug,
            secret_payload=body.secrets,
            endpoint_meta=body.endpoint_meta or {"_": "console"},
            actor=scope.principal.actor,
        )
    except ConnectorNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except IncompatibleAuthKind as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return await _one(scope, composio, slug)


__all__ = ["router"]
