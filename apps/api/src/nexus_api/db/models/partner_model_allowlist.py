"""Techo de catálogo del partner — F2 allowlist.

FORCE RLS por ``app.partner_id`` (migración 0098). El partner sale del
path (admin) o del principal (consola). No reescribe ``tenant_model_bindings``.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base


class PartnerModelAllowlist(Base):
    """Fila = un id del catálogo cerrado que el partner puede ver."""

    __tablename__ = "partner_model_allowlist"

    partner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("partners.id", ondelete="CASCADE"),
        primary_key=True,
    )
    model_id: Mapped[str] = mapped_column(Text, primary_key=True)
