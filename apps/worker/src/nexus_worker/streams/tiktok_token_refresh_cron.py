"""TikTok access-token refresh cron.

**This cron is load-bearing, not housekeeping.** A TikTok access token lives
roughly 24 hours. If it is not rotated, every TikTok channel in the platform
goes silent within a day — outbound sends fail and inbound turns get answered
into a void. There is no equivalent on the Meta side, where a BISUAT is
long-lived and the health cron is merely informative.

What it does, per ACTIVE tenant with a TikTok channel:

1. Read the credential row inside a tenant-scoped session (RLS is the only
   authority on which row is visible).
2. Skip it unless the access token is inside the refresh leeway.
3. Redeem the refresh token, persist the **new pair** — TikTok rotates the
   refresh token too, so writing back only the access token would break the
   next rotation.
4. On failure, flag ``needs_reauth`` and write an audit row so the operator
   panel shows which tenant lost its channel and why.

Tick: 1 hour. With a six-hour refresh leeway that means roughly six chances
to rotate before a token actually dies, so a deploy, a restart or a short
TikTok outage cannot take a channel down on their own.

Tenant discovery is RLS-free against ``tenants`` (a global table) and every
credential read happens inside a per-tenant scoped session — the same shape
``whatsapp_health_cron`` uses, and the reason no token ever crosses a tenant
boundary here.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
import structlog
from nexus_api.config import get_settings
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AuditLog,
    Channel,
    ChannelStatus,
    ChannelType,
    Tenant,
    TenantStatus,
)
from nexus_channels.tiktok_bm import TikTokClient
from nexus_channels.tiktok_bm.credentials import (
    TikTokCredentials,
    TikTokCredentialsRepository,
)
from nexus_channels.tiktok_bm.exceptions import TikTokTokenRefreshError

log = structlog.get_logger(__name__)

DEFAULT_TICK_SECONDS = 3600.0
ACTOR = "system:tiktok_token_refresh_cron"


async def run_tiktok_token_refresh_cron(
    *,
    stop: asyncio.Event,
    tick_seconds: float = DEFAULT_TICK_SECONDS,
) -> None:
    """Background task. Returns when ``stop`` is set."""
    settings = get_settings()
    if not settings.tiktok_enabled:
        # Nothing to rotate until the channel is switched on. Returning
        # rather than idling keeps the task list honest about what is
        # actually running.
        log.info("tiktok_token_refresh.disabled")
        return

    log.info("tiktok_token_refresh.start", tick_seconds=tick_seconds)
    sm = get_sessionmaker()
    while not stop.is_set():
        try:
            tenant_ids = await _list_active_tenants(sm)
            for tid in tenant_ids:
                if stop.is_set():
                    break
                await _refresh_one(sm, tid)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("tiktok_token_refresh.tick_failed", error=str(exc))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info("tiktok_token_refresh.stopped")


async def _list_active_tenants(sm: sa.orm.sessionmaker) -> list[uuid.UUID]:  # type: ignore[type-arg]
    async with sm() as session:
        rows = await session.execute(
            sa.select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE)
        )
        return [row[0] for row in rows]


async def _refresh_one(
    sm: sa.orm.sessionmaker,  # type: ignore[type-arg]
    tenant_id: uuid.UUID,
) -> None:
    settings = get_settings()

    async with sm() as session, tenant_scoped_session(session, tenant_id):
        channel = await session.scalar(
            sa.select(Channel).where(
                Channel.tenant_id == tenant_id,
                Channel.type == ChannelType.TIKTOK,
                Channel.status != ChannelStatus.DISCONNECTED,
            )
        )
        if channel is None:
            return

        repo = TikTokCredentialsRepository(session)
        creds = await repo.get()
        if creds is None:
            return

        if creds.refresh_token_expired():
            # The one-year refresh token is gone; no automated recovery
            # exists. Flag it once so the panel can prompt for re-auth.
            await _fail(
                session=session,
                repo=repo,
                channel=channel,
                tenant_id=tenant_id,
                reason="refresh_token_expired",
                detail="the TikTok refresh token expired; the owner must re-authorise",
            )
            return

        if not creds.needs_refresh():
            return

        client = TikTokClient(
            settings.tiktok_app_id,
            settings.tiktok_app_secret,
            base_url=settings.tiktok_api_base_url,
            api_version=settings.tiktok_api_version,
        )
        try:
            payload = await client.refresh_access_token(refresh_token=creds.refresh_token)
        except TikTokTokenRefreshError as exc:
            await _fail(
                session=session,
                repo=repo,
                channel=channel,
                tenant_id=tenant_id,
                reason="refresh_failed",
                detail=str(exc),
            )
            return
        finally:
            await client.close()

        access_token = payload.get("access_token")
        refresh_token = payload.get("refresh_token")
        if not isinstance(access_token, str) or not access_token:
            await _fail(
                session=session,
                repo=repo,
                channel=channel,
                tenant_id=tenant_id,
                reason="refresh_malformed",
                detail="TikTok returned no access_token on refresh",
            )
            return

        rotated = TikTokCredentials(
            access_token=access_token,
            # TikTok rotates the refresh token as well. Falling back to the
            # old one when the response omits it is deliberate — some
            # responses reuse it — but silently dropping a *new* one would
            # break the next rotation and take the channel down tomorrow.
            refresh_token=(
                refresh_token
                if isinstance(refresh_token, str) and refresh_token
                else creds.refresh_token
            ),
            business_id=creds.business_id,
            display_name=creds.display_name,
            access_token_expires_at=_expiry_from(payload, "expires_in"),
            refresh_token_expires_at=(
                _expiry_from(payload, "refresh_token_expires_in") or creds.refresh_token_expires_at
            ),
            region=creds.region,
            webhook_config_id=creds.webhook_config_id,
        )
        await repo.upsert(rotated)
        await repo.touch_health_check()

        # A channel parked DEGRADED by a previous failed refresh is healthy
        # again the moment a rotation succeeds.
        if channel.status == ChannelStatus.DEGRADED:
            channel.status = ChannelStatus.ACTIVE
        channel.last_health_check_at = datetime.now(UTC)

        log.info(
            "tiktok_token_refresh.rotated",
            tenant_id=str(tenant_id),
            business_id=creds.business_id,
            expires_at=(
                rotated.access_token_expires_at.isoformat()
                if rotated.access_token_expires_at
                else None
            ),
        )


async def _fail(
    *,
    session: sa.orm.Session,  # type: ignore[type-arg]
    repo: TikTokCredentialsRepository,
    channel: Channel,
    tenant_id: uuid.UUID,
    reason: str,
    detail: str,
) -> None:
    """Flag the tenant for re-auth and leave a trail the operator can act on.

    The channel is marked DEGRADED rather than DISCONNECTED: the row and its
    credentials stay in place so a later successful rotation (or a manual
    re-auth) restores it without re-onboarding from scratch.
    """
    await repo.mark_reauth_needed()
    channel.status = ChannelStatus.DEGRADED
    channel.last_health_check_at = datetime.now(UTC)
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor=ACTOR,
            action="channel.tiktok.token_refresh_failed",
            target=f"channel:{channel.id}",
            before_json=None,
            after_json={"reason": reason, "detail": detail[:500]},
        )
    )
    log.warning(
        "tiktok_token_refresh.failed",
        tenant_id=str(tenant_id),
        reason=reason,
        detail=detail[:200],
    )


def _expiry_from(payload: dict[str, object], key: str) -> datetime | None:
    raw = payload.get(key)
    if not isinstance(raw, int | float) or raw <= 0:
        return None
    return datetime.now(UTC) + timedelta(seconds=int(raw))
