"""Connect, check and disconnect an Instagram account or a Facebook Page.

The browser runs ``FB.login`` with the channel's Facebook Login for Business
configuration (``response_type=code``, ``override_default_response_type``);
the console hands the single-use ``code`` to :meth:`MetaSocialConnector.begin`:

1. ``code`` → business integration system-user token (the same exchange the
   WhatsApp Embedded Signup uses).
2. ``GET /me?fields=client_business_id``. Unified Login requires the business
   to have a portfolio; no id means it has none.
3. What the business granted: ``/me/assigned_instagram_accounts`` or
   ``/me/accounts`` (Pages, each with its Page token).
4. One asset → connect it. Several → keep the token encrypted in Redis for
   ten minutes and return the list; :meth:`complete` connects the one picked.
5. ``POST /{id}/subscribed_apps`` with the channel's fields, the profile for
   the card, the channel row (``status=active``) and the credential,
   encrypted on the row. The tenant-resolver cache is invalidated so the next
   webhook routes here.

Everything runs under the tenant-scoped session the API opened; the only
cross-tenant read is the SECURITY DEFINER resolver, to refuse an asset that
is live under another client.
"""

from __future__ import annotations

import json
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, cast

import structlog
from cryptography.fernet import Fernet, InvalidToken
from nexus_api.config import get_settings
from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.core.tenant_resolver import invalidate_tenant_cache
from nexus_api.db.models import Channel, ChannelStatus, ChannelType
from redis.asyncio import Redis
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_channels.meta_social.credentials import SocialCredentials, SocialCredentialsRepository
from nexus_channels.meta_social.exceptions import (
    MetaSocialConnectError,
    is_messages_disabled,
    is_permission_error,
)
from nexus_channels.meta_social.graph import INSTAGRAM_FIELDS, MESSENGER_FIELDS, MetaSocialClient
from nexus_channels.meta_social.webhook_adapter import PROVIDER_INSTAGRAM, PROVIDER_MESSENGER
from nexus_channels.whatsapp_meta.exceptions import (
    MetaAPIError,
    TokenExchangeError,
    TokenInvalidatedError,
)

log = structlog.get_logger(__name__)

Kind = Literal["instagram", "messenger"]
PENDING_TTL_SECONDS = 600
_PENDING_KEY = "nexus:meta_social:pending:{tenant}:{nonce}"


def provider_of(kind: Kind) -> str:
    return PROVIDER_INSTAGRAM if kind == "instagram" else PROVIDER_MESSENGER


def kind_of(provider: str) -> Kind | None:
    if provider == PROVIDER_INSTAGRAM:
        return "instagram"
    if provider == PROVIDER_MESSENGER:
        return "messenger"
    return None


@dataclass(frozen=True, slots=True)
class ConnectableAccount:
    id: str
    name: str
    username: str | None = None
    picture_url: str | None = None


@dataclass(slots=True)
class ConnectOutcome:
    status: Literal["connected", "choose"]
    channel_id: uuid.UUID | None = None
    account: ConnectableAccount | None = None
    nonce: str | None = None
    accounts: list[ConnectableAccount] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class HealthResult:
    ok: bool
    reason: str | None = None
    resubscribed: bool = False


def _fernet() -> Fernet:
    return Fernet(get_settings().fernet_key.encode())


