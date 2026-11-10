"""The post a comment was left on, for the Inbox (owner, 2026-11-02).

Read from Graph when the conversation is open, not at the webhook: nothing else
needs it, and a post can change. Instagram names it on the comment
(``media``, ``instagram_basic``). A Page comment's id is ``<object>_<comment>``:
the object is a post of the Page (``<page>_<object>``) or, for a reel or a video,
the object itself (``pages_read_engagement``). The answer lives an hour in Redis.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import structlog
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import Channel, ChannelType, Conversation, Message

log = structlog.get_logger(__name__)

COMMENT_PREFIX = "comment:"
CACHE_SECONDS = 3600


async def read(
    session: AsyncSession, redis: Redis, conversation: Conversation, message_id: uuid.UUID
) -> dict[str, str | None] | None:
    from nexus_channels.meta_social.credentials import SocialCredentialsRepository

    from nexus_api.services import meta_social_service

    message = await session.get(Message, message_id)
    if message is None or message.conversation_id != conversation.id:
        return None
    ref = message.provider_message_id or ""
    if not ref.startswith(COMMENT_PREFIX):
        return None
    comment_id = ref.removeprefix(COMMENT_PREFIX)

    cache_key = f"nexus:inbox:comment_post:{comment_id}"
    cached = await redis.get(cache_key)
    if cached:
        found = json.loads(cached)
        return dict(found) if isinstance(found, dict) else None

    channel = await session.get(Channel, conversation.channel_id)
    if channel is None:
        return None
    creds = await SocialCredentialsRepository(session).get(channel.id)
    if creds is None:
        return None
    client = meta_social_service.client()

    async def graph(object_id: str, fields: str) -> dict[str, Any] | None:
        try:
            got = await client.account_profile(
                object_id=object_id, access_token=creds.send_token, fields=fields
            )
            return dict(got) if isinstance(got, dict) else None
        except Exception as exc:
            log.info("inbox.comment_post.read_failed", error=type(exc).__name__)
            return None

    post: dict[str, str | None] | None = None
    if channel.type == ChannelType.INSTAGRAM:
        got = await graph(comment_id, "media{caption,media_url,thumbnail_url,permalink,media_type}")
        media = (got or {}).get("media")
        if isinstance(media, dict):
            is_video = media.get("media_type") == "VIDEO"
            post = {
                "text": media.get("caption"),
                "image_url": media.get("thumbnail_url") if is_video else media.get("media_url"),
                "permalink": media.get("permalink"),
            }
    else:
        object_id = comment_id.split("_")[0]
        got = await graph(
            f"{channel.provider_identifier}_{object_id}", "message,full_picture,permalink_url"
        )
        if got is not None:
            post = {
                "text": got.get("message"),
                "image_url": got.get("full_picture"),
                "permalink": got.get("permalink_url"),
            }
        else:
            got = await graph(object_id, "description,picture,permalink_url")
            if got is not None:
                post = {
                    "text": got.get("description"),
                    "image_url": got.get("picture"),
                    "permalink": got.get("permalink_url"),
                }
    if post is None or not any(post.values()):
        return None
    await redis.set(cache_key, json.dumps(post), ex=CACHE_SECONDS)
    return post
