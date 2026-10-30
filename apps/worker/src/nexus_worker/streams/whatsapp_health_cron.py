"""WhatsApp WABA health-check cron (Meta Cloud API).

Periodically fetches ``GET /{phone_number_id}`` for every ACTIVE tenant's
WhatsApp channel and refreshes the snapshot fields:

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

Pattern: RLS-free tenant discovery, then per-tenant scoped session for the
channel update + audit log insert. The per-tenant BISUAT is resolved INSIDE the scoped
session (RLS is the only authority on which credentials row is read).
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, date, datetime
from typing import Any

import sqlalchemy as sa
import structlog
from nexus_api.config import get_settings, graph_version_notice
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
from nexus_channels.whatsapp_meta import MetaClient
from nexus_channels.whatsapp_meta.credentials import resolve_send_credentials
from nexus_channels.whatsapp_meta.exceptions import MetaAPIError
from sqlalchemy.ext.asyncio import AsyncSession

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
    warned_on: date | None = None
    while not stop.is_set():
        warned_on = warn_if_graph_version_expiring(warned_on)
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


def _limit(value: Any) -> str | None:
    """``whatsapp_business_manager_messaging_limit`` as a ``TIER_*`` string."""
    if isinstance(value, str) and value:
        return value
    if isinstance(value, dict):
        for key in ("current_limit", "limit", "tier"):
            if isinstance(value.get(key), str):
                return str(value[key])
    return None


def apply_phone_snapshot(channel: Channel, payload: dict[str, Any]) -> None:
    """Spec 050 (4.2, 8.4): what ``GET /{phone_number_id}`` says, on the channel.

    The snapshot fields are refreshed. A YELLOW / RED reading degrades the
    number with ``problem_reason = "quality"`` and ``problem_source =
    "quality"`` unless an account problem is already there; GREEN clears only
    a problem the cron set (or a pre-050 one without a source). An account
    problem is cleared by its own opposite event, never by quality.
    """
    cfg = dict(channel.config or {})
    quality = payload.get("quality_rating") or payload.get("qualityRating")
    display = payload.get("display_phone_number") or payload.get("display_name")
    verified = payload.get("verified_name") or payload.get("verifiedName")
    limit = _limit(payload.get("whatsapp_business_manager_messaging_limit")) or _limit(
        payload.get("messaging_limit_tier")
    )
    if quality:
        cfg["quality_rating"] = quality
    if display:
        cfg["display_name"] = display
    if verified:
        cfg["verified_name"] = verified
    if limit:
        cfg["messaging_limit"] = limit
    if isinstance(payload.get("name_status"), str):
        cfg["name_status"] = payload["name_status"]

    source = cfg.get("problem_source")
    mine = source == "quality" or (source is None and channel.problem_reason in (None, "quality"))
    level = quality.upper() if isinstance(quality, str) else ""
    if level in {"YELLOW", "RED"}:
        if channel.status is not ChannelStatus.DEGRADED or mine:
            channel.status = ChannelStatus.DEGRADED
            channel.problem_reason = "quality"
            cfg["problem_source"] = "quality"
    elif level == "GREEN" and channel.status is ChannelStatus.DEGRADED and mine:
        channel.status = ChannelStatus.ACTIVE
        channel.problem_reason = None
        cfg.pop("problem_source", None)
    channel.config = cfg


def warn_if_graph_version_expiring(
    warned_on: date | None, *, today: date | None = None
) -> date | None:
    """Spec 050 (3.6): once a day, an error-level log while the Graph
    version dies within 60 days; the panel's Estado page says the same.
    Returns the day it last warned."""
    day = today or datetime.now(tz=UTC).date()
    if warned_on == day:
        return warned_on
    version = get_settings().meta_graph_api_version
    notice = graph_version_notice(version, day)
    if notice is None:
        return warned_on
    log.error(
        "meta.graph_version_expiring",
        version=version,
        expires_on=notice[0].isoformat(),
        days_left=notice[1],
    )
    return day


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
    """Refresh the health snapshot of EVERY live WhatsApp number of a tenant.

    This used to read a single channel with ``scalar()``, which on a tenant
    with two numbers silently picked one and left the other's quality rating
    frozen at whatever it was when it was connected — the operator panel would
    show GREEN for a line Meta had already downgraded.
    """
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        channels = list(
            (
                await session.execute(
                    sa.select(Channel).where(
                        Channel.type == ChannelType.WHATSAPP,
                        Channel.status != ChannelStatus.DISCONNECTED,
                    )
                )
            ).scalars()
        )
        for channel in channels:
            await _check_channel(session, tenant_id=tenant_id, channel=channel)


async def _check_channel(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    channel: Channel,
) -> None:
    """Fetch one channel's WhatsApp phone metadata + persist the snapshot."""
    settings = get_settings()
    cfg = channel.config or {}

    # Per-channel: the phone_number_id belongs to the number, and on a
    # two-WABA tenant so does the token.
    try:
        phone_number_id, access_token = await resolve_send_credentials(
            session, channel_id=channel.id
        )
    except LookupError:
        return

    client = MetaClient(
        app_secret=settings.meta_app_secret,
        require_appsecret_proof=settings.meta_require_appsecret_proof,
        version=settings.meta_graph_api_version,
    )
    try:
        try:
            payload = await client.get_phone_number(
                phone_number_id=phone_number_id,
                access_token=access_token,
            )
        except MetaAPIError as exc:
            log.warning(
                "whatsapp_health.fetch_failed",
                tenant_id=str(tenant_id),
                phone_number_id=phone_number_id,
                status=exc.status_code,
                detail=str(exc),
            )
            channel.last_health_check_at = datetime.now(UTC)
            return
    finally:
        await client.close()

    prior_quality = cfg.get("quality_rating")
    old_status = channel.status
    apply_phone_snapshot(channel, payload)
    new_quality = (channel.config or {}).get("quality_rating")
    channel.last_health_check_at = datetime.now(UTC)
    channel.last_provider_synced_at = datetime.now(UTC)

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
