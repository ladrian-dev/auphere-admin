"""A shareable link to connect a channel from the business owner's device.

WhatsApp since spec 040; Instagram and Messenger since spec 085 (0244). See
migration 0160 for why the table has no RLS: the public page only knows the
token. Only the token's SHA-256 is stored.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import UUIDPrimaryKey

#: Long enough for the owner to find a moment; short enough that a forgotten
#: link in a chat history stops working.
CHANNEL_SIGNUP_LINK_TTL = timedelta(days=7)


class ChannelSignupLink(UUIDPrimaryKey, Base):
    __tablename__ = "channel_signup_links"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    #: ``whatsapp``, ``instagram`` or ``messenger`` (0244): one channel per link.
    channel: Mapped[str] = mapped_column(String(16), nullable=False, default="whatsapp")
    #: WhatsApp: ``coexistence`` (the owner keeps the WhatsApp Business app),
    #: ``cloud_api`` or ``whatsapp_login``. Instagram and Messenger:
    #: ``meta_login`` — the owner picks how to sign in on their page (0244).
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    #: ``operator:<email>`` or ``console:<email>`` — who sent it.
    created_by: Mapped[str] = mapped_column(String(320), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: The channel the owner connected with it.
    channel_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    #: Spec 047 (0191): the agent the owner connects the number to.
    agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
