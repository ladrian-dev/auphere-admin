"""Credentials of an Instagram or Messenger channel.

One channel, one credential, stored encrypted in ``channels.config_encrypted``
(the column the WhatsApp numbers already use). There is no tenant-level row:
a business can connect an Instagram account and a Page, each with its own
token, and nothing about one may resolve through the other.

- ``token`` — the business integration system-user token issued by the
  Facebook Login for Business configuration. Does not expire; dies when the
  business removes the app from its portfolio or moves the asset away.
- ``page_token`` — Messenger only: the Page token derived from it, which is
  what the Send API and ``/{page-id}/subscribed_apps`` take.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import Channel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class SocialCredentials:
    token: str
    client_business_id: str | None = None
    page_token: str | None = None

    @property
    def send_token(self) -> str:
        return self.page_token or self.token

    def to_payload(self) -> bytes:
        return json.dumps(
            {
                "kind": "meta_social",
                "token": self.token,
                "client_business_id": self.client_business_id,
                "page_token": self.page_token,
            }
        ).encode()

    @classmethod
    def from_payload(cls, payload: bytes) -> SocialCredentials:
        data = json.loads(payload)
        if not isinstance(data, dict) or data.get("kind") != "meta_social" or not data.get("token"):
            raise ValueError("not a meta_social credential")
        return cls(
            token=str(data["token"]),
            client_business_id=data.get("client_business_id"),
            page_token=data.get("page_token"),
        )


class SocialCredentialsRepository:
    """RLS-scoped: another tenant's channel id reads as absent."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, channel_id: uuid.UUID) -> SocialCredentials | None:
        require_current_tenant()
        payload = await self._session.scalar(
            select(Channel.config_encrypted).where(Channel.id == channel_id)
        )
        if not payload:
            return None
        try:
            return SocialCredentials.from_payload(payload)
        except (ValueError, json.JSONDecodeError):
            return None

    async def upsert(self, channel_id: uuid.UUID, creds: SocialCredentials) -> None:
        require_current_tenant()
        channel = await self._session.get(Channel, channel_id)
        if channel is None:
            raise LookupError(f"channel {channel_id} not found for current tenant")
        channel.config_encrypted = creds.to_payload()
        await self._session.flush()

    async def delete(self, channel_id: uuid.UUID) -> None:
        require_current_tenant()
        channel = await self._session.get(Channel, channel_id)
        if channel is not None:
            channel.config_encrypted = None
            await self._session.flush()