class MetaSocialConnector:
    def __init__(
        self,
        *,
        session: AsyncSession,
        redis: Redis,
        client: MetaSocialClient,
        app_id: str,
    ) -> None:
        self._session = session
        self._redis = redis
        self._client = client
        self._app_id = app_id
        self._credentials = SocialCredentialsRepository(session)

    # ── connect ─────────────────────────────────────────────────────────

    async def begin(self, *, kind: Kind, code: str) -> ConnectOutcome:
        tenant_id = require_current_tenant()
        try:
            envelope = await self._client.exchange_code(app_id=self._app_id, code=code)
        except TokenExchangeError as exc:
            raise MetaSocialConnectError("code_exchange_failed", str(exc)[:200]) from exc
        token = envelope.get("access_token")
        if not isinstance(token, str) or not token:
            raise MetaSocialConnectError("code_exchange_failed", "no access_token in response")

        try:
            business_id = await self._client.client_business_id(access_token=token)
        except MetaAPIError as exc:
            log.info("meta_social.connect.no_business", code=exc.code)
            business_id = None
        if not business_id:
            raise MetaSocialConnectError("no_business_portfolio")

        accounts, page_tokens = await self._granted(kind, token)
        if not accounts:
            raise MetaSocialConnectError(
                "no_instagram_account" if kind == "instagram" else "no_page"
            )
        if len(accounts) == 1:
            account = accounts[0]
            return await self._connect(
                kind,
                account,
                SocialCredentials(
                    token=token,
                    client_business_id=business_id,
                    page_token=page_tokens.get(account.id),
                ),
            )

        nonce = secrets.token_urlsafe(16)
        stash = {
            "kind": kind,
            "token": token,
            "business_id": business_id,
            "page_tokens": page_tokens,
            "accounts": [_account_dict(a) for a in accounts],
        }
        await self._redis.set(
            _PENDING_KEY.format(tenant=tenant_id, nonce=nonce),
            _fernet().encrypt(json.dumps(stash).encode()),
            ex=PENDING_TTL_SECONDS,
        )
        return ConnectOutcome(status="choose", nonce=nonce, accounts=accounts)

    async def complete(self, *, kind: Kind, nonce: str, account_id: str) -> ConnectOutcome:
        tenant_id = require_current_tenant()
        key = _PENDING_KEY.format(tenant=tenant_id, nonce=nonce)
        raw = await self._redis.get(key)
        if not raw:
            raise MetaSocialConnectError("pending_expired")
        try:
            stash = json.loads(_fernet().decrypt(raw if isinstance(raw, bytes) else raw.encode()))
        except (InvalidToken, json.JSONDecodeError) as exc:
            raise MetaSocialConnectError("pending_expired") from exc
        if stash.get("kind") != kind:
            raise MetaSocialConnectError("pending_expired")
        accounts = [ConnectableAccount(**a) for a in stash.get("accounts") or []]
        account = next((a for a in accounts if a.id == account_id), None)
        if account is None:
            raise MetaSocialConnectError("pending_expired", "account not in the granted list")
        outcome = await self._connect(
            kind,
            account,
            SocialCredentials(
                token=stash["token"],
                client_business_id=stash.get("business_id"),
                page_token=(stash.get("page_tokens") or {}).get(account.id),
            ),
        )
        await self._redis.delete(key)
        return outcome

    async def _granted(
        self, kind: Kind, token: str
    ) -> tuple[list[ConnectableAccount], dict[str, str]]:
        if kind == "instagram":
            raw = await self._client.assigned_instagram_accounts(access_token=token)
            accounts = []
            for a in raw:
                profile: dict[str, Any] = {}
                try:
                    profile = await self._client.account_profile(
                        object_id=str(a["id"]),
                        access_token=token,
                        fields="id,username,name,profile_picture_url",
                    )
                except MetaAPIError as exc:
                    log.info("meta_social.connect.profile_unavailable", code=exc.code)
                username = profile.get("username") or a.get("username")
                accounts.append(
                    ConnectableAccount(
                        id=str(a["id"]),
                        name=str(profile.get("name") or username or a["id"]),
                        username=str(username) if username else None,
                        picture_url=profile.get("profile_picture_url"),
                    )
                )
            return accounts, {}

        pages = await self._client.pages(access_token=token)
        accounts, tokens = [], {}
        for p in pages:
            tasks = p.get("tasks")
            # Messenger needs the person to hold MESSAGING on the Page; a Page
            # granted without it would connect and then fail every send.
            if isinstance(tasks, list) and "MESSAGING" not in tasks and "MANAGE" not in tasks:
                continue
            page_token = p.get("access_token")
            if not page_token:
                page_token = await self._client.page_access_token(
                    page_id=str(p["id"]), access_token=token
                )
            if not page_token:
                continue
            picture = ((p.get("picture") or {}).get("data") or {}).get("url")
            accounts.append(
                ConnectableAccount(
                    id=str(p["id"]), name=str(p.get("name") or p["id"]), picture_url=picture
                )
            )
            tokens[str(p["id"])] = str(page_token)
        if pages and not accounts:
            raise MetaSocialConnectError("page_messaging_task_missing")
        return accounts, tokens

    async def _connect(
        self, kind: Kind, account: ConnectableAccount, creds: SocialCredentials
    ) -> ConnectOutcome:
        tenant_id = require_current_tenant()
        provider = provider_of(kind)

        owner = await self._session.scalar(
            text("SELECT resolve_channel_tenant(:p, :i)"), {"p": provider, "i": account.id}
        )
        if owner is not None and uuid.UUID(str(owner)) != tenant_id:
            raise MetaSocialConnectError("already_connected_elsewhere")

        fields = INSTAGRAM_FIELDS if kind == "instagram" else MESSENGER_FIELDS
        try:
            await self._client.subscribe(
                object_id=account.id, access_token=creds.send_token, fields=fields
            )
        except MetaAPIError as exc:
            if kind == "instagram" and is_messages_disabled(exc):
                raise MetaSocialConnectError("messages_disabled") from exc
            if is_permission_error(exc):
                raise MetaSocialConnectError("missing_permission", exc.message) from exc
            raise MetaSocialConnectError("subscribe_failed", exc.message) from exc

        channel_id = await self._upsert_channel(kind, provider, account)
        await self._credentials.upsert(channel_id, creds)
        await invalidate_tenant_cache(self._redis, provider, account.id)
        log.info(
            "meta_social.connected",
            tenant_id=str(tenant_id),
            channel_id=str(channel_id),
            provider=provider,
            account_id=account.id,
        )
        return ConnectOutcome(status="connected", channel_id=channel_id, account=account)

    async def _upsert_channel(
        self, kind: Kind, provider: str, account: ConnectableAccount
    ) -> uuid.UUID:
        tenant_id = require_current_tenant()
        row = (
            await self._session.execute(
                select(Channel).where(
                    Channel.provider == provider, Channel.provider_identifier == account.id
                )
            )
        ).scalar_one_or_none()
        now = datetime.now(UTC)
        public = {
            "account_id": account.id,
            "name": account.name,
            "username": account.username,
            "picture_url": account.picture_url,
            "connected_at": now.isoformat(),
        }
        if row is None:
            row = Channel(
                tenant_id=tenant_id,
                type=ChannelType.INSTAGRAM if kind == "instagram" else ChannelType.MESSENGER,
                provider=provider,
                provider_identifier=account.id,
                config=public,
                status=ChannelStatus.ACTIVE,
                last_provider_synced_at=now,
            )
            self._session.add(row)
        else:
            # A reconnect keeps what the business configured (comment replies)
            # and clears what the disconnect left (purge clock, attention).
            config = {
                k: v
                for k, v in (row.config or {}).items()
                if k not in {"disconnected_at", "needs_attention", "purged_at"}
            }
            row.config = {**config, **public}
            row.status = ChannelStatus.ACTIVE
            row.last_provider_synced_at = now
        await self._session.flush()
        return cast(uuid.UUID, row.id)

    # ── disconnect ──────────────────────────────────────────────────────

    async def disconnect(self, channel: Channel) -> bool:
        """Stop receiving and sending now, drop the token now, start the
        30-day clock for the data. Returns whether Meta confirmed the
        unsubscribe (the channel is disconnected either way)."""
        creds = await self._credentials.get(channel.id)
        unsubscribed = False
        if creds is not None:
            try:
                await self._client.unsubscribe(
                    object_id=channel.provider_identifier, access_token=creds.send_token
                )
                unsubscribed = True
            except MetaAPIError as exc:
                # A revoked token or an asset the business already removed:
                # there is nothing left to unsubscribe from.
                log.info(
                    "meta_social.disconnect.unsubscribe_failed",
                    code=exc.code,
                    channel_id=str(channel.id),
                )
        await self._credentials.delete(channel.id)
        channel.status = ChannelStatus.DISCONNECTED
        channel.config = {
            **{k: v for k, v in (channel.config or {}).items() if k != "needs_attention"},
            "disconnected_at": datetime.now(UTC).isoformat(),
        }
        await self._session.flush()
        await invalidate_tenant_cache(self._redis, channel.provider, channel.provider_identifier)
        return unsubscribed

    # ── health ──────────────────────────────────────────────────────────

    async def check(self, channel: Channel) -> HealthResult:
        """Token alive and app still subscribed; resubscribe if Meta dropped
        it (it does after an hour of failed deliveries)."""
        kind = kind_of(channel.provider)
        creds = await self._credentials.get(channel.id)
        if kind is None or creds is None:
            return HealthResult(ok=False, reason="no_credentials")
        fields = INSTAGRAM_FIELDS if kind == "instagram" else MESSENGER_FIELDS
        try:
            apps = await self._client.subscribed_apps(
                object_id=channel.provider_identifier, access_token=creds.send_token
            )
        except TokenInvalidatedError:
            return HealthResult(ok=False, reason="token_revoked")
        except MetaAPIError as exc:
            if is_permission_error(exc):
                return HealthResult(ok=False, reason="permission_lost")
            return HealthResult(ok=True, reason="check_inconclusive")
        ours = [a for a in apps if str(a.get("id")) == self._app_id]
        subscribed = set((ours[0].get("subscribed_fields") or []) if ours else [])
        if ours and set(fields) <= subscribed:
            return HealthResult(ok=True)
        try:
            await self._client.subscribe(
                object_id=channel.provider_identifier, access_token=creds.send_token, fields=fields
            )
        except MetaAPIError as exc:
            if kind == "instagram" and is_messages_disabled(exc):
                return HealthResult(ok=False, reason="messages_disabled")
            return HealthResult(ok=False, reason="subscribe_failed")
        return HealthResult(ok=True, resubscribed=True)


def _account_dict(a: ConnectableAccount) -> dict[str, Any]:
    return {"id": a.id, "name": a.name, "username": a.username, "picture_url": a.picture_url}
