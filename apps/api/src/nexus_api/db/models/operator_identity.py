"""Identidad del panel de operador (migración 0089, ADR-034).

Gemela de ``console_identity.py`` y por el mismo motivo: el panel deja de
tener base de datos: usuarios, contraseñas y sesiones viven aquí y el BFF
de ``apps/admin`` solo guarda una cookie con un token opaco.

Dos tablas de PLATAFORMA en el esquema ``operator_auth`` (sin ``tenant_id``,
sin RLS — mismo modelo de confianza que ``partners``):

- :class:`OperatorAccount`  → ``operator_auth.principals``
- :class:`OperatorSession`  → ``operator_auth.principal_sessions``

**Esquema separado del de la consola a propósito.** Los principals de
``console_auth`` son gente de los partners; estos son personal de Auphere
con acceso transversal. Dos tablas hacen imposible que una fila mal
etiquetada convierta a un partner en operador.

Ninguna de las dos guarda un secreto en claro: la contraseña es un hash
scrypt con sal (``services/identity.py``) y de la sesión solo se guarda el
SHA-256 del token.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base

OPERATOR_AUTH_SCHEMA = "operator_auth"


class OperatorAccount(Base):
    """Una persona del equipo de Auphere que entra en el panel.

    ``id`` viaja como texto en ``X-Operator-Id`` hacia los endpoints del QA
    Playground, que aíslan por ``app.operator_id`` (TEXT). Antes ese valor
    era el id cuid de Better Auth; ahora es este UUID en forma de cadena.
    """

    __tablename__ = "principals"
    __table_args__ = (
        Index("uq_operator_principals_email", text("lower(email)"), unique=True),
        CheckConstraint(
            "role IN ('admin', 'qa_operator', 'viewer')",
            name="ck_operator_principals_role",
        ),
        {"schema": OPERATOR_AUTH_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    #: Siempre en minúsculas — lo normaliza el servicio, lo impone el índice.
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    #: ``scrypt$n$r$p$<salt_b64>$<hash_b64>``. Nunca sale en una respuesta.
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    locale: Mapped[str] = mapped_column(String(5), nullable=False, server_default="es")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: El rol que gatea el QA Playground, portado de ``auth.user.role``. NO
    #: decide qué se puede tocar en ``/admin/*``: el panel sigue siendo
    #: god-mode por ADR-009.
    role: Mapped[str] = mapped_column(String(32), nullable=False, server_default="qa_operator")
    #: Intentos fallidos consecutivos; se pone a cero al acertar.
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    #: Mientras esté en el futuro, ninguna contraseña abre la cuenta. La
    #: respuesta es idéntica al 401 normal: el bloqueo no se revela.
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Revocación permanente sin borrar la fila, para que el rastro de
    #: ``audit_log`` siga resolviendo a alguien. Distinta de ``locked_until``,
    #: que es temporal y automática.
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<OperatorAccount {self.email}>"


class OperatorSession(Base):
    """Sesión del panel. La PK es el hash del token: buscar una sesión es un
    índice único sobre 64 caracteres, y un volcado de la tabla no permite
    entrar en ninguna cuenta (mismo patrón que ``api_keys``)."""

    __tablename__ = "principal_sessions"
    __table_args__ = (
        Index("ix_operator_sessions_principal", "principal_id"),
        Index("ix_operator_sessions_expires", "expires_at"),
        {"schema": OPERATOR_AUTH_SCHEMA},
    )

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    principal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{OPERATOR_AUTH_SCHEMA}.principals.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    #: Caducidad absoluta (no se renueva): 7 días desde el login.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<OperatorSession {self.principal_id}>"
