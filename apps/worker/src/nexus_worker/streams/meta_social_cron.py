"""Instagram / Messenger upkeep — spec 049, requirements 5.3 and 5.7.

Two jobs on one tick (6 h), per tenant, inside a tenant-scoped session:

1. **Health.** For each active Instagram account and Page: the token still
   works and Auphere is still subscribed. Meta drops a Page's subscription
   after an hour of failed deliveries; the cron subscribes it again. A
   revoked token, a lost permission or messages switched off move the
   channel to ``degraded`` with the reason the console explains; a channel
   that answers again goes back to ``active``.
2. **Retention.** A channel disconnected 30 days ago has its people
   anonymised (``meta_social_retention.purge_channel``) and an audit row.

Tenant discovery reads ``tenants`` (global); everything else is per tenant,
the same shape as ``whatsapp_health_cron``.
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
from nexus_api.db.models import AuditLog, Channel, ChannelStatus, Tenant
from nexus_api.services.channel_config import health_degraded, set_health
from nexus_api.services.meta_social_retention import due_for_purge, purge_channel
from nexus_api.services.meta_social_service import PROBLEM_REASON_OF
from nexus_channels.meta_social import META_SOCIAL_PROVIDERS, MetaSocialClient
from nexus_channels.meta_social.connect import MetaSocialConnector
from redis.asyncio import Redis

log = structlog.get_logger(__name__)

DEFAULT_TICK_SECONDS = 6 * 3600.0
ACTOR = "system:meta_social_cron"


async def run_meta_social_cron(
    *,
    stop: asyncio.Event,
    redis: Redis,
    tick_seconds: float = DEFAULT_TICK_SECONDS,
) -> None:
    settings = get_settings()
    client = MetaSocialClient(
        settings.meta_app_secret,
        version=settings.meta_social_graph_api_version,
        require_appsecret_proof=settings.meta_require_appsecret_proof,
    )
    sm = get_sessionmaker()
    log.info("meta_social_cron.start", tick_seconds=tick_seconds)
    try:
        while not stop.is_set():
            try:
                async with sm() as session:
                    # Every tenant, archived ones included: retention does not
                    # stop because the client left.
                    tenant_ids = list((await session.scalars(sa.select(Tenant.id))).all())
                for tid in tenant_ids:
                    if stop.is_set():
                        break
                    await tick_tenant(tid, client=client, redis=redis, app_id=settings.meta_app_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("meta_social_cron.tick_failed", error=str(exc))
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    finally:
        await client.close()
    log.info("meta_social_cron.stopped")


async def tick_tenant(
    tenant_id: uuid.UUID, *, client: MetaSocialClient, redis: Redis, app_id: str
) -> None:
    sm = get_sessionmaker()
    now = datetime.now(UTC)
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        channels = (
            await session.scalars(
                sa.select(Channel).where(Channel.provider.in_(tuple(META_SOCIAL_PROVIDERS)))
            )
        ).all()
        connector = MetaSocialConnector(session=session, redis=redis, client=client, app_id=app_id)
        for channel in channels:
            if channel.status is ChannelStatus.DISCONNECTED:
                if due_for_purge(channel, now=now):
                    people = await purge_channel(session, channel)
                    session.add(
                        AuditLog(
                            tenant_id=tenant_id,
                            actor=ACTOR,
                            action="channel.meta_social.purge",
                            target=f"channel:{channel.id}",
                            before_json=None,
                            after_json={
                                "display_name": _display(channel),
                                "people": people,
                            },
                        )
                    )
                    log.info("meta_social_cron.purged", tenant_id=str(tenant_id), people=people)
                continue
            try:
                health = await connector.check(channel)
            except Exception as exc:
                log.warning(
                    "meta_social_cron.check_failed",
                    channel_id=str(channel.id),
                    error=type(exc).__name__,
                )
                continue
            channel.last_health_check_at = now
            cfg = dict(channel.config or {})
            # A paused channel stays paused: set_health changes what resuming returns.
            if health.ok:
                if health_degraded(channel) and cfg.get("needs_attention"):
                    cfg.pop("needs_attention", None)
                    channel.config = cfg
                    set_health(channel, degraded=False)
                    channel.problem_reason = None
                if health.resubscribed:
                    log.info("meta_social_cron.resubscribed", channel_id=str(channel.id))
            elif cfg.get("needs_attention") != health.reason:
                cfg["needs_attention"] = health.reason
                channel.config = cfg
                set_health(channel, degraded=True)
                channel.problem_reason = PROBLEM_REASON_OF.get(str(health.reason), "meta_error")
                session.add(
                    AuditLog(
                        tenant_id=tenant_id,
                        actor=ACTOR,
                        action="channel.meta_social.needs_attention",
                        target=f"channel:{channel.id}",
                        before_json=None,
                        after_json={"display_name": _display(channel), "reason": health.reason},
                    )
                )
        await session.flush()


def _display(channel: Channel) -> str:
    cfg = channel.config or {}
    if cfg.get("username"):
        return f"@{cfg['username']}"
    return str(cfg.get("name") or channel.provider_identifier)
