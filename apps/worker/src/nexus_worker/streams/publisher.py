"""``XADD`` helper for the Meta webhook (and any future ChannelAdapter).

The webhook resolves the tenant and channel from the provider identifier
already (block B) — that is the *only* place that mapping happens, so the
worker can trust the values it reads off the stream.
"""

from __future__ import annotations

import uuid

from redis.asyncio import Redis

INBOUND_STREAM = "nexus:inbound"


async def publish_inbound(
    redis: Redis,
    *,
    tenant_id: uuid.UUID,
    channel_id: uuid.UUID,
    user_id: str,
    content: str,
    customer_name: str | None = None,
    provider: str = "meta",
    stream: str = INBOUND_STREAM,
) -> str:
    fields: dict[str, str] = {
        "tenant_id": str(tenant_id),
        "channel_id": str(channel_id),
        "user_id": user_id,
        "content": content,
        "provider": provider,
    }
    if customer_name:
        fields["customer_name"] = customer_name
    msg_id = await redis.xadd(stream, fields)  # type: ignore[arg-type]
    return msg_id if isinstance(msg_id, str) else msg_id.decode()
