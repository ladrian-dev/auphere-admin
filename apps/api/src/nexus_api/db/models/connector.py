"""ORM models for the Connectors module (Block L).

- ``Connector``      — global catalog row (no RLS).
- ``TenantConnector`` — per-tenant install (RLS+FORCE).
- ``TenantConnectorToolOverride`` — per-tenant per-tool gating (RLS+FORCE).

The runtime gating tri-state is kept in a plain ``String(20)`` column with a
``CHECK`` constraint (mode in {always, blocked, needs_approval}) instead of a
PG enum, so adding a fourth state in Phase 4+ does not need a migration with
``ALTER TYPE ... ADD VALUE`` and the surrounding autocommit dance.

Status enums on ``Connector.status`` and ``TenantConnector.status`` follow the
same convention. Defense in depth: Pydantic schemas at the API boundary
re-validate the string against the same canonical sets.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import TimestampMixin, UUIDPrimaryKey


class ConnectorAuthKind(str, enum.Enum):
    """Authentication mechanism a connector uses to talk to the upstream service.

    Kept as a Python enum + DB CHECK constraint (not a PG enum) so adding a
    new auth_kind in Phase 4+ is an ALTER TABLE check, not an ALTER TYPE.
    """

    OAUTH_COMPOSIO = "oauth_composio"
    BROWSER_CREDENTIALS = "browser_credentials"
    WEBHOOK_MANUAL = "webhook_manual"
    API_KEY = "api_key"


class ConnectorStatus(str, enum.Enum):
    AVAILABLE = "available"
    BETA = "beta"
    DEPRECATED = "deprecated"


class TenantConnectorStatus(str, enum.Enum):
    """Lifecycle of a single install.

    Transitions allowed (validated in the status machine):
        pending     → connected | partial | error
        connected   → needs_reauth | disconnected | partial | paused
        partial     → connected | needs_reauth | disconnected | paused
        needs_reauth → connected | disconnected | paused
        paused      → connected | disconnected
        disconnected → (terminal; new install requires a new row)
        error       → (terminal; manual operator intervention)

    ``paused`` (M.6) keeps the upstream tokens + sync metadata intact but
    the runtime skips the connector — used when the operator wants to
    temporarily silence a connector without losing the grant. Reversible.
    """

    PENDING = "pending"
    CONNECTED = "connected"
    PARTIAL = "partial"
    NEEDS_REAUTH = "needs_reauth"
    PAUSED = "paused"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class ConnectorToolMode(str, enum.Enum):
    """Per-tool gating mode.

    Phase 1 runtime only consumes ALWAYS and BLOCKED. NEEDS_APPROVAL is
    schema-ready for Phase 4+; at runtime in Phase 1 it is treated as
    BLOCKED with a dedicated counter (so the eventual switch-over does
    not require a migration nor a data backfill).
    """

    ALWAYS = "always"
    BLOCKED = "blocked"
    NEEDS_APPROVAL = "needs_approval"


class Connector(UUIDPrimaryKey, TimestampMixin, Base):
    """Global catalog of available connectors.

    Seeded from YAML in
    ``apps/api/src/nexus_api/services/connectors/seeds/*.yaml``. Re-runs of
    the seed loader are idempotent (``ON CONFLICT (slug) DO UPDATE`` on
    every field except ``auth_kind``, which is treated as immutable —
    a change there means a new connector).
    """

    __tablename__ = "connectors"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_connectors_slug"),
        CheckConstraint(
            "auth_kind IN ('oauth_composio', 'browser_credentials', 'webhook_manual', 'api_key')",
            name="ck_connectors_auth_kind",
        ),
        CheckConstraint(
            "status IN ('available', 'beta', 'deprecated')",
            name="ck_connectors_status",
        ),
    )

    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    vendor: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    capabilities: Mapped[list[str]] = mapped_column(ARRAY(String(40)), nullable=False, default=list)
    auth_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    mcp_server_ref: Mapped[str] = mapped_column(String(120), nullable=False)
    provider_meta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    auto_enable_on_connect: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    auto_enable_destructive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    consent_link_template_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ConnectorStatus.AVAILABLE.value
    )


class TenantConnector(UUIDPrimaryKey, TimestampMixin, Base):
    """One row per (tenant, connector) install.

    The runtime resolves ``mcp_server_ref`` + ``auth_kind`` from the
    ``Connector`` row and reads credentials from one of three places
    depending on ``auth_kind``:

    - ``oauth_composio`` → ``credentials_ref.composio_connection_id``
      identifies the connected account in Composio. The Composio adapter
      passes it on every tools.execute call along with
      ``user_id = f"tenant_{tenant.slug}"``.
    - ``browser_credentials`` → ``credentials_ref.tenant_credentials_id``
      points to a row in the existing ``tenant_credentials`` table
      (Fernet vault, ADR-006). AgendaPro and similar.
    - ``webhook_manual`` → ``credentials_ref.channel_id`` points to a row
      in ``channels``. WhatsApp YCloud.
    - ``api_key`` → ``credentials_ref.secret_ref`` is a Doppler path.

    The tenant_id column is NOT declared via TenantScopedMixin because the
    column ordering ends up the same and we want the ForeignKey on
    tenant_id (the mixin doesn't add an FK).
    """

    __tablename__ = "tenant_connectors"
    __table_args__ = (
        UniqueConstraint("tenant_id", "connector_id", name="uq_tc_tenant_connector"),
        CheckConstraint(
            "status IN ('pending', 'connected', 'partial', 'needs_reauth', "
            "'paused', 'disconnected', 'error')",
            name="ck_tc_status",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT", name="fk_tc_tenant"),
        nullable=False,
    )
    connector_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("connectors.id", ondelete="RESTRICT", name="fk_tc_connector"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    credentials_ref: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    scopes_granted: Mapped[list[str]] = mapped_column(
        ARRAY(String(120)), nullable=False, default=list
    )
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    last_health_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consent_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    consent_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class TenantConnectorToolOverride(UUIDPrimaryKey, TimestampMixin, Base):
    """Optional per-(tenant, tool) gating override.

    When present, ``mode`` overrides the connector's ``default_mode`` for
    this tool in this tenant only. Used by the operator to:
    - Block a tool that auto-enabled on consent but shouldn't run yet
      (e.g. a destructive write while the tenant is in soak period).
    - Promote a tool from ``blocked`` to ``always`` once the operator
      reviews the first executions.
    - Future (Phase 4+): set ``needs_approval`` for human-in-loop.
    """

    __tablename__ = "tenant_connector_tool_overrides"
    __table_args__ = (
        UniqueConstraint("tenant_id", "tool_name", name="uq_tcto_tenant_tool"),
        CheckConstraint(
            "mode IN ('always', 'blocked', 'needs_approval')",
            name="ck_tcto_mode",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT", name="fk_tcto_tenant"),
        nullable=False,
    )
    tool_name: Mapped[str] = mapped_column(
        String(120),
        ForeignKey("tool_catalog.name", ondelete="RESTRICT", name="fk_tcto_tool"),
        nullable=False,
    )
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    set_by_actor: Mapped[str] = mapped_column(String(120), nullable=False)


__all__ = [
    "Connector",
    "ConnectorAuthKind",
    "ConnectorStatus",
    "ConnectorToolMode",
    "TenantConnector",
    "TenantConnectorStatus",
    "TenantConnectorToolOverride",
]
