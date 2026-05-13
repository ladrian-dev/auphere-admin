"""Admin endpoints for the Connectors module (Block L / ADR-011).

Catalog (global):
    GET    /admin/connectors                          list catalog
    GET    /admin/connectors/{slug}                   detail

Per-tenant (RLS-scoped):
    GET    /admin/tenants/{id}/connectors             list tenant installs
    POST   /admin/tenants/{id}/connectors/{slug}/initiate-consent
    POST   /admin/tenants/{id}/connectors/{slug}/bootstrap-browser
    POST   /admin/tenants/{id}/connectors/{slug}/connect-manual
    POST   /admin/tenants/{id}/connectors/{slug}/sync
    POST   /admin/tenants/{id}/connectors/{slug}/disconnect
    POST   /admin/tenants/{id}/connectors/{slug}/reissue-consent
    GET    /admin/tenants/{id}/connector-tool-overrides
    PUT    /admin/tenants/{id}/connector-tool-overrides/{tool_name}
    DELETE /admin/tenants/{id}/connector-tool-overrides/{tool_name}

All admin paths require Bearer admin token. Composio client and consent
secret are wired through Depends so tests can swap in FakeComposioClient.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session, scoped_session_from_path
from nexus_api.config import get_settings
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import (
    AuditLog,
    Channel,
    Connector,
    ConnectorToolMode,
    Tenant,
    TenantConnector,
    TenantConnectorStatus,
    TenantConnectorToolOverride,
    TenantCredentials,
)
from nexus_api.services.connectors import catalog as connector_catalog
from nexus_api.services.connectors import service as connector_service
from nexus_api.services.connectors.composio_client import (
    ComposioAuthConfigAmbiguous,
    ComposioAuthConfigMissing,
    ComposioAuthExpired,
    ComposioClientProtocol,
    ComposioError,
    ComposioUnavailable,
    FakeComposioClient,
    LiveComposioClient,
)
from nexus_api.services.connectors.service import (
    ConnectorAlreadyConnected,
    ConnectorNotConfigured,
    ConnectorNotFound,
    IncompatibleAuthKind,
)

log = structlog.get_logger(__name__)
router = APIRouter()


# ── Composio client provider (DI) ───────────────────────────────────────────
#
# The factory lives in ``services/connectors/runtime`` so the worker can
# import it without pulling in the FastAPI admin module. Both code paths
# share the same in-process singleton — flipping ``set_composio_client``
# from a test affects every consumer.

from nexus_api.services.connectors.runtime import (  # noqa: E402
    get_composio_client,
    set_composio_client as set_composio_client_for_tests,
)


# ── shape ───────────────────────────────────────────────────────────────────


class ConnectorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    # ``id`` is null for dynamic Composio entries that haven't been
    # persisted yet. The panel uses ``slug`` as the stable identifier;
    # ``id`` is only used by callers that need a DB row reference.
    id: uuid.UUID | None = None
    slug: str
    display_name: str
    vendor: str
    category: str
    capabilities: list[str]
    auth_kind: str
    mcp_server_ref: str
    provider_meta: dict[str, Any]
    auto_enable_on_connect: bool
    auto_enable_destructive: bool
    consent_link_template_name: str | None
    status: str


class TenantConnectorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    tenant_id: uuid.UUID
    connector_id: uuid.UUID
    connector_slug: str
    connector_display_name: str
    connector_auth_kind: str
    connector_category: str
    status: str
    credentials_ref: dict[str, Any]
    scopes_granted: list[str]
    config: dict[str, Any]
    last_health_check_at: datetime | None
    last_synced_at: datetime | None
    connected_at: datetime | None
    disconnected_at: datetime | None
    consent_token_expires_at: datetime | None


class InitiateConsentOut(BaseModel):
    tenant_connector_id: uuid.UUID
    redirect_url: str
    consent_link_template_name: str
    expires_at: datetime
    # The plain magic-link URL the operator can paste/share manually if the
    # WhatsApp template fails. Includes a signed consent token in the query
    # so the OAuth callback can verify origin.
    signed_consent_url: str


class BootstrapBrowserIn(BaseModel):
    """Bootstrap a browser_credentials connector by linking an existing
    tenant_credentials row (created via the AgendaPro bootstrap flow).
    """

    model_config = ConfigDict(extra="forbid")
    tenant_credentials_id: uuid.UUID
    context_id: str | None = None


class ConnectManualIn(BaseModel):
    """Bootstrap a webhook_manual connector by linking an existing channel row."""

    model_config = ConfigDict(extra="forbid")
    channel_id: uuid.UUID


class OverrideIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: str = Field(pattern=r"^(always|blocked|needs_approval)$")
    reason: str | None = Field(default=None, max_length=2000)


class OverrideOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    tenant_id: uuid.UUID
    tool_name: str
    mode: str
    reason: str | None
    set_by_actor: str
    updated_at: datetime


class SyncOut(BaseModel):
    added: list[str]
    deprecated: list[str]
    unchanged_count: int


# ── catalog endpoints ───────────────────────────────────────────────────────


@router.get("/connectors", response_model=list[ConnectorOut])
async def list_catalog(
    category: str | None = None,
    status_filter: str | None = None,
    session: AsyncSession = Depends(get_db_session),
    composio: ComposioClientProtocol = Depends(get_composio_client),
    actor: str = Depends(require_admin_token),
) -> list[ConnectorOut]:
    """Catalog merge: custom seeds (non-OAuth) + Composio auth_configs."""
    items = await connector_catalog.list_catalog(
        session,
        composio,
        category=category,
        status_filter=status_filter,
    )
    return [ConnectorOut.model_validate(c.__dict__) for c in items]


@router.get("/connectors/{slug}", response_model=ConnectorOut)
async def get_catalog_entry(
    slug: str,
    session: AsyncSession = Depends(get_db_session),
    composio: ComposioClientProtocol = Depends(get_composio_client),
    actor: str = Depends(require_admin_token),
) -> ConnectorOut:
    entry = await connector_catalog.get_catalog_entry(session, composio, slug)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"connector slug not found: {slug!r}",
        )
    return ConnectorOut.model_validate(entry.__dict__)


# ── per-tenant endpoints ────────────────────────────────────────────────────


async def _list_tenant_installs(
    session: AsyncSession, tenant_id: uuid.UUID
) -> list[TenantConnectorOut]:
    stmt = (
        select(TenantConnector, Connector)
        .join(Connector, TenantConnector.connector_id == Connector.id)
        .where(TenantConnector.tenant_id == tenant_id)
        .order_by(Connector.category, Connector.display_name)
    )
    rows = (await session.execute(stmt)).all()
    out: list[TenantConnectorOut] = []
    for tc, c in rows:
        out.append(
            TenantConnectorOut(
                id=tc.id,
                tenant_id=tc.tenant_id,
                connector_id=tc.connector_id,
                connector_slug=c.slug,
                connector_display_name=c.display_name,
                connector_auth_kind=c.auth_kind,
                connector_category=c.category,
                status=tc.status,
                credentials_ref=tc.credentials_ref or {},
                scopes_granted=list(tc.scopes_granted or []),
                config=tc.config or {},
                last_health_check_at=tc.last_health_check_at,
                last_synced_at=tc.last_synced_at,
                connected_at=tc.connected_at,
                disconnected_at=tc.disconnected_at,
                consent_token_expires_at=tc.consent_token_expires_at,
            )
        )
    return out


@router.get(
    "/tenants/{tenant_id}/connectors",
    response_model=list[TenantConnectorOut],
)
async def list_tenant_connectors(
    tenant_id: Annotated[uuid.UUID, Path()],
    session: AsyncSession = Depends(scoped_session_from_path),
    actor: str = Depends(require_admin_token),
) -> list[TenantConnectorOut]:
    return await _list_tenant_installs(session, tenant_id)


@router.post(
    "/tenants/{tenant_id}/connectors/{slug}/initiate-consent",
    response_model=InitiateConsentOut,
    status_code=status.HTTP_201_CREATED,
)
async def initiate_consent(
    tenant_id: Annotated[uuid.UUID, Path()],
    slug: str,
    session: AsyncSession = Depends(scoped_session_from_path),
    composio: ComposioClientProtocol = Depends(get_composio_client),
    actor: str = Depends(require_admin_token),
) -> InitiateConsentOut:
    """Start an oauth_composio consent flow.

    The endpoint returns the signed consent URL whether or not the tenant
    has ``owner_phone`` configured — the panel surfaces the URL in a
    dialog so the operator can ship it via WhatsApp, email, or copy
    paste, depending on what the client prefers. WhatsApp dispatch via
    the template is best-effort and not enforced here.
    """
    settings = get_settings()
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:  # pragma: no cover — scoped_session_from_path raises 404 first
        raise HTTPException(status_code=404, detail="tenant not found")
    # Lazy upsert: if the slug is registered in Composio but doesn't have
    # a row in ``connectors`` yet (true for any OAuth toolkit the operator
    # added in the dashboard since the last deploy), create one from the
    # Composio metadata. Custom seeds (whatsapp_ycloud, agendapro) already
    # have rows from the seed runner.
    slug_lower = slug.lower()
    try:
        connector = await connector_catalog.ensure_composio_connector_persisted(
            session, composio, slug_lower
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ComposioUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"composio unavailable: {exc}",
        ) from exc
    if connector.auth_kind != "oauth_composio":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"connector {slug} is auth_kind={connector.auth_kind!r}; use "
                "/bootstrap-browser or /connect-manual instead"
            ),
        )
    # Resolve auth_config_id from Composio itself (toolkit slug → auth_config).
    # No env vars: Composio dashboard is the single source of truth. Missing
    # auth_config in Composio surfaces as 503 with an actionable message.
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
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"composio unavailable: {exc}",
        ) from exc

    callback_url = f"{settings.public_api_base_url.rstrip('/')}/connectors/oauth-callback"
    try:
        result = await connector_service.initiate_consent(
            session,
            tenant=tenant,
            connector_slug=slug,
            composio=composio,
            callback_url=callback_url,
            auth_config_id=auth_config_id,
            consent_secret=settings.connector_consent_secret,
            actor=f"admin:{actor[:8]}",
        )
    except ConnectorAlreadyConnected as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ConnectorNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except IncompatibleAuthKind as exc:  # pragma: no cover — gated above
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ComposioUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"composio unavailable: {exc}",
        ) from exc
    except ComposioError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"composio error: {exc}",
        ) from exc

    # The redirect_url from Composio embeds our callback. We append our own
    # consent_token so the OAuth callback can verify provenance.
    sep = "&" if "?" in result.redirect_url else "?"
    signed = f"{result.redirect_url}{sep}consent_token={result.consent_token}"
    return InitiateConsentOut(
        tenant_connector_id=result.tenant_connector_id,
        redirect_url=result.redirect_url,
        consent_link_template_name=result.consent_link_template_name,
        expires_at=result.expires_at,
        signed_consent_url=signed,
    )


@router.post(
    "/tenants/{tenant_id}/connectors/{slug}/bootstrap-browser",
    response_model=TenantConnectorOut,
    status_code=status.HTTP_201_CREATED,
)
async def bootstrap_browser(
    tenant_id: Annotated[uuid.UUID, Path()],
    slug: str,
    body: BootstrapBrowserIn,
    session: AsyncSession = Depends(scoped_session_from_path),
    actor: str = Depends(require_admin_token),
) -> TenantConnectorOut:
    tenant = await session.get(Tenant, tenant_id)
    assert tenant is not None  # scoped_session_from_path guards this
    # Validate the tenant_credentials row exists for this tenant.
    creds = await session.scalar(
        select(TenantCredentials).where(TenantCredentials.id == body.tenant_credentials_id)
    )
    if creds is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"tenant_credentials {body.tenant_credentials_id} not found",
        )
    try:
        await connector_service.bootstrap_browser_credentials(
            session,
            tenant=tenant,
            connector_slug=slug,
            tenant_credentials_id=body.tenant_credentials_id,
            context_id=body.context_id,
            actor=f"admin:{actor[:8]}",
        )
    except ConnectorNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IncompatibleAuthKind as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    installs = await _list_tenant_installs(session, tenant_id)
    out = next((i for i in installs if i.connector_slug == slug), None)
    if out is None:  # pragma: no cover
        raise HTTPException(status_code=500, detail="post-bootstrap lookup failed")
    return out


@router.post(
    "/tenants/{tenant_id}/connectors/{slug}/connect-manual",
    response_model=TenantConnectorOut,
    status_code=status.HTTP_201_CREATED,
)
async def connect_manual(
    tenant_id: Annotated[uuid.UUID, Path()],
    slug: str,
    body: ConnectManualIn,
    session: AsyncSession = Depends(scoped_session_from_path),
    actor: str = Depends(require_admin_token),
) -> TenantConnectorOut:
    tenant = await session.get(Tenant, tenant_id)
    assert tenant is not None
    channel = await session.scalar(select(Channel).where(Channel.id == body.channel_id))
    if channel is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"channel {body.channel_id} not found in this tenant",
        )
    try:
        await connector_service.bootstrap_webhook_manual(
            session,
            tenant=tenant,
            connector_slug=slug,
            channel_id=body.channel_id,
            actor=f"admin:{actor[:8]}",
        )
    except ConnectorNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IncompatibleAuthKind as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    installs = await _list_tenant_installs(session, tenant_id)
    out = next((i for i in installs if i.connector_slug == slug), None)
    if out is None:  # pragma: no cover
        raise HTTPException(status_code=500, detail="post-connect lookup failed")
    return out


@router.post(
    "/tenants/{tenant_id}/connectors/{slug}/sync",
    response_model=SyncOut,
)
async def sync_connector(
    tenant_id: Annotated[uuid.UUID, Path()],
    slug: str,
    session: AsyncSession = Depends(scoped_session_from_path),
    composio: ComposioClientProtocol = Depends(get_composio_client),
    actor: str = Depends(require_admin_token),
) -> SyncOut:
    connector = await session.scalar(select(Connector).where(Connector.slug == slug))
    if connector is None:
        raise HTTPException(status_code=404, detail=f"connector slug not found: {slug!r}")
    tc = await session.scalar(
        select(TenantConnector).where(
            TenantConnector.tenant_id == tenant_id,
            TenantConnector.connector_id == connector.id,
        )
    )
    if tc is None:
        raise HTTPException(
            status_code=404,
            detail=f"tenant has no install of {slug}; initiate-consent first",
        )
    try:
        result = await connector_service.sync_tools_for(
            session,
            tenant_connector=tc,
            connector=connector,
            composio=composio,
            actor=f"admin:{actor[:8]}",
        )
    except ComposioUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"composio unavailable: {exc}") from exc
    except ComposioAuthExpired as exc:
        raise HTTPException(
            status_code=409,
            detail=f"connector needs re-auth: {exc}",
        ) from exc
    return SyncOut(
        added=result.added,
        deprecated=result.deprecated,
        unchanged_count=len(result.unchanged),
    )


@router.post(
    "/tenants/{tenant_id}/connectors/{slug}/disconnect",
    response_model=TenantConnectorOut,
)
async def disconnect(
    tenant_id: Annotated[uuid.UUID, Path()],
    slug: str,
    session: AsyncSession = Depends(scoped_session_from_path),
    composio: ComposioClientProtocol = Depends(get_composio_client),
    actor: str = Depends(require_admin_token),
) -> TenantConnectorOut:
    tenant = await session.get(Tenant, tenant_id)
    assert tenant is not None
    try:
        await connector_service.disconnect_connector(
            session,
            tenant=tenant,
            connector_slug=slug,
            composio=composio,
            actor=f"admin:{actor[:8]}",
        )
    except ConnectorNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    installs = await _list_tenant_installs(session, tenant_id)
    out = next((i for i in installs if i.connector_slug == slug), None)
    if out is None:  # pragma: no cover
        raise HTTPException(status_code=500, detail="post-disconnect lookup failed")
    return out


_PAUSABLE_FROM = frozenset(
    {
        TenantConnectorStatus.CONNECTED.value,
        TenantConnectorStatus.PARTIAL.value,
        TenantConnectorStatus.NEEDS_REAUTH.value,
    }
)


@router.post(
    "/tenants/{tenant_id}/connectors/{slug}/pause",
    response_model=TenantConnectorOut,
)
async def pause_connector(
    tenant_id: Annotated[uuid.UUID, Path()],
    slug: str,
    session: AsyncSession = Depends(scoped_session_from_path),
    actor: str = Depends(require_admin_token),
) -> TenantConnectorOut:
    """Block M.5 — Pause a connector without revoking upstream tokens.

    Pause keeps ``credentials_ref``, sync metadata, and Composio
    connection intact. The agent runtime skips tools bound to a paused
    connector (the editor allows whitelisting them but flags them with
    a "Pausado" badge). Reversible via ``resume``.

    409 if the install is not in a state where pausing makes sense
    (already paused, disconnected, error, or pending consent).
    """
    return await _set_connector_status(
        session,
        tenant_id=tenant_id,
        slug=slug,
        from_statuses=_PAUSABLE_FROM,
        to_status=TenantConnectorStatus.PAUSED.value,
        action="connector.pause",
        actor=actor,
    )


@router.post(
    "/tenants/{tenant_id}/connectors/{slug}/resume",
    response_model=TenantConnectorOut,
)
async def resume_connector(
    tenant_id: Annotated[uuid.UUID, Path()],
    slug: str,
    session: AsyncSession = Depends(scoped_session_from_path),
    actor: str = Depends(require_admin_token),
) -> TenantConnectorOut:
    """Block M.5 — Resume a paused connector.

    Flips ``paused → connected``. If the upstream tokens have expired
    while paused the runtime will flag the install as ``needs_reauth``
    on first use; we do NOT proactively verify here to keep the
    operator action snappy and to avoid burning Composio API quota.
    """
    return await _set_connector_status(
        session,
        tenant_id=tenant_id,
        slug=slug,
        from_statuses=frozenset({TenantConnectorStatus.PAUSED.value}),
        to_status=TenantConnectorStatus.CONNECTED.value,
        action="connector.resume",
        actor=actor,
    )


async def _set_connector_status(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    slug: str,
    from_statuses: frozenset[str],
    to_status: str,
    action: str,
    actor: str,
) -> TenantConnectorOut:
    tc = await session.scalar(
        select(TenantConnector)
        .join(Connector, TenantConnector.connector_id == Connector.id)
        .where(
            TenantConnector.tenant_id == tenant_id,
            Connector.slug == slug,
        )
    )
    if tc is None:
        raise HTTPException(
            status_code=404,
            detail=f"tenant connector {slug!r} not installed",
        )
    if tc.status not in from_statuses:
        raise HTTPException(
            status_code=409,
            detail=(
                f"cannot {action.split('.')[1]} from status {tc.status!r}; "
                f"expected one of {sorted(from_statuses)}"
            ),
        )
    before = tc.status
    tc.status = to_status
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor=f"admin:{actor[:8]}",
            action=action,
            target=f"tenant_connector:{tc.id}",
            before_json={"status": before},
            after_json={"status": to_status},
        )
    )
    await session.flush()
    installs = await _list_tenant_installs(session, tenant_id)
    out = next((i for i in installs if i.connector_slug == slug), None)
    if out is None:  # pragma: no cover
        raise HTTPException(status_code=500, detail="post-status lookup failed")
    return out


@router.post(
    "/tenants/{tenant_id}/connectors/{slug}/reissue-consent",
    response_model=InitiateConsentOut,
)
async def reissue_consent(
    tenant_id: Annotated[uuid.UUID, Path()],
    slug: str,
    session: AsyncSession = Depends(scoped_session_from_path),
    actor: str = Depends(require_admin_token),
) -> InitiateConsentOut:
    settings = get_settings()
    tenant = await session.get(Tenant, tenant_id)
    assert tenant is not None
    try:
        new_token = await connector_service.reissue_consent(
            session,
            tenant=tenant,
            connector_slug=slug,
            consent_secret=settings.connector_consent_secret,
            actor=f"admin:{actor[:8]}",
        )
    except ConnectorNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConnectorAlreadyConnected as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    # Build response from the refreshed row.
    tc = await session.scalar(
        select(TenantConnector)
        .join(Connector, TenantConnector.connector_id == Connector.id)
        .where(
            TenantConnector.tenant_id == tenant_id,
            Connector.slug == slug,
        )
    )
    assert tc is not None and tc.consent_token_expires_at is not None
    connector = await session.get(Connector, tc.connector_id)
    assert connector is not None
    template = connector.consent_link_template_name or ""
    return InitiateConsentOut(
        tenant_connector_id=tc.id,
        redirect_url=tc.credentials_ref.get("redirect_url", ""),
        consent_link_template_name=template,
        expires_at=tc.consent_token_expires_at,
        signed_consent_url=f"?consent_token={new_token}",
    )


# ── tool overrides ──────────────────────────────────────────────────────────


@router.get(
    "/tenants/{tenant_id}/connector-tool-overrides",
    response_model=list[OverrideOut],
)
async def list_overrides(
    tenant_id: Annotated[uuid.UUID, Path()],
    session: AsyncSession = Depends(scoped_session_from_path),
    actor: str = Depends(require_admin_token),
) -> list[OverrideOut]:
    rows = (
        await session.scalars(
            select(TenantConnectorToolOverride).order_by(TenantConnectorToolOverride.tool_name)
        )
    ).all()
    return [
        OverrideOut(
            tenant_id=r.tenant_id,
            tool_name=r.tool_name,
            mode=r.mode,
            reason=r.reason,
            set_by_actor=r.set_by_actor,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


@router.put(
    "/tenants/{tenant_id}/connector-tool-overrides/{tool_name}",
    response_model=OverrideOut,
)
async def put_override(
    tenant_id: Annotated[uuid.UUID, Path()],
    tool_name: str,
    body: OverrideIn,
    session: AsyncSession = Depends(scoped_session_from_path),
    actor: str = Depends(require_admin_token),
) -> OverrideOut:
    tenant = await session.get(Tenant, tenant_id)
    assert tenant is not None
    from nexus_api.services.connectors.gating import ToolNotInCatalog

    try:
        row = await connector_service.upsert_override(
            session,
            tenant=tenant,
            tool_name=tool_name,
            mode=ConnectorToolMode(body.mode),
            reason=body.reason,
            actor=f"admin:{actor[:8]}",
        )
    except ToolNotInCatalog as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.refresh(row)
    return OverrideOut(
        tenant_id=row.tenant_id,
        tool_name=row.tool_name,
        mode=row.mode,
        reason=row.reason,
        set_by_actor=row.set_by_actor,
        updated_at=row.updated_at,
    )


@router.delete(
    "/tenants/{tenant_id}/connector-tool-overrides/{tool_name}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_override(
    tenant_id: Annotated[uuid.UUID, Path()],
    tool_name: str,
    session: AsyncSession = Depends(scoped_session_from_path),
    actor: str = Depends(require_admin_token),
) -> None:
    tenant = await session.get(Tenant, tenant_id)
    assert tenant is not None
    deleted = await connector_service.delete_override(
        session,
        tenant=tenant,
        tool_name=tool_name,
        actor=f"admin:{actor[:8]}",
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no override for tool {tool_name!r}",
        )


__all__ = ["get_composio_client", "router", "set_composio_client_for_tests"]
