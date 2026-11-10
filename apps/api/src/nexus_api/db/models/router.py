"""El catálogo certificado y el router — spec 047, ola 6 (migración 0180,
``data-model.md`` §8, ``contracts/router-and-catalog.md``).

Una fila de ``model_profiles`` es un **despliegue** (ADR-036). Alrededor:

- de plataforma, sin datos de clientes y escritas solo por el admin:
  ``model_prices`` (con vigencia), ``router_taxonomy`` (versionada),
  ``router_profiles`` (la política por tarea de cada perfil, versionada) y
  ``model_task_certifications`` (despliegue y tarea);
- por cliente, con RLS FORCE y FK compuestas: ``agent_model_certifications``
  (despliegue y agente) y ``router_anomalies``.

Las decisiones del router no tienen tabla: van al log (``llm.route_decision``),
y ``usage_records.route_decision_id`` las enlaza.
"""

from __future__ import annotations

import decimal
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import UUIDPrimaryKey

#: ``model_profiles.status``. ``deprecated`` es el de antes de la 047; pasa a
#: ``retiring`` cuando el router sea el único lector.
DEPLOYMENT_STATUSES: tuple[str, ...] = (
    "draft",
    "certifying",
    "active",
    "retiring",
    "retired",
    "unavailable",
    "deprecated",
)
RESIDENCIES: tuple[str, ...] = ("eu", "us", "global")
ROUTER_PROFILES: tuple[str, ...] = ("auto", "economy", "balanced", "max", "platform")
ANOMALY_KINDS: tuple[str, ...] = ("reserve_model", "no_model", "cooldown", "missing_task")
#: Quién paga una certificación por agente (``router-and-catalog.md`` §5.2).
CERTIFICATION_PAYERS: tuple[str, ...] = ("partner", "auphere")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


_PRICE = Numeric(12, 6)


class ModelPrice(Base):
    """Un precio con su vigencia. El de hoy es el de mayor ``valid_from`` ≤ hoy."""

    __tablename__ = "model_prices"

    deployment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("model_profiles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    valid_from: Mapped[date] = mapped_column(Date, primary_key=True)
    unit: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="per_million_tokens",
        server_default="per_million_tokens",
    )
    input: Mapped[decimal.Decimal | None] = mapped_column(_PRICE, nullable=True)
    cache_read: Mapped[decimal.Decimal | None] = mapped_column(_PRICE, nullable=True)
    cache_write: Mapped[decimal.Decimal | None] = mapped_column(_PRICE, nullable=True)
    output: Mapped[decimal.Decimal | None] = mapped_column(_PRICE, nullable=True)
    audio_minute: Mapped[decimal.Decimal | None] = mapped_column(_PRICE, nullable=True)
    image: Mapped[decimal.Decimal | None] = mapped_column(_PRICE, nullable=True)
    #: p. ej. ``{"above_tokens": 100000, "multiplier": 5, "applies_to": "whole_request"}``.
    surcharge: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="USD", server_default="USD"
    )
    created_at: Mapped[datetime] = _now()


class RouterTaxonomy(Base):
    """Las tareas del router. Una tarea nueva es una versión nueva."""

    __tablename__ = "router_taxonomy"
    __table_args__ = (CheckConstraint("version >= 1", name="ck_router_taxonomy_version"),)

    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    #: ``[{"code", "conversation", "needs"}]``.
    tasks: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = _now()


class RouterProfile(Base):
    """La política por tarea de un perfil (``router-and-catalog.md`` §3), versionada."""

    __tablename__ = "router_profiles"
    __table_args__ = (
        CheckConstraint(f"profile IN ({_in(ROUTER_PROFILES)})", name="ck_router_profiles_profile"),
        CheckConstraint("version >= 1", name="ck_router_profiles_version"),
    )

    profile: Mapped[str] = mapped_column(String(16), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    published_by: Mapped[str] = mapped_column(String(160), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime] = _now()


class ModelTaskCertification(Base):
    """Certificación por clase: despliegue, tarea y versión de la batería.

    Caduca al cambiar el modelo, el proveedor, la región, la cuantización o la
    batería. Un cambio de precio no la caduca.
    """

    __tablename__ = "model_task_certifications"
    __table_args__ = (
        CheckConstraint("quality BETWEEN 0 AND 1", name="ck_model_task_cert_quality"),
    )

    deployment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("model_profiles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    task: Mapped[str] = mapped_column(String(32), primary_key=True)
    battery_version: Mapped[int] = mapped_column(Integer, primary_key=True)
    scores: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    quality: Mapped[decimal.Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    certified_at: Mapped[datetime] = _now()
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentModelCertification(UUIDPrimaryKey, Base):
    """Certificación por agente: la suite del agente con ese despliegue
    (``router-and-catalog.md`` §5.2). Por cliente; garantía 9: el router de un
    agente no elige con la certificación de su hermano."""

    __tablename__ = "agent_model_certifications"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_agent_model_cert_tenant_id"),
        CheckConstraint(
            f"paid_by IN ({_in(CERTIFICATION_PAYERS)})", name="ck_agent_model_cert_paid_by"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "agent_id"],
            ["agents.tenant_id", "agents.id"],
            name="fk_agent_model_cert_agent",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "agent_config_id"],
            ["agent_configs.tenant_id", "agent_configs.id"],
            name="fk_agent_model_cert_version",
            ondelete="CASCADE",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    deployment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_profiles.id", ondelete="CASCADE"), nullable=False
    )
    agent_config_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    suite_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    paid_by: Mapped[str] = mapped_column(String(16), nullable=False)
    certified_at: Mapped[datetime] = _now()
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RouterAnomaly(UUIDPrimaryKey, Base):
    """Lo que Auphere tiene que mirar: el modelo de reserva, ningún modelo
    posible, un enfriamiento (requisito 40.7)."""

    __tablename__ = "router_anomalies"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_router_anomalies_tenant_id"),
        CheckConstraint(f"kind IN ({_in(ANOMALY_KINDS)})", name="ck_router_anomalies_kind"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    task: Mapped[str] = mapped_column(String(32), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    decision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = _now()
