"""Connector service — orchestration entry points for the API layer.

These functions are the public surface that ``api/admin/connectors.py``
and ``api/connectors.py`` (webhook + oauth callback) call. They:

- Run inside an already-RLS-scoped session (the caller is responsible).
- Write to ``tenant_connectors``, ``audit_log``, ``tool_catalog`` (global,
  no RLS).
- Talk to Composio (or any future provider) through ``ComposioClientProtocol``
  — never a concrete impl, so tests pass ``FakeComposioClient``.
- Increment counters via ``nexus_api.core.metrics``.

Each operation maps roughly 1:1 to an endpoint:

    initiate_consent           POST .../initiate-consent
    complete_consent           POST /connectors/composio-webhook (after HMAC)
    bootstrap_browser          POST .../bootstrap
    bootstrap_webhook_manual   POST .../connect-manual
    sync_tools                 POST .../sync (and called on complete_consent)
    disconnect                 POST .../disconnect
    reissue_consent            POST .../reissue-consent
    upsert_override            PUT  .../connector-tool-overrides/:tool
    delete_override            DELETE .../connector-tool-overrides/:tool

All paths emit ``audit_log`` rows with action ``connector.*`` and metadata
including ``connector_slug``. Tests verify both the side-effect AND the
audit row.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.metrics import counters
from nexus_api.db.models import (
    AuditLog,
    Connector,
    ConnectorToolMode,
    Tenant,
    TenantConnector,
    TenantConnectorStatus,
    TenantConnectorToolOverride,
    TenantCredentials,
    ToolCatalog,
    ToolStatus,
)
from nexus_api.services.agent_config_service import AgentConfigService

from .composio_client import (
    ComposioClientProtocol,
    ComposioError,
    ComposioNotFound,
    ComposioTool,
    ComposioUnavailable,
)
from .consent_token import sign_consent_token

log = structlog.get_logger(__name__)

# ── exceptions ──────────────────────────────────────────────────────────────


class ConnectorNotFound(LookupError):
    pass


class ConnectorAlreadyConnected(RuntimeError):
    pass


class ConnectorNotConfigured(RuntimeError):
    """The connector exists but its auth_config or secret is missing in env."""


class IncompatibleAuthKind(ValueError):
    """Caller invoked the wrong path for this connector's auth_kind."""


# ── dataclasses ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class InitiateConsentResult:
    tenant_connector_id: uuid.UUID
    consent_token: str
    redirect_url: str
    consent_link_template_name: str
    expires_at: datetime


@dataclass(frozen=True)
class CompleteConsentResult:
    tenant_connector_id: uuid.UUID
    tools_added: list[str]
    tools_deprecated: list[str]
    auto_enabled: list[str]
    blocked_pending_operator: list[str]


@dataclass(frozen=True)
class SyncToolsResult:
    added: list[str]
    deprecated: list[str]
    unchanged: list[str]


# ── helpers ─────────────────────────────────────────────────────────────────


def _entity_for_tenant(tenant: Tenant) -> str:
    """The Composio user_id for a tenant. Single source of truth."""
    return f"tenant_{tenant.slug}"


async def _load_connector_by_slug(session: AsyncSession, slug: str) -> Connector:
    """Connectors live in the global catalog — no RLS, slug is unique."""
    conn = await session.scalar(select(Connector).where(Connector.slug == slug))
    if conn is None:
        msg = f"connector slug not found in catalog: {slug!r}"
        raise ConnectorNotFound(msg)
    return conn


async def _load_tenant_connector(
    session: AsyncSession, tenant_id: uuid.UUID, connector_id: uuid.UUID
) -> TenantConnector | None:
    row: TenantConnector | None = await session.scalar(
        select(TenantConnector).where(
            TenantConnector.tenant_id == tenant_id,
            TenantConnector.connector_id == connector_id,
        )
    )
    return row


