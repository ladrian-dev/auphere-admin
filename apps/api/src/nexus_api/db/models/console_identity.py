"""Identidad de la consola de partners (migración 0088).

La consola ya no tiene base de datos: usuarios, contraseñas y sesiones
viven aquí y el BFF solo guarda una cookie con un token opaco. Ver el
docstring de ``alembic/versions/0088_console_identity.py`` para el porqué.

Dos tablas de PLATAFORMA en el esquema ``console_auth`` (sin ``tenant_id``,
sin RLS — mismo modelo de confianza que ``partners``):

- :class:`ConsoleAccount` → ``console_auth.principals``. Los nombres no
  coinciden a propósito: la tabla se llama ``principals`` porque es lo que
  es en el vocabulario del backend (``core/console_auth.ConsolePrincipal``),
  y la clase se llama ``ConsoleAccount`` para que leer código donde
  conviven ambas no sea un acertijo.
- :class:`ConsoleSession` → ``console_auth.principal_sessions``.

Ninguna de las dos guarda un secreto en claro: la contraseña es un hash
scrypt con sal (``services/console_identity.py``) y de la sesión solo se
guarda el SHA-256 del token.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base

CONSOLE_AUTH_SCHEMA = "console_auth"


class ConsoleAccount(Base):
    """Una persona que entra en la consola de un partner.

    ``id`` es el ``user_id`` textual de ``public.partner_memberships``: la
    pertenencia sigue siendo esa tabla (0080) y sigue sin FK, porque el
    esquema de identidad puede vivir en otra base el día que haga falta.
    """

    __tablename__ = "principals"
    __table_args__ = (
        Index("uq_console_principals_email", text("lower(email)"), unique=True),
        {"schema": CONSOLE_AUTH_SCHEMA},
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
    #: Intentos fallidos consecutivos; se pone a cero al acertar.
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    #: Mientras esté en el futuro, ninguna contraseña abre la cuenta. La
    #: respuesta es idéntica al 401 normal: el bloqueo no se revela.
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<ConsoleAccount {self.email}>"


class ConsoleSession(Base):
    """Sesión de consola. La PK es el hash del token: buscar una sesión es
    un índice único sobre 64 caracteres, y un volcado de la tabla no
    permite entrar en ninguna cuenta (mismo patrón que ``api_keys``)."""

    __tablename__ = "principal_sessions"
    __table_args__ = (
        Index("ix_console_sessions_principal", "principal_id"),
        Index("ix_console_sessions_expires", "expires_at"),
        {"schema": CONSOLE_AUTH_SCHEMA},
    )

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    principal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{CONSOLE_AUTH_SCHEMA}.principals.id", ondelete="CASCADE"),
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
        return f"<ConsoleSession {self.principal_id}>"
