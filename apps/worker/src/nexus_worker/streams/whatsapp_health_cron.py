"""WhatsApp WABA health-check cron.

Periodically fetches ``GET /v2/whatsapp/phoneNumbers/...`` for every
ACTIVE tenant's WhatsApp channel and refreshes the snapshot fields:

- ``Channel.config['quality_rating']`` — Meta's degradation indicator
  (GREEN / YELLOW / RED). A YELLOW or RED transition triggers an audit
  log entry so the operator alerter surfaces it.
- ``Channel.config['display_name']`` / ``verified_name`` — Meta may
  update these out-of-band.
- ``Channel.last_health_check_at`` + ``Channel.last_provider_synced_at``
  — timestamps the panel renders as "última verificación".

Tick: 1 hour by default. The Cloud API rate limit on this endpoint is
generous (per-WABA, not per-phone), so we can re-check every tenant once
an hour without burning the budget.

Pattern: shared with ``health_check_cron`` (AgendaPro) — RLS-free tenant
discovery, then per-tenant scoped session for the channel update +
audit log insert.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, datetime

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
from nexus_channels.whatsapp_ycloud.ycloud_client import YCloudAPIError, YCloudClient

log = structlog.get_logger(__name__)

DEFAULT_TICK_SECONDS = 3600.0
ACTOR = "system:whatsapp_health_cron"


async def run_whatsapp_health_cron(
    *,
    stop: asyncio.Event,
    tick_seconds: float = DEFAULT_TICK_SECONDS,
) -> None:
    """Background task. Returns when ``stop`` is set."""
    log.info("whatsapp_health.start", tick_seconds=tick_seconds)
    sm = get_sessionmaker()
    while not stop.is_set():
        try:
            tenant_ids = await _list_active_tenants(sm)
            for tid in tenant_ids:
                if stop.is_set():
                    break
                await _check_one(sm, tid)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("whatsapp_health.tick_failed", error=str(exc))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info("whatsapp_health.stopped")


async def _list_active_tenants(sm: sa.orm.sessionmaker) -> list[uuid.UUID]:  # type: ignore[type-arg]
    async with sm() as session:
        rows = await session.execute(
            sa.select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE)
        )
        return [row[0] for row in rows]


async def _check_one(
    sm: sa.orm.sessionmaker,  # type: ignore[type-arg]
    tenant_id: uuid.UUID,
) -> None:
    """Fetch the channel's WhatsApp phone metadata + persist refreshed snapshot."""
    settings = get_settings()
    if not settings.ycloud_api_key:
        return

    async with sm() as session, tenant_scoped_session(session, tenant_id):
        channel = await session.scalar(
            sa.select(Channel).where(
                Channel.tenant_id == tenant_id,
                Channel.type == ChannelType.WHATSAPP,
                Channel.status != ChannelStatus.DISCONNECTED,
            )
        )
        if channel is None:
            return
        cfg = channel.config or {}
        waba_id = cfg.get("waba_id")
        if not isinstance(waba_id, str) or not waba_id:
            return
        # Prefer the canonical Meta phone_number_id when YCloud emitted
        # one at connect-time; otherwise fall back to the E.164 stored as
        # the channel's provider_identifier — YCloud accepts both as the
        # second path segment of /whatsapp/phoneNumbers/{waba}/{lookup}.
        phone_lookup = cfg.get("phone_number_id") or channel.provider_identifier
        if not isinstance(phone_lookup, str) or not phone_lookup:
            return

        client = YCloudClient(
            api_key=settings.ycloud_api_key, base_url=settings.ycloud_api_base_url
        )
        try:
            try:
                payload = await client.get_phone_number(
                    waba_id=waba_id, phone_lookup=phone_lookup
                )
            except YCloudAPIError as exc:
                log.warning(
                    "whatsapp_health.fetch_failed",
                    tenant_id=str(tenant_id),
                    waba_id=waba_id,
                    status=exc.status_code,
                    detail=exc.message,
                )
                channel.last_health_check_at = datetime.now(UTC)
                return
        finally:
            await client.close()

        prior_quality = cfg.get("quality_rating")
        new_quality = payload.get("qualityRating") or payload.get("quality_rating")
        new_display = payload.get("displayName") or payload.get("display_name")
        new_verified = payload.get("verifiedName") or payload.get("verified_name")

        # Persist refreshed snapshot.
        cfg = dict(cfg)
        if new_quality:
            cfg["quality_rating"] = new_quality
        if new_display:
            cfg["display_name"] = new_display
        if new_verified:
            cfg["verified_name"] = new_verified
        channel.config = cfg
        channel.last_health_check_at = datetime.now(UTC)
        channel.last_provider_synced_at = datetime.now(UTC)

        # Mark the channel DEGRADED on a YELLOW / RED transition so the
        # operator panel surfaces it. The original status is restored
        # automatically on the next GREEN reading.
        old_status = channel.status
        if isinstance(new_quality, str) and new_quality.upper() in {"YELLOW", "RED"}:
            channel.status = ChannelStatus.DEGRADED
        elif (
            isinstance(new_quality, str)
            and new_quality.upper() == "GREEN"
            and channel.status == ChannelStatus.DEGRADED
        ):
            channel.status = ChannelStatus.ACTIVE

        if prior_quality != new_quality or old_status != channel.status:
            audit = AuditLog(
                tenant_id=tenant_id,
                actor=ACTOR,
                action="channel.whatsapp.quality_rating_changed",
                target=f"channel:{channel.id}",
                before_json={
                    "quality_rating": prior_quality,
                    "status": old_status.value if old_status else None,
                },
                after_json={
                    "quality_rating": new_quality,
                    "status": channel.status.value,
                },
            )
            session.add(audit)
            log.info(
                "whatsapp_health.quality_changed",
                tenant_id=str(tenant_id),
                channel_id=str(channel.id),
                prior=prior_quality,
                new=new_quality,
                status=channel.status.value,
            )
        await session.flush()
