"""La persona de un cliente — spec 030 (migración 0147).

Tres tablas hermanas de las del partner y **separadas de ellas a propósito**
(plan D1): un usuario de cliente no es un rol más de ``partner_memberships``,
porque hoy hay código que recorre los miembros del partner y cada sitio
tendría que acordarse de excluirlo. Aquí, lo que existe sigue siendo correcto
sin tocarlo.

- :class:`ClientAccess` — si el cliente tiene consola lite y qué módulos.
- :class:`ClientMembership` — una cuenta de consola atada a UN tenant.
- :class:`ClientInvitation` — el enlace de un solo uso, guardado como hash.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timedelta

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import TimestampMixin, UUIDPrimaryKey


class ClientModule(str, enum.Enum):
    """Los módulos que Auphere elige para un cliente, en el orden en que la
    barra lateral los enseña."""

    PANEL = "panel"
    INBOX = "inbox"
    USAGE = "usage"


#: Orden canónico: el de la barra lateral (Panel, Bandeja de entrada, Consumo).
CLIENT_MODULES: tuple[str, ...] = tuple(m.value for m in ClientModule)


class ClientMemberStatus(str, enum.Enum):
    ACTIVE = "active"
    REVOKED = "revoked"


class ClientInvitationStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"
    EXPIRED = "expired"


#: Lo que dura un enlace de invitación: lo mismo que el del partner.
CLIENT_INVITATION_TTL = timedelta(days=21)


class ClientAccess(TimestampMixin, Base):
    __tablename__ = "client_access"
    __table_args__ = (
        CheckConstraint(
            "modules <@ ARRAY['panel','inbox','usage']::varchar[]",
            name="ck_client_access_modules",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("partners.id", ondelete="CASCADE"), nullable=False
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    modules: Mapped[list[str]] = mapped_column(
        ARRAY(String(16)), nullable=False, default=list, server_default=text("'{}'")
    )
    updated_by: Mapped[str | None] = mapped_column(String(320), nullable=True)

    def ordered_modules(self) -> tuple[str, ...]:
        """Los módulos del cliente en el orden de la barra, sin repetidos."""
        have = set(self.modules or [])
        return tuple(m for m in CLIENT_MODULES if m in have)


class ClientMembership(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "client_memberships"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'revoked')", name="ck_client_memberships_status"),
        # Una cuenta, un cliente. Y nunca a la vez de un partner: eso lo
        # comprueba el servicio (no se puede declarar entre dos tablas).
        Index("uq_client_memberships_user", "user_id", unique=True),
        Index("ix_client_memberships_tenant", "tenant_id"),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("partners.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    # Id de la cuenta (``console_auth.principals``), por valor como en el partner.
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ClientMemberStatus.ACTIVE.value,
        server_default="active",
    )
    invited_by: Mapped[str | None] = mapped_column(String(320), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<ClientMembership {self.email} {self.status}@{self.tenant_id}>"


class ClientInvitation(UUIDPrimaryKey, Base):
    __tablename__ = "client_invitations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'accepted', 'revoked', 'expired')",
            name="ck_client_invitations_status",
        ),
        Index(
            "uq_client_invitations_pending_email",
            "tenant_id",
            "email",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_client_invitations_tenant", "tenant_id"),
    )

    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("partners.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    # Siempre en minúsculas; se compara en minúsculas al aceptar.
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # SHA-256 del token en claro. Un volcado de la tabla no abre ninguna puerta.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ClientInvitationStatus.PENDING.value,
        server_default="pending",
    )
    invited_by: Mapped[str | None] = mapped_column(String(320), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_membership_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("client_memberships.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<ClientInvitation {self.email} {self.status}>"
