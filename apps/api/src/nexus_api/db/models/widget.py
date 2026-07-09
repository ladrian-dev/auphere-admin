"""Web chat widget config (migration 0050).

A ``tenant_widget_config`` turns on the public web chat widget for one
tenant and holds everything the browser needs to talk to that tenant's
agent: the public site key, the origin allow-list, and cosmetic bits
(greeting / appearance).

This is a PLATFORM table — NOT tenant-scoped, no RLS — following the same
trust model as ``partners``/``partner_tenants``: the ``public_key`` →
``tenant_id`` lookup happens in ``POST /v1/widget/session`` BEFORE any
tenant scope exists, exactly like ``partner_tenants`` resolves a session's
tenant. The resolved ``tenant_id`` is then baked into the signed widget
JWT and every downstream request reads it exclusively from those claims —
never from browser input — which plugs into ``SET LOCAL app.tenant_id`` +
RLS on the message/conversation tables.

Unlike the partner platform, there is no reseller layer: Barber Supply is
a direct Auphere tenant with its own website, and its visitors are
anonymous (no ``external_client_ref``). The ``public_key`` is a public,
non-secret site key (Stripe publishable-key / Intercom app-id analog); the
real gate is the origin allow-list + the short-lived JWT + RLS.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import TimestampMixin, UUIDPrimaryKey


class TenantWidgetConfig(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "tenant_widget_configs"

    # One config per tenant. FK CASCADE: deleting a tenant removes its
    # widget config. Not the primary key so the row keeps its own stable id.
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    # Public, non-secret site key embedded in the ``<script>`` snippet
    # (``wgt_pub_…``). UNIQUE → O(1) lookup on session mint.
    public_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # Origins allowed to open a widget session for this tenant. Enforced
    # server-side at session mint AND on every message request; also copied
    # into the JWT claims so the token is bound to one origin.
    allowed_origins: Mapped[list[str]] = mapped_column(
        ARRAY(String(255)),
        nullable=False,
        server_default=text("ARRAY[]::varchar[]"),
    )
    # First bubble shown when the panel opens (before the visitor types).
    greeting: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Cosmetic knobs the loader reads: ``{"title","accent_color","logo_url"}``.
    appearance: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    # Kill switch. A disabled config refuses new sessions AND fails-closed
    # on live tokens (re-checked per request), mirroring key revocation.
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<TenantWidgetConfig tenant={self.tenant_id} enabled={self.enabled}>"
