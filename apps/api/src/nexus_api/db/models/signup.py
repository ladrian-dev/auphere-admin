"""Solicitudes de alta de partner (migración 0118, spec 006).

Una fila aquí es **un correo que pidió cuenta y todavía no la tiene**. Es lo
único que existe antes de verificar, y se extingue al completarse el alta o al
caducar.

Tabla de PLATAFORMA: sin ``tenant_id``, sin RLS, mismo modelo de confianza que
``partners`` y ``partner_invitations``. Que no lleve ``tenant_id`` es la
afirmación, no la omisión — no hay tenant al que pertenecer.

**No lleva ``partner_id``, y no puede llevarlo:** el partner no existe hasta que
alguien completa el alta. Ésa es toda la razón por la que esto es una tabla
propia y no una columna en otra.

Del token se guarda **solo** el SHA-256. El claro se enseña una vez, dentro del
enlace, y no se escribe en ningún registro ni traza — mismo patrón que
``partner_invitations`` y ``console_auth.principal_sessions``.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import TimestampMixin, UUIDPrimaryKey


class SignupStatus(str, enum.Enum):
    PENDING = "pending"
    CONSUMED = "consumed"
    EXPIRED = "expired"
    REVOKED = "revoked"


SIGNUP_STATUSES: tuple[str, ...] = tuple(s.value for s in SignupStatus)


class SignupProvider(str, enum.Enum):
    """De dónde vino la solicitud. ``None`` es «por contraseña»."""

    GOOGLE = "google"


class SignupRequest(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "signup_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'consumed', 'expired', 'revoked')",
            name="ck_signup_requests_status",
        ),
        CheckConstraint(
            "provider IS NULL OR provider IN ('google')",
            name="ck_signup_requests_provider",
        ),
        Index("uq_signup_requests_token_hash", "token_hash", unique=True),
        Index(
            "ix_signup_requests_email_pending",
            text("lower(email)"),
            postgresql_where=text("status = 'pending'"),
        ),
        Index(
            "ix_signup_requests_expires",
            "expires_at",
            postgresql_where=text("status = 'pending'"),
        ),
    )

    #: Siempre en minúsculas — lo normaliza el servicio, lo aprovecha el índice.
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    #: SHA-256 hex. Nunca sale en una respuesta ni entra en un log.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=SignupStatus.PENDING.value,
        server_default=SignupStatus.PENDING.value,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: La vía de entrada que el operador ve. ``None`` = por contraseña.
    provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    #: SHA-256 de la IP: se puede investigar un abuso sin guardar el dato en
    #: claro. Una IP es un dato personal; su hash sigue sirviendo para
    #: correlacionar, que es para lo único que se quiere.
    created_ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<SignupRequest {self.email} {self.status}>"
