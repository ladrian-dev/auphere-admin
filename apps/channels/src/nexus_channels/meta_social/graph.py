"""Graph API calls for Instagram (Unified Login) and Messenger.

Both go through ``graph.facebook.com`` with the business integration
system-user token the Facebook Login for Business configuration issues —
Instagram User tokens and ``graph.instagram.com`` do not work with Unified
Login. The HTTP primitives, ``appsecret_proof``, retries and error mapping
are :class:`MetaClient`'s; this class only adds the endpoints.

Endpoints (Meta docs, 2026-10):

- ``GET /oauth/access_token`` — code → system-user token (inherited).
- ``GET /me?fields=client_business_id`` — the client's business portfolio.
- ``GET /me/assigned_instagram_accounts`` — the Instagram accounts the
  business granted. ``/me`` with this token is the system user, not the
  account.
- ``GET /me/accounts`` — the Pages granted, each with its Page token.
- ``POST|GET|DELETE /{id}/subscribed_apps`` — webhooks per account or Page.
- ``POST /{id}/messages`` — Send API (``{IG_ID}`` or ``{PAGE_ID}``).
- ``POST /{comment_id}/replies`` — public reply to an Instagram comment.
- ``GET /{IGSID|PSID}`` — the person's name and picture (Business Asset
  User Profile Access).
"""

from __future__ import annotations

from typing import Any, Final

import httpx

from nexus_channels.whatsapp_meta.meta_client import MetaClient

META_SOCIAL_GRAPH_VERSION: Final = "v26.0"

#: Fields subscribed per Instagram account. ``messages`` carries the echoes
#: (``is_echo``); there is no separate echoes field on Instagram.
INSTAGRAM_FIELDS: Final = (
    "messages",
    "messaging_postbacks",
    "messaging_seen",
    "message_reactions",
    "messaging_referral",
    "comments",
    "mentions",
)
#: Fields subscribed per Page. ``messaging_policy_enforcement`` is required
#: by Messenger's App Review checklist.
MESSENGER_FIELDS: Final = (
    "messages",
    "messaging_postbacks",
    "message_reads",
    "message_reactions",
    "messaging_referrals",
    "message_echoes",
    "messaging_policy_enforcement",
)

#: Hosts Meta serves message attachments from. Anything else is refused, so
#: a crafted payload cannot make the worker fetch an arbitrary URL.
ATTACHMENT_HOST_SUFFIXES: Final = (".fbcdn.net", ".cdninstagram.com", ".fbsbx.com")


def graph_base_url(version: str = META_SOCIAL_GRAPH_VERSION) -> str:
    return f"https://graph.facebook.com/{version}"


class MetaSocialClient(MetaClient):
    """One per process; owns an httpx pool, like :class:`MetaClient`."""

    def __init__(
        self,
        app_secret: str,
        *,
        version: str = META_SOCIAL_GRAPH_VERSION,
        require_appsecret_proof: bool = True,
        timeout: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(
            app_secret,
            require_appsecret_proof=require_appsecret_proof,
            timeout=timeout,
            base_url=graph_base_url(version),
            transport=transport,
        )
        self._download = httpx.AsyncClient(timeout=30.0, transport=transport, follow_redirects=True)

    async def close(self) -> None:
        await self._download.aclose()
        await super().close()

    # ── identity of what was granted ─────────────────────────────────────

    async def client_business_id(self, *, access_token: str) -> str | None:
        data = await self._get(
            "/me", access_token=access_token, params={"fields": "client_business_id"}
        )
        value = data.get("client_business_id")
        return str(value) if value else None

    async def assigned_instagram_accounts(self, *, access_token: str) -> list[dict[str, Any]]:
        data = await self._get(
            "/me/assigned_instagram_accounts",
            access_token=access_token,
            params={"fields": "id,username", "limit": 50},
        )
        return [a for a in data.get("data") or [] if isinstance(a, dict) and a.get("id")]

    async def pages(self, *, access_token: str) -> list[dict[str, Any]]:
        data = await self._get(
            "/me/accounts",
            access_token=access_token,
            params={"fields": "id,name,access_token,tasks,picture{url}", "limit": 50},
        )
        return [p for p in data.get("data") or [] if isinstance(p, dict) and p.get("id")]

    async def page_access_token(self, *, page_id: str, access_token: str) -> str | None:
        data = await self._get(
            f"/{page_id}", access_token=access_token, params={"fields": "access_token"}
        )
        token = data.get("access_token")
        return str(token) if token else None

    async def account_profile(
        self, *, object_id: str, access_token: str, fields: str
    ) -> dict[str, Any]:
        return await self._get(
            f"/{object_id}", access_token=access_token, params={"fields": fields}
        )

    # ── webhooks per account / Page ──────────────────────────────────────

    async def subscribe(
        self, *, object_id: str, access_token: str, fields: tuple[str, ...]
    ) -> dict[str, Any]:
        return await self._post(
            f"/{object_id}/subscribed_apps",
            access_token=access_token,
            params={"subscribed_fields": ",".join(fields)},
        )

    async def unsubscribe(self, *, object_id: str, access_token: str) -> dict[str, Any]:
        return await self._delete(f"/{object_id}/subscribed_apps", access_token=access_token)

    async def subscribed_apps(self, *, object_id: str, access_token: str) -> list[dict[str, Any]]:
        data = await self._get(f"/{object_id}/subscribed_apps", access_token=access_token)
        return [a for a in data.get("data") or [] if isinstance(a, dict)]

    # ── messaging ────────────────────────────────────────────────────────

    async def send(
        self, *, sender_id: str, access_token: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._post(f"/{sender_id}/messages", access_token=access_token, json_body=body)

    async def reply_comment(
        self, *, comment_id: str, access_token: str, message: str
    ) -> dict[str, Any]:
        return await self._post(
            f"/{comment_id}/replies", access_token=access_token, params={"message": message}
        )

    async def user_profile(self, *, user_id: str, access_token: str, fields: str) -> dict[str, Any]:
        return await self._get(f"/{user_id}", access_token=access_token, params={"fields": fields})

    async def download_attachment(self, url: str, *, max_bytes: int) -> tuple[bytes, str | None]:
        """Fetch an attachment from Meta's CDN. Only Meta hosts, only HTTPS."""
        parsed = httpx.URL(url)
        host = parsed.host or ""
        if parsed.scheme != "https" or not host.endswith(ATTACHMENT_HOST_SUFFIXES):
            raise ValueError(f"attachment host not allowed: {host}")
        async with self._download.stream("GET", url) as resp:
            resp.raise_for_status()
            chunks: list[bytes] = []
            size = 0
            async for chunk in resp.aiter_bytes():
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError(f"attachment larger than {max_bytes} bytes")
                chunks.append(chunk)
            mime = resp.headers.get("content-type")
        return b"".join(chunks), (mime.split(";")[0].strip() if mime else None)
