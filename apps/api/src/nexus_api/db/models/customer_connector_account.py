"""El vínculo de un cliente final con su cuenta en un sistema externo — spec 061
(enmienda del 2026-11-16).

Un agente da de alta en Quédate a la persona que escribe como anfitriona; esta
fila recuerda qué anfitrión es suyo para seguir actuando por ella (su
verificación de identidad, sus anuncios). **No guarda ninguna credencial**: todas
las llamadas van con la clave del negocio (``tenant_credentials``), que solo
alcanza los anfitriones que ella misma creó. ADR en la KB:
``decisions/2026-11-13-adr-credenciales-de-terceros-por-cliente-final`` (enmendado).

- Garantía 8: un vínculo por tenant, cliente final y conector, y una cuenta
  externa vinculada a una sola persona del negocio. Ninguna herramienta lo
  recibe: lo resuelve el cliente del turno.
- Garantía 1: RLS forzada por tenant y FK compuesta a ``customers``. Una FK de
  una sola columna no pasa por la RLS.
- Se borra con el cliente final y con el negocio (``ON DELETE CASCADE``).
- ``needs_review``: la clave del negocio ya no alcanza ese anfitrión (Quédate
  responde 403), por ejemplo tras generar una clave nueva.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, ForeignKeyConstraint, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import TenantScopedMixin, TimestampMixin, UUIDPrimaryKey


class CustomerConnectorAccount(UUIDPrimaryKey, TimestampMixin, TenantScopedMixin, Base):
    __tablename__ = "customer_connector_accounts"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "customer_id", "connector_slug", name="uq_customer_connector_accounts"
        ),
        # Una cuenta externa, una persona por negocio (/cso del 2026-11-16).
        UniqueConstraint(
            "tenant_id",
            "connector_slug",
            "external_user_id",
            name="uq_customer_connector_accounts_external",
        ),
        # Borrar el negocio borra sus cuentas (test_22), además de por el cliente final.
        ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_customer_connector_accounts_tenant",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["customers.tenant_id", "customers.id"],
            name="fk_customer_connector_accounts_customer",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "connector_slug = lower(connector_slug)",
            name="ck_customer_connector_accounts_slug_lower",
        ),
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    connector_slug: Mapped[str] = mapped_column(Text, nullable=False)
    external_user_id: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    def __repr__(self) -> str:
        return (
            f"CustomerConnectorAccount(id={self.id}, connector={self.connector_slug!r}, "
            f"needs_review={self.needs_review})"
        )
