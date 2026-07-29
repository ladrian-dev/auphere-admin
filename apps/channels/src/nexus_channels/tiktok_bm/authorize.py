"""TikTok Business Messaging authorisation orchestration.

The counterpart to :mod:`nexus_channels.whatsapp_meta.signup`. The business
owner is sent to TikTok, authorises the single Auphere developer app over
their Business Account, and comes back with a one-shot ``auth_code``. This
module runs everything that has to happen after that:

1. Exchange ``auth_code`` → ``access_token`` + ``refresh_token``.
2. Read the authorised Business Account(s): id, display name, region.
3. Refuse regions where TikTok does not offer Business Messaging, *before*
   anything is persisted.
4. Register the Business Messaging webhook so events reach our endpoint.
5. Persist :class:`TikTokCredentials` under the active tenant.
6. Upsert / activate the ``channels`` row with ``provider="tiktok"``.
7. Invalidate the tenant-resolver cache so the next webhook routes.

Failure policy mirrors the Meta orchestrator: once a token exists we do NOT
roll it back on a later failure. A tenant with a live token and a broken
webhook is recoverable from the panel; a tenant whose token we threw away
has to start over. Instead the credentials row is written with
``needs_reauth=True`` so the panel shows exactly what went wrong.

The region check is the one step with no Meta analogue, and it earns its
place: TikTok does not offer Business Messaging in the EEA, Switzerland or
the UK, and it does not *error* for those accounts — it simply never
delivers a webhook. Without this check the owner would see a channel that
connected successfully and then stayed silent forever.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import structlog
from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.core.tenant_resolver import invalidate_tenant_cache
from nexus_api.db.models import Channel
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_channels.tiktok_bm.credentials import (
    TikTokCredentials,
    TikTokCredentialsRepository,
)
from nexus_channels.tiktok_bm.exceptions import (
    TikTokAPIError,
    TikTokNoBusinessAccountError,
    TikTokRegionNotSupportedError,
    TikTokWebhookSetupError,
)
from nexus_channels.tiktok_bm.tiktok_client import TikTokClient

log = structlog.get_logger(__name__)

PROVIDER = "tiktok"

# ISO country codes where TikTok does not offer Business Messaging: the EEA,
# Switzerland and the UK. Accounts registered here cannot be managed through
# the API and their DMs are never delivered to a webhook.
#
# This list is the EEA (EU 27 + Iceland, Liechtenstein, Norway) plus CH and
# GB. It is a denylist rather than an allowlist on purpose — TikTok is
# expanding availability, and a new market should start working on its own
# rather than waiting for us to ship a code change.
UNSUPPORTED_REGIONS: frozenset[str] = frozenset(
    {
        "AT",
        "BE",
        "BG",
        "HR",
        "CY",
        "CZ",
        "DK",
        "EE",
        "FI",
        "FR",
        "DE",
        "GR",
        "HU",
        "IE",
        "IT",
        "LV",
        "LT",
        "LU",
        "MT",
        "NL",
        "PL",
        "PT",
        "RO",
        "SK",
        "SI",
        "ES",
        "SE",  # EU 27
        "IS",
        "LI",
        "NO",  # rest of the EEA
        "CH",
        "GB",  # Switzerland, United Kingdom
    }
)


@dataclass(slots=True, frozen=True)
class TikTokAuthorizationResult:
    """What the caller needs to render the "connected" state."""

    channel_id: uuid.UUID
    business_id: str
    display_name: str
    region: str | None
    access_token_expires_at: datetime | None
    refresh_token_expires_at: datetime | None
    webhook_config_id: str | None


class TikTokAuthorizationOrchestrator:
    """Runs the post-authorisation dance for one tenant.

    The caller must have applied the tenant RLS scope to ``session`` before
    calling in — this writes the tenant-scoped ``channels`` and
    ``tenant_credentials`` rows and relies on RLS, never on a passed id.
    """

    def __init__(
        self,
        *,
        session: AsyncSession,
        redis: Redis,
        client: TikTokClient,
        webhook_callback_url: str,
        redirect_uri: str,
    ) -> None:
        self._session = session
        self._redis = redis
        self._client = client
        self._webhook_callback_url = webhook_callback_url
        # TikTok re-validates the redirect URI at exchange time against the
        # one registered on the app. A mismatch (even a trailing slash) fails
        # the exchange, so it has to be threaded through rather than assumed.
        self._redirect_uri = redirect_uri
        self._credentials = TikTokCredentialsRepository(session)

    async def complete(self, *, auth_code: str) -> TikTokAuthorizationResult:
        tenant_id = require_current_tenant()

        # 1. Exchange. Raises TikTokTokenExchangeError, which the service
        # layer maps to a 400 — nothing has been written yet. The auth_code
        # is single-use and expires in 10 minutes.
        token_data = await self._client.exchange_auth_code(
            auth_code=auth_code,
            redirect_uri=self._redirect_uri,
        )
        access_token = _require_str(token_data, "access_token")
        refresh_token = _require_str(token_data, "refresh_token")
        access_expires_at = _expiry_from(token_data, "expires_in")
        refresh_expires_at = _expiry_from(token_data, "refresh_token_expires_in")

        # 2. Identify the Business Account.
        account = await self._resolve_business_account(access_token)
        business_id = account["business_id"]
        display_name = account["display_name"]
        region = account["region"]

        # 3. Refuse unsupported regions before persisting anything. A tenant
        # here would connect cleanly and then never receive a single event.
        if region and region.upper() in UNSUPPORTED_REGIONS:
            log.warning(
                "tiktok.authorize.region_unsupported",
                tenant_id=str(tenant_id),
                business_id=business_id,
                region=region,
            )
            raise TikTokRegionNotSupportedError(
                f"TikTok does not offer Business Messaging for accounts registered "
                f"in {region.upper()} (EEA, Switzerland and the UK are excluded)"
            )

        # 4. Webhook registration. From here on a failure leaves a live token
        # behind on purpose — see the module docstring.
        webhook_config_id = await self._register_webhook(
            access_token=access_token,
            business_id=business_id,
            tenant_id=tenant_id,
        )

        # 5. Persist credentials.
        credentials = TikTokCredentials(
            access_token=access_token,
            refresh_token=refresh_token,
            business_id=business_id,
            display_name=display_name,
            access_token_expires_at=access_expires_at,
            refresh_token_expires_at=refresh_expires_at,
            region=region,
            webhook_config_id=webhook_config_id,
        )
        await self._credentials.upsert(credentials)

        # 6. Channel row.
        channel_id = await self._upsert_channel(
            business_id=business_id,
            display_name=display_name,
            region=region,
            webhook_config_id=webhook_config_id,
        )

        # 7. Let the resolver see it. Without this the first inbound after
        # connecting resolves against a stale miss and is dropped.
        await invalidate_tenant_cache(self._redis, PROVIDER, business_id)

        log.info(
            "tiktok.authorize.complete",
            tenant_id=str(tenant_id),
            channel_id=str(channel_id),
            business_id=business_id,
            region=region,
        )
        return TikTokAuthorizationResult(
            channel_id=channel_id,
            business_id=business_id,
            display_name=display_name,
            region=region,
            access_token_expires_at=access_expires_at,
            refresh_token_expires_at=refresh_expires_at,
            webhook_config_id=webhook_config_id,
        )

    async def disconnect(self) -> None:
        """Offboard the tenant from TikTok.

        Deletes the webhook registration first (so TikTok stops delivering to
        a channel we no longer serve), then drops the credentials and marks
        the channel disconnected. A failure to reach TikTok does not block
        the local teardown — a stale registration on their side is far less
        harmful than a tenant stuck half-connected on ours.
        """
        from nexus_api.db.models import ChannelStatus

        tenant_id = require_current_tenant()
        creds = await self._credentials.get()
        if creds is None:
            return

        try:
            await self._client.delete_webhook_config(
                access_token=creds.access_token,
                business_id=creds.business_id,
            )
        except TikTokAPIError as exc:
            log.warning(
                "tiktok.disconnect.webhook_delete_failed",
                tenant_id=str(tenant_id),
                business_id=creds.business_id,
                code=exc.code,
                detail=exc.message,
            )

        await self._credentials.delete()

        row = await self._session.scalar(
            select(Channel).where(
                Channel.provider == PROVIDER,
                Channel.provider_identifier == creds.business_id,
            )
        )
        if row is not None:
            row.status = ChannelStatus.DISCONNECTED
            await self._session.flush()

        await invalidate_tenant_cache(self._redis, PROVIDER, creds.business_id)
        log.info(
            "tiktok.disconnect.complete",
            tenant_id=str(tenant_id),
            business_id=creds.business_id,
        )

    # ── internals ──────────────────────────────────────────────────────────

    async def _resolve_business_account(self, access_token: str) -> dict[str, Any]:
        """Pick the Business Account this authorisation is for.

        TikTok returns a list. Phase 1 connects exactly one account per
        tenant and takes the first — connecting several Business Accounts to
        one tenant would need a channel-picker UI and a second ``channels``
        row, which no client has asked for yet.
        """
        payload = await self._client.get_business_accounts(access_token=access_token)
        candidates = payload.get("list") or payload.get("business_accounts") or []
        if isinstance(payload.get("business_id"), str | int) and not candidates:
            candidates = [payload]

        for entry in candidates:
            if not isinstance(entry, dict):
                continue
            business_id = entry.get("business_id") or entry.get("id")
            if business_id in (None, ""):
                continue
            return {
                "business_id": str(business_id),
                "display_name": _first_str(entry, "display_name", "username", "name") or "",
                "region": _first_str(entry, "region", "country_code", "country"),
            }

        raise TikTokNoBusinessAccountError(
            "the authorisation exposed no TikTok Business Account — Business "
            "Messaging requires a Business Account, not a personal one"
        )

    async def _register_webhook(
        self,
        *,
        access_token: str,
        business_id: str,
        tenant_id: uuid.UUID,
    ) -> str | None:
        try:
            result = await self._client.create_webhook_config(
                access_token=access_token,
                business_id=business_id,
                callback_url=self._webhook_callback_url,
            )
        except TikTokAPIError as exc:
            log.warning(
                "tiktok.authorize.webhook_setup_failed",
                tenant_id=str(tenant_id),
                business_id=business_id,
                code=exc.code,
                detail=exc.message,
            )
            raise TikTokWebhookSetupError(
                f"could not register the Business Messaging webhook for "
                f"business_id={business_id}: {exc.message}"
            ) from exc

        config_id = result.get("webhook_id") or result.get("config_id") or result.get("id")
        return str(config_id) if config_id not in (None, "") else None

    async def _upsert_channel(
        self,
        *,
        business_id: str,
        display_name: str,
        region: str | None,
        webhook_config_id: str | None,
    ) -> uuid.UUID:
        """Insert/update the ``channels`` row for this Business Account.

        ``provider_identifier`` is the ``business_id`` — the value TikTok
        stamps on every webhook, which is what the tenant resolver matches
        on. ``config`` JSONB carries the rest so the webhook layer can read
        it without decrypting credentials.
        """
        from nexus_api.db.models import ChannelStatus, ChannelType

        tenant_id = require_current_tenant()
        row = await self._session.scalar(
            select(Channel).where(
                Channel.provider == PROVIDER,
                Channel.provider_identifier == business_id,
            )
        )
        config: dict[str, Any] = {
            "business_id": business_id,
            "display_name": display_name,
            "region": region,
            "webhook_config_id": webhook_config_id,
            # Recorded on the channel so the outbound guardrails and the
            # panel can read the window without importing the channels
            # package or hardcoding 48 in three places.
            "service_window_hours": 48,
            "supports_business_initiated": False,
        }
        now = datetime.now(tz=UTC)
        if row is None:
            row = Channel(
                tenant_id=tenant_id,
                type=ChannelType.TIKTOK,
                provider=PROVIDER,
                provider_identifier=business_id,
                config=config,
                status=ChannelStatus.ACTIVE,
                last_provider_synced_at=now,
            )
            self._session.add(row)
        else:
            row.config = config
            row.status = ChannelStatus.ACTIVE
            row.last_provider_synced_at = now
        await self._session.flush()
        return cast(uuid.UUID, row.id)


# ── helpers ────────────────────────────────────────────────────────────────


def _require_str(source: dict[str, Any], key: str) -> str:
    value = source.get(key)
    if not isinstance(value, str) or not value:
        raise TikTokAPIError(f"TikTok response is missing {key!r}", status_code=200)
    return value


def _expiry_from(source: dict[str, Any], key: str) -> datetime | None:
    """Turn TikTok's ``*_in`` seconds into an absolute instant.

    Absolute is what the refresh cron needs; storing the raw duration would
    make every read depend on knowing when the row was written.
    """
    raw = source.get(key)
    if not isinstance(raw, int | float) or raw <= 0:
        return None
    return datetime.now(tz=UTC) + timedelta(seconds=int(raw))


def _first_str(source: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = source.get(key)
        if isinstance(value, str) and value:
            return value
    return None