async def _write_audit(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor: str,
    action: str,
    target: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> AuditLog:
    row = AuditLog(
        tenant_id=tenant_id,
        actor=actor,
        action=action,
        target=target,
        before_json=before or {},
        after_json=after or {},
    )
    session.add(row)
    await session.flush()
    return row


# ── annotation derivation ───────────────────────────────────────────────────


# Hard-coded fallback annotations per Composio tool slug for the cases where
# upstream tools.list does not surface readOnlyHint / destructiveHint. The
# spike documented in BUILD-PLAN-v2 Bloque L decides which slugs need this.
# Conservative default: unknown slugs → destructive=True.
_TOOL_SLUG_ANNOTATIONS: dict[str, dict[str, bool]] = {
    # Google Calendar — common slug patterns from Composio.
    "GOOGLECALENDAR_LIST_EVENTS": {"read_only": True, "destructive": False},
    "GOOGLECALENDAR_FIND_EVENT": {"read_only": True, "destructive": False},
    "GOOGLECALENDAR_GET_EVENT": {"read_only": True, "destructive": False},
    "GOOGLECALENDAR_LIST_CALENDARS": {"read_only": True, "destructive": False},
    "GOOGLECALENDAR_CREATE_EVENT": {"read_only": False, "destructive": True},
    "GOOGLECALENDAR_UPDATE_EVENT": {"read_only": False, "destructive": True},
    "GOOGLECALENDAR_DELETE_EVENT": {"read_only": False, "destructive": True},
    "GOOGLECALENDAR_QUICK_ADD": {"read_only": False, "destructive": True},
    # Calendly
    "CALENDLY_LIST_EVENT_TYPES": {"read_only": True, "destructive": False},
    "CALENDLY_LIST_SCHEDULED_EVENTS": {"read_only": True, "destructive": False},
    "CALENDLY_CREATE_SCHEDULING_LINK": {"read_only": False, "destructive": True},
    "CALENDLY_CANCEL_EVENT": {"read_only": False, "destructive": True},
    # Notion
    "NOTION_SEARCH": {"read_only": True, "destructive": False},
    "NOTION_GET_PAGE": {"read_only": True, "destructive": False},
    "NOTION_LIST_DATABASES": {"read_only": True, "destructive": False},
    "NOTION_CREATE_PAGE": {"read_only": False, "destructive": True},
    "NOTION_UPDATE_PAGE": {"read_only": False, "destructive": True},
    "NOTION_APPEND_BLOCK": {"read_only": False, "destructive": True},
}


def _derive_annotations(tool: ComposioTool) -> dict[str, bool]:
    """Resolve read_only / destructive for a tool.

    Order:
    1. ``raw_tags`` from Composio response (readOnlyHint / destructiveHint).
    2. Hard-coded mapping in ``_TOOL_SLUG_ANNOTATIONS``.
    3. Heuristic on slug prefix (LIST_, GET_, FIND_, SEARCH_ → read_only).
    4. Conservative fallback: destructive=true.
    """
    tags = tool.raw_tags or {}
    if "readOnlyHint" in tags or "destructiveHint" in tags:
        return {
            "read_only": bool(tags.get("readOnlyHint", False)),
            "destructive": bool(tags.get("destructiveHint", False)),
        }
    if tool.slug in _TOOL_SLUG_ANNOTATIONS:
        return dict(_TOOL_SLUG_ANNOTATIONS[tool.slug])
    upper = tool.slug.upper()
    for prefix in ("_LIST_", "_GET_", "_FIND_", "_SEARCH_", "_READ_"):
        if prefix in upper:
            return {"read_only": True, "destructive": False}
    return {"read_only": False, "destructive": True}


def _default_mode_for(*, read_only: bool, destructive: bool, auto_enable_destructive: bool) -> str:
    if read_only or not destructive:
        return ConnectorToolMode.ALWAYS.value
    return (
        ConnectorToolMode.ALWAYS.value
        if auto_enable_destructive
        else ConnectorToolMode.BLOCKED.value
    )


# ── core operations ─────────────────────────────────────────────────────────


async def initiate_consent(
    session: AsyncSession,
    *,
    tenant: Tenant,
    connector_slug: str,
    composio: ComposioClientProtocol,
    callback_url: str,
    auth_config_id: str,
    consent_secret: str,
    actor: str,
) -> InitiateConsentResult:
    """Start the OAuth consent dance for an oauth_composio connector."""
    connector = await _load_connector_by_slug(session, connector_slug)
    if connector.auth_kind != "oauth_composio":
        msg = (
            f"connector {connector_slug} has auth_kind={connector.auth_kind!r}; "
            "initiate_consent is only valid for oauth_composio"
        )
        raise IncompatibleAuthKind(msg)
    if not auth_config_id:
        msg = (
            f"connector {connector_slug}: auth_config_id is empty — "
            "did you set NEXUS_COMPOSIO_AUTH_CONFIG_* in Doppler?"
        )
        raise ConnectorNotConfigured(msg)
    if not connector.consent_link_template_name:
        msg = f"connector {connector_slug} has no consent_link_template_name"
        raise ConnectorNotConfigured(msg)

    existing = await _load_tenant_connector(session, tenant.id, connector.id)
    if existing and existing.status == TenantConnectorStatus.CONNECTED.value:
        msg = f"tenant {tenant.slug} already has connector {connector_slug} connected"
        raise ConnectorAlreadyConnected(msg)

    user_id = _entity_for_tenant(tenant)
    try:
        req = await composio.link_account(
            user_id=user_id,
            auth_config_id=auth_config_id,
            callback_url=callback_url,
        )
    except ComposioUnavailable:
        counters.incr(f"connector.consent.failed:{connector_slug}:composio_unavailable")
        raise
    except ComposioError as exc:
        counters.incr(f"connector.consent.failed:{connector_slug}:{type(exc).__name__}")
        raise

    consent_token, payload = sign_consent_token(
        tenant_id=tenant.id,
        connector_id=connector.id,
        secret=consent_secret,
    )

    if existing is None:
        tc = TenantConnector(
            tenant_id=tenant.id,
            connector_id=connector.id,
            status=TenantConnectorStatus.PENDING.value,
            credentials_ref={
                "composio_connection_id": req.connection_id,
                "user_id": user_id,
            },
            scopes_granted=[],
            config={},
            consent_token=consent_token,
            consent_token_expires_at=payload.expires_at,
        )
        session.add(tc)
    else:
        existing.status = TenantConnectorStatus.PENDING.value
        existing.credentials_ref = {
            "composio_connection_id": req.connection_id,
            "user_id": user_id,
        }
        existing.consent_token = consent_token
        existing.consent_token_expires_at = payload.expires_at
        existing.disconnected_at = None
        tc = existing
    await session.flush()

    await _write_audit(
        session,
        tenant_id=tenant.id,
        actor=actor,
        action="connector.connect_initiated",
        target=f"connector:{connector_slug}",
        after={
            "connector_slug": connector_slug,
            "composio_connection_id": req.connection_id,
            "expires_at": payload.expires_at.isoformat(),
        },
    )
    counters.incr(f"connector.consent.initiated:{connector_slug}")

    return InitiateConsentResult(
        tenant_connector_id=tc.id,
        consent_token=consent_token,
        redirect_url=req.redirect_url,
        consent_link_template_name=connector.consent_link_template_name,
        expires_at=payload.expires_at,
    )


async def complete_consent_from_webhook(
    session: AsyncSession,
    *,
    composio_connection_id: str,
    upstream_status: str,
    granted_scopes: list[str],
    composio: ComposioClientProtocol,
    actor: str = "system:composio_webhook",
) -> CompleteConsentResult | None:
    """Apply a webhook event for an existing pending tenant_connector.

    Returns ``None`` if the connection_id is unknown (404-equivalent at
    the API layer). Returns the result with tools added on success.

    Called from ``/connectors/composio-webhook`` AFTER HMAC verification.
    The caller MUST set the RLS-scoped session by tenant_id before calling
    — but for the webhook path we don't know the tenant up front; instead
    the caller looks it up by composio_connection_id with row_security off,
    then opens a tenant-scoped session and passes it here.
    """
    tc = await session.scalar(
        select(TenantConnector).where(
            TenantConnector.credentials_ref["composio_connection_id"].astext
            == composio_connection_id
        )
    )
    if tc is None:
        return None

    connector = await session.get(Connector, tc.connector_id)
    if connector is None:  # pragma: no cover — FK guarantees this
        msg = f"orphan tenant_connector {tc.id}"
        raise RuntimeError(msg)

    if upstream_status == "ACTIVE":
        tc.status = TenantConnectorStatus.CONNECTED.value
        tc.connected_at = datetime.now(UTC)
        tc.scopes_granted = list(granted_scopes)
        tc.consent_token = None
        tc.consent_token_expires_at = None
        action = "connector.connect_completed"
    elif upstream_status == "EXPIRED":
        tc.status = TenantConnectorStatus.NEEDS_REAUTH.value
        action = "connector.needs_reauth"
    elif upstream_status == "FAILED":
        tc.status = TenantConnectorStatus.ERROR.value
        action = "connector.error"
    else:
        # Unknown upstream status: write audit but don't change row.
        await _write_audit(
            session,
            tenant_id=tc.tenant_id,
            actor=actor,
            action="connector.webhook_unhandled_status",
            target=f"connector:{connector.slug}",
            after={"upstream_status": upstream_status},
        )
        return CompleteConsentResult(
            tenant_connector_id=tc.id,
            tools_added=[],
            tools_deprecated=[],
            auto_enabled=[],
            blocked_pending_operator=[],
        )

    await _write_audit(
        session,
        tenant_id=tc.tenant_id,
        actor=actor,
        action=action,
        target=f"connector:{connector.slug}",
        after={
            "composio_connection_id": composio_connection_id,
            "granted_scopes": list(granted_scopes),
        },
    )
    counters.incr(f"connector.consent.{action.split('.')[-1]}:{connector.slug}")

    if upstream_status != "ACTIVE":
        return CompleteConsentResult(
            tenant_connector_id=tc.id,
            tools_added=[],
            tools_deprecated=[],
            auto_enabled=[],
            blocked_pending_operator=[],
        )

    # On ACTIVE, fan out to tools/list sync.
    sync = await sync_tools_for(
        session,
        tenant_connector=tc,
        connector=connector,
        composio=composio,
        actor=actor,
    )
    auto_enabled = []
    blocked = []
    for slug in sync.added:
        tool = await session.scalar(select(ToolCatalog).where(ToolCatalog.name == slug))
        if tool is None:
            continue
        if tool.default_mode == ConnectorToolMode.ALWAYS.value:
            auto_enabled.append(slug)
        else:
            blocked.append(slug)
    await auto_enable_connector_tools(
        session, tenant_id=tc.tenant_id, connector=connector, actor=actor
    )
    return CompleteConsentResult(
        tenant_connector_id=tc.id,
        tools_added=sync.added,
        tools_deprecated=sync.deprecated,
        auto_enabled=auto_enabled,
        blocked_pending_operator=blocked,
    )


async def reconcile_connector_status(
    session: AsyncSession,
    *,
    tenant_connector: TenantConnector,
    connector: Connector,
    composio: ComposioClientProtocol,
    actor: str = "system:sync_reconcile",
) -> CompleteConsentResult | None:
    """Reconcile a tenant_connector's status against Composio's live state.

    The status of an ``oauth_composio`` install flips to ``connected`` only
    via the Composio webhook (``complete_consent_from_webhook``). If that
    server-to-server callback never lands — Composio webhook not configured,
    a transient miss, a signature mismatch — the install stays ``pending``
    forever even though the OAuth succeeded and the connection is ``ACTIVE``
    on Composio. Neither the browser ``oauth-callback`` nor a tools-only sync
    recover from that.

    This polls ``composio.get_account`` and, when the upstream status implies
    a transition our row hasn't applied yet, drives it through the SAME path
    the webhook uses (so ACTIVE also fans out to tools sync + auto-enable).
    Returns the transition result, or ``None`` when nothing was applied
    (already in sync, not an oauth_composio install, or no connection id).

    Idempotent: when the row already matches the upstream status it is a
    no-op, so the operator's "Sincronizar" button is safe to click anytime.
    """
    if connector.auth_kind != "oauth_composio":
        return None
    connection_id = (tenant_connector.credentials_ref or {}).get(
        "composio_connection_id"
    )
    if not connection_id:
        return None
    try:
        account = await composio.get_account(str(connection_id))
    except ComposioNotFound:
        # The connection no longer exists on Composio's side. Don't guess —
        # leave the row as-is; a fresh consent is the only safe recovery.
        log.info(
            "connector.reconcile.connection_not_found",
            connector=connector.slug,
            connection_id=str(connection_id),
        )
        return None

    upstream = (account.status or "").upper()
    target_status = {
        "ACTIVE": TenantConnectorStatus.CONNECTED.value,
        "EXPIRED": TenantConnectorStatus.NEEDS_REAUTH.value,
        "FAILED": TenantConnectorStatus.ERROR.value,
    }.get(upstream)
    # Nothing to do when the upstream status is unmapped, or our row already
    # reflects it (the common case for a healthy, already-connected install).
    if target_status is None or tenant_connector.status == target_status:
        return None

    counters.incr(f"connector.reconcile.applied:{connector.slug}:{upstream}")
    return await complete_consent_from_webhook(
        session,
        composio_connection_id=str(connection_id),
        upstream_status=upstream,
        granted_scopes=list(account.granted_scopes),
        composio=composio,
        actor=actor,
    )


async def sync_tools_for(
    session: AsyncSession,
    *,
    tenant_connector: TenantConnector,
    connector: Connector,
    composio: ComposioClientProtocol,
    actor: str,
) -> SyncToolsResult:
    """Call composio.tools.get(...) and reconcile tool_catalog.

    Only for oauth_composio connectors. For browser_credentials and
    webhook_manual the tools are static and seeded with the existing
    Bloque D/E migrations — no upstream tools/list call.

    Idempotent. Re-runs that see the same tools produce zero changes.
    """
    if connector.auth_kind != "oauth_composio":
        # No-op for static-tools connectors.
        return SyncToolsResult(added=[], deprecated=[], unchanged=[])

    if not connector.mcp_server_ref.startswith("composio:"):
        msg = f"connector {connector.slug}: malformed mcp_server_ref {connector.mcp_server_ref!r}"
        raise RuntimeError(msg)
    toolkit = connector.mcp_server_ref.split(":", 1)[1]

    user_id = tenant_connector.credentials_ref.get("user_id", "")
    if not user_id:
        msg = f"tenant_connector {tenant_connector.id} has empty user_id"
        raise RuntimeError(msg)

    try:
        tools = await composio.list_tools(user_id=user_id, toolkit=toolkit)
    except ComposioUnavailable:
        counters.incr(f"connector.sync.failed:{connector.slug}:composio_unavailable")
        raise

    upstream_slugs = {t.slug for t in tools}
    existing_rows = (
        await session.scalars(select(ToolCatalog).where(ToolCatalog.connector_id == connector.id))
    ).all()
    existing_by_slug = {r.name: r for r in existing_rows}

    added: list[str] = []
    unchanged: list[str] = []
    for t in tools:
        ann = _derive_annotations(t)
        default_mode = _default_mode_for(
            read_only=ann["read_only"],
            destructive=ann["destructive"],
            auto_enable_destructive=connector.auto_enable_destructive,
        )
        existing_row = existing_by_slug.get(t.slug)
        if existing_row is None:
            row = ToolCatalog(
                name=t.slug,
                description=t.description or f"{connector.display_name} tool {t.slug}",
                mcp_server=connector.mcp_server_ref,
                input_schema=t.input_schema,
                output_schema=t.output_schema,
                side_effects=["destructive"] if ann["destructive"] else [],
                capability_tags=[connector.category],
                cost_estimate={},
                connector_id=connector.id,
                read_only=ann["read_only"],
                destructive=ann["destructive"],
                requires_consent=True,
                default_mode=default_mode,
            )
            session.add(row)
            added.append(t.slug)
        else:
            # Update annotations + schema if they drifted.
            existing_row.description = t.description or existing_row.description
            existing_row.input_schema = t.input_schema or existing_row.input_schema
            existing_row.output_schema = t.output_schema or existing_row.output_schema
            existing_row.read_only = ann["read_only"]
            existing_row.destructive = ann["destructive"]
            existing_row.default_mode = default_mode
            unchanged.append(t.slug)

    from nexus_api.db.models import ToolStatus

    deprecated: list[str] = []
    for slug, row in existing_by_slug.items():
        if slug not in upstream_slugs:
            row.status = ToolStatus.DEPRECATED
            deprecated.append(slug)

    tenant_connector.last_synced_at = datetime.now(UTC)
    await session.flush()

    await _write_audit(
        session,
        tenant_id=tenant_connector.tenant_id,
        actor=actor,
        action="connector.tools.synced",
        target=f"connector:{connector.slug}",
        after={
            "added": added,
            "deprecated": deprecated,
            "unchanged_count": len(unchanged),
        },
    )
    counters.incr(f"connector.tools.synced:{connector.slug}:added", len(added))
    counters.incr(f"connector.tools.synced:{connector.slug}:deprecated", len(deprecated))
    return SyncToolsResult(added=added, deprecated=deprecated, unchanged=unchanged)


async def auto_enable_connector_tools(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    connector: Connector,
    actor: str,
) -> list[str]:
    """Stage a new ``agent_config`` version that adds the connector's safe
    tools to the agent whitelist — step 11 of ``architecture/connectors.md``.

    Called right after a connector reaches ``connected`` (any auth_kind).
    Tools whose ``tool_catalog.default_mode`` is ``always`` (read-only
    tools, plus destructive tools when the connector is flagged
    ``auto_enable_destructive``) are appended to the whitelist of a fresh
    STAGED version cloned from the tenant's current config. Destructive
    tools left at ``blocked`` are NOT auto-added — the operator opts them
    in deliberately from the agent editor.

    No-op (returns ``[]``) when:

    - the connector has ``auto_enable_on_connect=false``;
    - the connector contributes no ``always``-mode tools;
    - the tenant has no ``agent_config`` yet (apply a seed template first —
      the editor then surfaces these tools per the connector-aware catalog);
    - every candidate tool is already whitelisted.

    Idempotent: reconnecting a connector whose tools are already in the
    whitelist stages nothing, so it never spams staged versions. Runs
    inside the caller's RLS-scoped session.
    """
    if not connector.auto_enable_on_connect:
        return []

    tool_rows = (
        await session.scalars(
            select(ToolCatalog).where(
                ToolCatalog.connector_id == connector.id,
                ToolCatalog.status == ToolStatus.ACTIVE,
            )
        )
    ).all()
    candidates = sorted(
        t.name for t in tool_rows if t.default_mode == ConnectorToolMode.ALWAYS.value
    )
    if not candidates:
        return []

    svc = AgentConfigService(session)
    # Extend the LATEST version (highest version number, active or staged)
    # — not necessarily the active one. Basing off the latest keeps the
    # operator's in-progress draft intact and makes this idempotent: once
    # the connector's tools are in the newest version, a re-connect adds
    # nothing and stages nothing.
    versions = await svc.list_versions()
    base = max(versions, key=lambda v: v.version, default=None)
    if base is None:
        # No config to extend — the operator applies a seed template
        # first; the connector-aware editor catalog then exposes these
        # tools for explicit selection.
        return []

    current = set(base.tools)
    added = [name for name in candidates if name not in current]
    if not added:
        return []

    await svc.stage_new_version(
        actor=actor,
        system_prompt_rendered=base.system_prompt_rendered,
        channels=list(base.channels),
        tools=sorted(current | set(added)),
        policies=dict(base.policies),
        seed_template_ref=base.seed_template_ref,
        kg_schema_id=base.kg_schema_id,
    )
    await _write_audit(
        session,
        tenant_id=tenant_id,
        actor=actor,
        action="connector.tools_auto_enabled",
        target=f"connector:{connector.slug}",
        after={"tools_added": added},
    )
    counters.incr(f"connector.tools_auto_enabled:{connector.slug}")
    return added


async def bootstrap_webhook_manual(
    session: AsyncSession,
    *,
    tenant: Tenant,
    connector_slug: str,
    channel_id: uuid.UUID,
    actor: str,
) -> TenantConnector:
    """Register an existing channel row as a connector install.

    Used by Block J's wizard for WhatsApp — the channel row is created
    first by the existing whatsapp-manual flow, this just mirrors it
    into the connectors layer for the uniform panel view.
    """
    connector = await _load_connector_by_slug(session, connector_slug)
    if connector.auth_kind != "webhook_manual":
        msg = (
            f"connector {connector_slug} has auth_kind={connector.auth_kind!r}; "
            "bootstrap_webhook_manual requires webhook_manual"
        )
        raise IncompatibleAuthKind(msg)

    existing = await _load_tenant_connector(session, tenant.id, connector.id)
    if existing:
        existing.status = TenantConnectorStatus.CONNECTED.value
        existing.credentials_ref = {"channel_id": str(channel_id)}
        existing.connected_at = existing.connected_at or datetime.now(UTC)
        existing.disconnected_at = None
        tc = existing
    else:
        tc = TenantConnector(
            tenant_id=tenant.id,
            connector_id=connector.id,
            status=TenantConnectorStatus.CONNECTED.value,
            credentials_ref={"channel_id": str(channel_id)},
            scopes_granted=[],
            config={},
            connected_at=datetime.now(UTC),
        )
        session.add(tc)
    await session.flush()
    await _write_audit(
        session,
        tenant_id=tenant.id,
        actor=actor,
        action="connector.connect_completed",
        target=f"connector:{connector_slug}",
        after={"channel_id": str(channel_id), "auth_kind": "webhook_manual"},
    )
    return tc


async def bootstrap_browser_credentials(
    session: AsyncSession,
    *,
    tenant: Tenant,
    connector_slug: str,
    tenant_credentials_id: uuid.UUID,
    context_id: str | None,
    actor: str,
) -> TenantConnector:
    """Register an existing tenant_credentials row as a connector install."""
    connector = await _load_connector_by_slug(session, connector_slug)
    if connector.auth_kind != "browser_credentials":
        msg = (
            f"connector {connector_slug} has auth_kind={connector.auth_kind!r}; "
            "bootstrap_browser_credentials requires browser_credentials"
        )
        raise IncompatibleAuthKind(msg)
    ref: dict[str, Any] = {"tenant_credentials_id": str(tenant_credentials_id)}
    if context_id:
        ref["context_id"] = context_id

    existing = await _load_tenant_connector(session, tenant.id, connector.id)
    if existing:
        existing.status = TenantConnectorStatus.CONNECTED.value
        existing.credentials_ref = ref
        existing.connected_at = existing.connected_at or datetime.now(UTC)
        existing.disconnected_at = None
        tc = existing
    else:
        tc = TenantConnector(
            tenant_id=tenant.id,
            connector_id=connector.id,
            status=TenantConnectorStatus.CONNECTED.value,
            credentials_ref=ref,
            scopes_granted=[],
            config={},
            connected_at=datetime.now(UTC),
        )
        session.add(tc)
    await session.flush()
    await _write_audit(
        session,
        tenant_id=tenant.id,
        actor=actor,
        action="connector.connect_completed",
        target=f"connector:{connector_slug}",
        after={
            "tenant_credentials_id": str(tenant_credentials_id),
            "context_id": context_id,
            "auth_kind": "browser_credentials",
        },
    )
    await auto_enable_connector_tools(
        session, tenant_id=tenant.id, connector=connector, actor=actor
    )
    return tc


async def bootstrap_api_key(
    session: AsyncSession,
    *,
    tenant: Tenant,
    connector_slug: str,
    secret_payload: dict[str, str],
    endpoint_meta: dict[str, Any],
    actor: str,
) -> TenantConnector:
    """Wire up an ``api_key`` connector by encrypting the secret in
    ``tenant_credentials`` and pointing ``tenant_connectors.credentials_ref``
    at it.

    Used by the WooCommerce wizard (first ``api_key`` consumer). The
    panel form collects the secret fields (e.g. consumer_key +
    consumer_secret) plus non-secret routing info (store_url); the
    secret bundle lands in ``encrypted_payload`` (Fernet) and the
    routing info lands in ``credentials_ref.endpoint_meta``.

    Idempotent on (tenant_id, connector.slug): if the install already
    exists, rotate the underlying tenant_credentials row and reset the
    install status to ``connected``. The previous tenant_credentials
    row (if any) is left in place — historical credentials are an
    audit signal, not garbage.
    """
    connector = await _load_connector_by_slug(session, connector_slug)
    if connector.auth_kind != "api_key":
        msg = (
            f"connector {connector_slug} has auth_kind={connector.auth_kind!r}; "
            "bootstrap_api_key requires api_key"
        )
        raise IncompatibleAuthKind(msg)
    if not secret_payload:
        msg = "secret_payload must contain at least one secret field"
        raise ValueError(msg)
    # ``tenant_credentials`` is uniqued on (tenant_id, integration). The
    # connector slug doubles as the integration key for ``api_key``
    # connectors so rotations replace the row in place.
    existing_cred = await session.scalar(
        select(TenantCredentials).where(
            TenantCredentials.tenant_id == tenant.id,
            TenantCredentials.integration == connector_slug,
        )
    )
    encrypted_bytes = json.dumps(secret_payload, separators=(",", ":")).encode("utf-8")
    if existing_cred is not None:
        existing_cred.encrypted_payload = encrypted_bytes
        existing_cred.needs_reauth = False
        cred_row = existing_cred
    else:
        cred_row = TenantCredentials(
            tenant_id=tenant.id,
            integration=connector_slug,
            encrypted_payload=encrypted_bytes,
            needs_reauth=False,
        )
        session.add(cred_row)
    await session.flush()

    ref: dict[str, Any] = {
        "tenant_credentials_id": str(cred_row.id),
        "endpoint_meta": dict(endpoint_meta),
    }
    existing = await _load_tenant_connector(session, tenant.id, connector.id)
    if existing:
        existing.status = TenantConnectorStatus.CONNECTED.value
        existing.credentials_ref = ref
        existing.connected_at = existing.connected_at or datetime.now(UTC)
        existing.disconnected_at = None
        tc = existing
    else:
        tc = TenantConnector(
            tenant_id=tenant.id,
            connector_id=connector.id,
            status=TenantConnectorStatus.CONNECTED.value,
            credentials_ref=ref,
            scopes_granted=[],
            config={},
            connected_at=datetime.now(UTC),
        )
        session.add(tc)
    await session.flush()
    await _write_audit(
        session,
        tenant_id=tenant.id,
        actor=actor,
        action="connector.connect_completed",
        target=f"connector:{connector_slug}",
        after={
            "tenant_credentials_id": str(cred_row.id),
            "endpoint_meta": dict(endpoint_meta),
            "auth_kind": "api_key",
        },
    )
    await auto_enable_connector_tools(
        session, tenant_id=tenant.id, connector=connector, actor=actor
    )
    return tc


async def disconnect_connector(
    session: AsyncSession,
    *,
    tenant: Tenant,
    connector_slug: str,
    composio: ComposioClientProtocol | None,
    actor: str,
) -> TenantConnector:
    connector = await _load_connector_by_slug(session, connector_slug)
    tc = await _load_tenant_connector(session, tenant.id, connector.id)
    if tc is None:
        msg = f"tenant {tenant.slug} has no install of {connector_slug}"
        raise ConnectorNotFound(msg)
    if tc.status == TenantConnectorStatus.DISCONNECTED.value:
        return tc  # idempotent

    # OAuth — try to revoke upstream. Failures don't block disconnect.
    if (
        connector.auth_kind == "oauth_composio"
        and composio is not None
        and (cid := tc.credentials_ref.get("composio_connection_id"))
    ):
        try:
            await composio.revoke_account(cid)
        except (ComposioError, ComposioUnavailable, ComposioNotFound):
            counters.incr(f"connector.disconnect.upstream_revoke_failed:{connector_slug}")

    before_status = tc.status
    tc.status = TenantConnectorStatus.DISCONNECTED.value
    tc.disconnected_at = datetime.now(UTC)
    await session.flush()
    await _write_audit(
        session,
        tenant_id=tenant.id,
        actor=actor,
        action="connector.disconnect",
        target=f"connector:{connector_slug}",
        before={"status": before_status},
        after={"status": tc.status},
    )
    counters.incr(f"connector.disconnect:{connector_slug}")
    return tc


async def reissue_consent(
    session: AsyncSession,
    *,
    tenant: Tenant,
    connector_slug: str,
    consent_secret: str,
    actor: str,
) -> str:
    """Rotate the consent token on a pending tenant_connector.

    Returns the new token. Does NOT re-call Composio — the connection_id
    stays the same; only our magic-link expires.
    """
    connector = await _load_connector_by_slug(session, connector_slug)
    tc = await _load_tenant_connector(session, tenant.id, connector.id)
    if tc is None:
        msg = f"tenant {tenant.slug} has no install of {connector_slug}"
        raise ConnectorNotFound(msg)
    if tc.status == TenantConnectorStatus.CONNECTED.value:
        msg = f"connector {connector_slug} already connected for {tenant.slug}"
        raise ConnectorAlreadyConnected(msg)
    new_token, payload = sign_consent_token(
        tenant_id=tenant.id, connector_id=connector.id, secret=consent_secret
    )
    tc.consent_token = new_token
    tc.consent_token_expires_at = payload.expires_at
    tc.status = TenantConnectorStatus.PENDING.value
    await session.flush()
    await _write_audit(
        session,
        tenant_id=tenant.id,
        actor=actor,
        action="connector.consent_reissued",
        target=f"connector:{connector_slug}",
        after={"expires_at": payload.expires_at.isoformat()},
    )
    counters.incr(f"connector.consent.reissued:{connector_slug}")
    return new_token


async def upsert_override(
    session: AsyncSession,
    *,
    tenant: Tenant,
    tool_name: str,
    mode: ConnectorToolMode,
    reason: str | None,
    actor: str,
) -> TenantConnectorToolOverride:
    # Verify the tool exists.
    tool = await session.scalar(select(ToolCatalog).where(ToolCatalog.name == tool_name))
    if tool is None:
        from .gating import ToolNotInCatalog

        msg = f"tool not in catalog: {tool_name!r}"
        raise ToolNotInCatalog(msg)

    existing = await session.scalar(
        select(TenantConnectorToolOverride).where(
            TenantConnectorToolOverride.tool_name == tool_name
        )
    )
    before = {"mode": existing.mode, "reason": existing.reason} if existing else None
    if existing is None:
        existing = TenantConnectorToolOverride(
            tenant_id=tenant.id,
            tool_name=tool_name,
            mode=mode.value,
            reason=reason,
            set_by_actor=actor,
        )
        session.add(existing)
    else:
        existing.mode = mode.value
        existing.reason = reason
        existing.set_by_actor = actor
    await session.flush()
    await _write_audit(
        session,
        tenant_id=tenant.id,
        actor=actor,
        action="connector.override_upsert",
        target=f"tool:{tool_name}",
        before=before,
        after={"mode": mode.value, "reason": reason},
    )
    return existing


async def delete_override(
    session: AsyncSession,
    *,
    tenant: Tenant,
    tool_name: str,
    actor: str,
) -> bool:
    existing = await session.scalar(
        select(TenantConnectorToolOverride).where(
            TenantConnectorToolOverride.tool_name == tool_name
        )
    )
    if existing is None:
        return False
    before = {"mode": existing.mode, "reason": existing.reason}
    await session.delete(existing)
    await session.flush()
    await _write_audit(
        session,
        tenant_id=tenant.id,
        actor=actor,
        action="connector.override_delete",
        target=f"tool:{tool_name}",
        before=before,
        after={},
    )
    return True


__all__ = [
    "CompleteConsentResult",
    "ConnectorAlreadyConnected",
    "ConnectorNotConfigured",
    "ConnectorNotFound",
    "IncompatibleAuthKind",
    "InitiateConsentResult",
    "SyncToolsResult",
    "bootstrap_browser_credentials",
    "bootstrap_webhook_manual",
    "complete_consent_from_webhook",
    "delete_override",
    "disconnect_connector",
    "initiate_consent",
    "reissue_consent",
    "sync_tools_for",
    "upsert_override",
]
