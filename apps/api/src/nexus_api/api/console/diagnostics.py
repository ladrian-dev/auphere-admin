"""``/console/clients/{ref}/channels/diagnostics`` — CP-19.

The WhatsApp channel is the flow with the most ways to fail, and there
is no on-demand health check in the platform. This router composes one
from what already exists — credentials row, ``needs_reauth``, channel
status and its Meta snapshot, the routing-role rule, the local template
verdict mirror — plus two cheap live probes against the Graph API
(``GET /{waba_id}/subscribed_apps`` and the template list) with a short
timeout that degrade to ``unknown`` instead of failing the page.

Every row is ``ok | warn | fail | unknown`` + a ``what_to_do`` code the
UI translates. Composition is a pure function (:func:`compose_rows`)
over a :class:`DiagnosticsSnapshot` so it is unit-tested with fixtures,
no network.

``POST .../diagnostics/test-send`` sends the pre-approved ``hello_world``
template to one number with the tenant's own BISUAT and leaves a
``console.channel.test_send`` audit row.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from nexus_channels.whatsapp_meta import MetaAPIError
from nexus_channels.whatsapp_meta.credentials import (
    INTEGRATION_KEY,
    MetaCredentials,
    MetaCredentialsRepository,
)
from redis.asyncio import Redis

from nexus_api.api.deps import get_redis
from nexus_api.config import get_settings
from nexus_api.core.rate_limit import allow
from nexus_api.db.models import Channel, ChannelStatus, ChannelType, TenantCredentials
from nexus_api.repositories.audit import AuditRepository
from nexus_api.services.channel_routing import channel_role
from nexus_api.services.whatsapp_templates import build_meta_client, fetch_templates

from .deps import ClientScope, client_scope
from .schemas_channels import DiagnosticRowOut, DiagnosticsOut, TestSendIn, TestSendOut

router = APIRouter(prefix="/clients/{ref}/channels/diagnostics")
log = structlog.get_logger(__name__)

#: How old a health snapshot may be before the row goes yellow.
HEALTH_STALE_AFTER = timedelta(hours=24)
#: Live probes must never hold the page: short timeout, then "unknown".
PROBE_TIMEOUT_SECONDS = 4.0
META_BUSINESS_URL = "https://business.facebook.com/wa/manage/home/"
META_BILLING_URL = "https://business.facebook.com/billing_hub/accounts"


@dataclass(frozen=True)
class ChannelFacts:
    status: str
    role: str | None
    quality_rating: str | None
    messaging_tier: str | None
    last_health_check_at: datetime | None
    identifier: str


@dataclass(frozen=True)
class DiagnosticsSnapshot:
    """Everything :func:`compose_rows` needs. Built by the endpoint from
    the DB + probes; built by tests by hand."""

    now: datetime
    has_credentials: bool
    needs_reauth: bool
    bisuat_expires_at: datetime | None
    channels: list[ChannelFacts] = field(default_factory=list)
    #: ``True`` subscribed, ``False`` not, ``None`` unknown (probe failed).
    webhook_subscribed: bool | None = None
    #: ``None`` when the template probe failed / no credentials.
    templates_approved: int | None = None
    templates_rejected: int | None = None
    templates_pending: int | None = None
    waba_id: str | None = None


def _row(
    key: str,
    state: str,
    what_to_do: str = "none",
    detail: str | None = None,
    link: str | None = None,
) -> DiagnosticRowOut:
    return DiagnosticRowOut.model_validate(
        {"key": key, "state": state, "what_to_do": what_to_do, "detail": detail, "link": link}
    )


def compose_rows(s: DiagnosticsSnapshot) -> list[DiagnosticRowOut]:
    """Pure composition of the diagnostics table. Order = reading order."""
    rows: list[DiagnosticRowOut] = []
    business_link = f"{META_BUSINESS_URL}?waba_id={s.waba_id}" if s.waba_id else META_BUSINESS_URL
    active_wa = [c for c in s.channels if c.status == "active"]

    # 1. credentials
    if not s.has_credentials:
        rows.append(_row("credentials", "fail", "connect_whatsapp"))
    elif s.needs_reauth:
        rows.append(_row("credentials", "fail", "reconnect_whatsapp"))
    elif s.bisuat_expires_at is not None and s.bisuat_expires_at <= s.now:
        rows.append(
            _row("credentials", "fail", "reconnect_whatsapp", s.bisuat_expires_at.isoformat())
        )
    elif s.bisuat_expires_at is not None and s.bisuat_expires_at - s.now < timedelta(days=7):
        rows.append(
            _row("credentials", "warn", "reconnect_whatsapp", s.bisuat_expires_at.isoformat())
        )
    else:
        rows.append(_row("credentials", "ok"))

    # 2. channel status
    if not s.channels:
        rows.append(_row("channel", "fail", "connect_whatsapp"))
    elif not active_wa:
        worst = s.channels[0]
        rows.append(_row("channel", "fail", "activate_channel", worst.status))
    elif any(c.status == "degraded" for c in s.channels):
        rows.append(_row("channel", "warn", "improve_quality", "degraded"))
    else:
        rows.append(_row("channel", "ok", detail=", ".join(c.identifier for c in active_wa)))

    # 3. roles (the refusal rule)
    if len(active_wa) > 1:
        untagged = [c for c in active_wa if c.role is None]
        if untagged:
            rows.append(
                _row("roles", "fail", "assign_roles", ", ".join(c.identifier for c in untagged))
            )
        else:
            rows.append(_row("roles", "ok"))
    else:
        rows.append(_row("roles", "ok"))

    # 4. webhook subscription (live probe)
    if not s.has_credentials:
        rows.append(_row("webhook", "unknown", "connect_whatsapp"))
    elif s.webhook_subscribed is None:
        rows.append(_row("webhook", "unknown", "check_webhook", link=business_link))
    elif s.webhook_subscribed:
        rows.append(_row("webhook", "ok"))
    else:
        rows.append(_row("webhook", "fail", "check_webhook", link=business_link))

    # 5. health snapshot freshness
    stamps = [c.last_health_check_at for c in s.channels if c.last_health_check_at is not None]
    if not s.channels:
        rows.append(_row("health_check", "unknown", "connect_whatsapp"))
    elif not stamps:
        rows.append(_row("health_check", "unknown", "wait_health_check"))
    else:
        latest = max(stamps)
        fresh = s.now - latest < HEALTH_STALE_AFTER
        rows.append(
            _row(
                "health_check",
                "ok" if fresh else "warn",
                "none" if fresh else "wait_health_check",
                latest.isoformat(),
            )
        )

    # 6. quality rating (from the Meta snapshot in channels.config)
    ratings = [c.quality_rating for c in active_wa if c.quality_rating]
    if not ratings:
        rows.append(
            _row("quality", "unknown", "wait_health_check" if s.channels else "connect_whatsapp")
        )
    else:
        rating = "RED" if "RED" in ratings else "YELLOW" if "YELLOW" in ratings else ratings[0]
        state = "fail" if rating == "RED" else "warn" if rating == "YELLOW" else "ok"
        rows.append(
            _row(
                "quality",
                state,
                "improve_quality" if state != "ok" else "none",
                rating,
                business_link,
            )
        )

    # 7. messaging tier (informational)
    tiers = [c.messaging_tier for c in active_wa if c.messaging_tier]
    rows.append(
        _row(
            "messaging_tier",
            "ok" if tiers else "unknown",
            "none",
            tiers[0] if tiers else None,
            business_link,
        )
    )

    # 8. templates
    if s.templates_approved is None:
        rows.append(
            _row(
                "templates",
                "unknown",
                "connect_whatsapp" if not s.has_credentials else "review_templates",
            )
        )
    else:
        approved, rejected, pending = (
            s.templates_approved,
            s.templates_rejected or 0,
            s.templates_pending or 0,
        )
        detail = f"{approved}/{rejected}/{pending}"
        if approved == 0 and rejected == 0 and pending == 0:
            rows.append(_row("templates", "warn", "create_template", detail))
        elif rejected > 0:
            rows.append(_row("templates", "warn", "review_templates", detail))
        else:
            rows.append(_row("templates", "ok", "none", detail))

    # 9. billing / balance — Meta does not expose it to a BISUAT; never invent.
    rows.append(_row("billing", "unknown", "check_meta_billing", link=META_BILLING_URL))
    return rows


# ── endpoint ───────────────────────────────────────────────────────────


async def _probe_webhook(creds: MetaCredentials) -> bool | None:
    settings = get_settings()
    client = build_meta_client()
    try:
        payload = await asyncio.wait_for(
            client.list_subscribed_apps(waba_id=creds.waba_id, access_token=creds.bisuat),
            timeout=PROBE_TIMEOUT_SECONDS,
        )
    except (MetaAPIError, TimeoutError, OSError) as exc:
        log.info("console.diagnostics.webhook_probe_failed", error=str(exc))
        return None
    finally:
        await client.close()
    return webhook_subscribed(payload, app_id=settings.meta_app_id)


def webhook_subscribed(payload: dict[str, object], *, app_id: str) -> bool:
    """``GET /{waba_id}/subscribed_apps`` → is OUR app among them? Pure.

    Meta answers ``{"data": [{"whatsapp_business_api_data": {"id": ..,
    "name": .., "link": ..}}]}``."""
    apps = payload.get("data")
    if not isinstance(apps, list):
        return False
    for entry in apps:
        if not isinstance(entry, dict):
            continue
        data = entry.get("whatsapp_business_api_data")
        ident = data.get("id") if isinstance(data, dict) else entry.get("id")
        if str(ident) == str(app_id):
            return True
    return False


async def _probe_templates(scope: ClientScope) -> tuple[int, int, int] | None:
    try:
        templates, _waba = await asyncio.wait_for(
            fetch_templates(scope.session, use_cache=True), timeout=PROBE_TIMEOUT_SECONDS
        )
    except (HTTPException, TimeoutError, OSError) as exc:
        log.info("console.diagnostics.templates_probe_failed", error=str(exc))
        return None
    st = [(t.status or "").upper() for t in templates]
    return (
        sum(1 for x in st if x == "APPROVED"),
        sum(1 for x in st if x in {"REJECTED", "PAUSED", "DISABLED"}),
        sum(1 for x in st if x in {"PENDING", "IN_APPEAL"}),
    )


@router.get("", response_model=DiagnosticsOut)
async def channel_diagnostics(
    scope: ClientScope = Depends(client_scope("channels:read")),
) -> DiagnosticsOut:
    now = datetime.now(UTC)
    creds = await MetaCredentialsRepository(scope.session).get()
    needs_reauth = bool(
        await scope.session.scalar(
            sa.select(TenantCredentials.needs_reauth).where(
                TenantCredentials.integration == INTEGRATION_KEY
            )
        )
        or False
    )
    channels = (
        (
            await scope.session.execute(
                sa.select(Channel)
                .where(Channel.type == ChannelType.WHATSAPP)
                .order_by(Channel.created_at)
            )
        )
        .scalars()
        .all()
    )
    facts = [
        ChannelFacts(
            status=c.status.value,
            role=channel_role(c),
            quality_rating=(c.config or {}).get("quality_rating")
            if isinstance((c.config or {}).get("quality_rating"), str)
            else None,
            messaging_tier=(c.config or {}).get("messaging_tier")
            if isinstance((c.config or {}).get("messaging_tier"), str)
            else None,
            last_health_check_at=c.last_health_check_at,
            identifier=c.provider_identifier,
        )
        for c in channels
    ]
    webhook: bool | None = None
    counts: tuple[int, int, int] | None = None
    if creds is not None:
        webhook = await _probe_webhook(creds)
        counts = await _probe_templates(scope)
    snapshot = DiagnosticsSnapshot(
        now=now,
        has_credentials=creds is not None,
        needs_reauth=needs_reauth,
        bisuat_expires_at=creds.bisuat_expires_at if creds else None,
        channels=facts,
        webhook_subscribed=webhook,
        templates_approved=counts[0] if counts else None,
        templates_rejected=counts[1] if counts else None,
        templates_pending=counts[2] if counts else None,
        waba_id=creds.waba_id if creds else None,
    )
    rows = compose_rows(snapshot)
    return DiagnosticsOut(rows=rows, checked_at=now, healthy=all(r.state != "fail" for r in rows))


@router.post("/test-send", response_model=TestSendOut)
async def test_send(
    body: TestSendIn,
    scope: ClientScope = Depends(client_scope("channels:write")),
    redis: Redis = Depends(get_redis),
) -> TestSendOut:
    # A test send is a real, billed WhatsApp message to any number: cap it
    # per partner so the endpoint cannot be turned into a spam cannon.
    if not await allow(
        redis,
        key=f"console:test_send:{scope.principal.partner.id}",
        per_minute=5,
        surface="console",
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many test sends — wait a minute before trying again.",
        )
    creds = await MetaCredentialsRepository(scope.session).get()
    if creds is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="WhatsApp is not connected for this client. Connect it first.",
        )
    if not any(
        c.status is ChannelStatus.ACTIVE
        for c in (
            await scope.session.execute(
                sa.select(Channel).where(Channel.type == ChannelType.WHATSAPP)
            )
        ).scalars()
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="No active WhatsApp channel."
        )
    client = build_meta_client()
    try:
        try:
            result = await client.send_template(
                phone_number_id=creds.phone_number_id,
                access_token=creds.bisuat,
                to=body.to,
                template_name="hello_world",
                language=body.language,
            )
        except MetaAPIError as exc:
            http_status = (
                status.HTTP_502_BAD_GATEWAY
                if exc.status_code and exc.status_code >= 500
                else status.HTTP_400_BAD_REQUEST
            )
            raise HTTPException(
                status_code=http_status, detail=f"Meta rejected the send: {exc.message}"
            ) from exc
    finally:
        await client.close()
    messages = result.get("messages") or []
    wamid = messages[0].get("id") if messages and isinstance(messages[0], dict) else None
    if not isinstance(wamid, str):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Meta returned no message id."
        )
    await AuditRepository(scope.session).record(
        actor=scope.principal.actor,
        action="console.channel.test_send",
        target=f"channel:meta:{creds.display_phone_number}",
        after={"to": body.to, "template": "hello_world", "wamid": wamid},
    )
    return TestSendOut(status="sent", wamid=wamid, to=body.to)


__all__ = ["ChannelFacts", "DiagnosticsSnapshot", "compose_rows", "router"]
