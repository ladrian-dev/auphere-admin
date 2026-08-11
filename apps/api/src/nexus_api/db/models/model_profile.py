"""Catálogo de modelos y elección por tenant (WP-19, plataforma v2).

Dos tablas con dueños distintos:

- ``ModelProfile`` es **catálogo de plataforma**: qué modelos existen, qué
  cuestan y qué saben hacer. Sin ``tenant_id`` y sin RLS — es igual para
  todos. Que el precio viva aquí y no en el código es el punto: cuando un
  proveedor cambia tarifas, se actualiza una fila y el consumo de la hora
  siguiente ya se valora bien, sin despliegue.
- ``TenantModelBinding`` es **la elección de un cliente**: qué modelo usa
  para cada rol. Con RLS forzada, porque saber en qué modelo corre otro
  cliente es información suya, no nuestra.

El precio se guarda por millón de tokens (no por token) porque es la
unidad en la que lo publican los proveedores: convertir al leer evita que
alguien copie mal un número al escribirlo.
"""

from __future__ import annotations

import decimal
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base


class ModelProfile(Base):
    """Un modelo del catálogo, con su tarifa y sus capacidades."""

    __tablename__ = "model_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )

    provider: Mapped[str] = mapped_column(Text, nullable=False)

    # El identificador de LiteLLM VERBATIM (``anthropic/claude-sonnet-4-6``),
    # que es la misma cadena que el emisor de consumo guarda en
    # ``usage_records.model``. Único por sí solo: el que factura busca por
    # esta cadena sin saber el proveedor, y dos filas iguales harían que el
    # precio de un turno dependiera del orden de lectura.
    model_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)

    # Tarifas por millón de tokens. NULL = modelo sin tarifa cargada; su
    # consumo se cuenta y queda sin precio, en vez de valorarse a cero.
    price_input_per_mtok: Mapped[decimal.Decimal | None] = mapped_column(
        Numeric(12, 6), nullable=True
    )
    price_output_per_mtok: Mapped[decimal.Decimal | None] = mapped_column(
        Numeric(12, 6), nullable=True
    )
    price_cache_read_per_mtok: Mapped[decimal.Decimal | None] = mapped_column(
        Numeric(12, 6), nullable=True
    )
    price_cache_write_per_mtok: Mapped[decimal.Decimal | None] = mapped_column(
        Numeric(12, 6), nullable=True
    )
    # Voz (STT/TTS): se factura por minuto, no por token.
    price_per_minute: Mapped[decimal.Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)

    max_context: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Prefijo mínimo cacheable del proveedor. Por debajo de este número NO
    # se cachea y NO se devuelve error: el ahorro simplemente no aparece.
    # Varía por generación (512 / 1024 / 4096), así que el mismo prompt de
    # 3k cachea en un modelo y no en otro.
    cache_min_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    supports_tools: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    supports_vision: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    # Residencia de datos — un cliente con exigencia de región solo puede
    # atarse a perfiles compatibles.
    region: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ``active`` | ``deprecated``. Un perfil deprecado sigue existiendo
    # (hay consumo histórico que valorar) pero no debería ofrecerse en el
    # selector del panel.
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'active'"))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class TenantModelBinding(Base):
    """Qué modelo usa un tenant para un rol concreto."""

    __tablename__ = "tenant_model_bindings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )

    role: Mapped[str] = mapped_column(Text, nullable=False)

    # RESTRICT y no CASCADE: retirar un perfil del catálogo no puede dejar
    # a un tenant sin modelo para un rol sin que nadie se entere.
    model_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_profiles.id", ondelete="RESTRICT"), nullable=False
    )

    # Lista ordenada de ``model_id`` a los que caer si el primario falla.
    # Se guardan como cadenas y no como FKs a propósito: la cadena de
    # respaldo tiene que seguir funcionando aunque una de sus entradas
    # desaparezca del catálogo — un fallback que revienta al resolverse no
    # es un fallback.
    fallback_chain: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )

    # Techo de coste por turno. NULL = sin techo; el corte real es WP-20.
    max_cost_per_turn_usd: Mapped[decimal.Decimal | None] = mapped_column(
        Numeric(12, 6), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


# Roles con binding propio. Lista y no enum de Postgres por el mismo
# motivo que ``USAGE_METERS``: añadir un rol no debe exigir migración.
# El CHECK de la tabla sí los fija, para que un typo no cree un rol
# fantasma que nunca resuelve.
MODEL_ROLES: frozenset[str] = frozenset(
    {
        "classify",
        "respond",
        "grade",
        "improve",
        "voice_llm",
        "voice_stt",
        "voice_tts",
    }
)
