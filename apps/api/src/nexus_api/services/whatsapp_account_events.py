"""Spec 050 (D5) — what Meta says about a WhatsApp account and its templates.

The webhook router hands every account and template field here
(``contracts/webhook-events.md``). Two rules hold for all of them:

- **Attribution.** An event that names a number (``display_phone_number`` /
  ``phone_number``) goes to the business that has that number, as today. One
  that only names the WABA (``entry[].id`` or ``waba_info.waba_id``) goes to
  every business with live numbers in that WABA, through
  ``resolve_waba_tenants`` (SECURITY DEFINER, tenant ids only), and is applied
  **under each business's RLS** to its own numbers of that WABA. A WABA nobody
  has is ignored.
- **Where a problem comes from.** A problem an account event sets carries
  ``config.problem_source = "account"`` and is cleared only by its opposite
  event (reconnected, review approved, alert gone); the health cron clears
  only the ones it set itself (``"quality"``).

The partner hears about it through ``channel_config.announce``, after the
change is committed and never in a way that can undo it.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
import structlog
from redis.asyncio import Redis
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.errors import TenantNotFound
from nexus_api.core.metrics import CHANNEL_UNRESOLVED_EVENT, counters
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.core.tenant_resolver import resolve_tenant
from nexus_api.db.models import AuditLog, Channel, ChannelStatus, WhatsAppTemplateStatus
from nexus_api.services.whatsapp_templates import invalidate_template_cache

log = structlog.get_logger(__name__)

TEMPLATE_FIELDS = frozenset(
    {
        "message_template_status_update",
        "message_template_quality_update",
        "template_category_update",
    }
)
ACCOUNT_FIELDS = frozenset(
    {
        "account_update",
        "account_alerts",
        "account_review_update",
        "business_capability_update",
        "phone_number_name_update",
        "phone_number_quality_update",
        "business_username_updates",
    }
)

#: Spec 047 (30.11): what ``account_update`` says about a number, as the reason
#: of «Con problemas». An event not listed only lands in ``config``.
ACCOUNT_PROBLEMS: dict[str, str] = {
    # Auphere's app no longer has access: connect again.
    "PARTNER_REMOVED": "auth_expired",
    # Coexistence: the business stopped opening the app (~14 days) or unlinked it.
    "ACCOUNT_OFFBOARDED": "coexistence_inactive",
    "PARTNER_APP_UNINSTALLED": "coexistence_inactive",
    # Meta restricted or removed the account.
    "ACCOUNT_DELETED": "meta_error",
    "ACCOUNT_RESTRICTION": "meta_error",
    "DISABLED_UPDATE": "meta_error",
}
#: The reasons only an account event sets (and its opposite clears).
ACCOUNT_REASONS = frozenset({*ACCOUNT_PROBLEMS.values(), "account_review", "account_alert"})

#: A template in one of these states can no longer be sent: the partner hears.
TEMPLATE_BLOCKED: dict[str, str] = {
    "PAUSED": "template.paused",
    "DISABLED": "template.disabled",
    "REJECTED": "template.rejected",
    "LOCKED": "template.disabled",
    "DELETED": "template.disabled",
}
_QUALITY_RANK = {"GREEN": 0, "UNKNOWN": 0, "YELLOW": 1, "RED": 2}
#: How many alerts ``config.alerts`` keeps, newest last.
ALERTS_KEPT = 20


@dataclass
class Notice:
    kind: str
    severity: str
    data: dict[str, Any]
    dedupe_key: str
    to_client: bool = False


@dataclass
class Change:
    """What applying an event to one channel did: whether it changed, what
    the audit says and whom to tell."""

    changed: bool = False
    audit: dict[str, Any] | None = None
    notices: list[Notice] = field(default_factory=list)


# ── entry point ─────────────────────────────────────────────────────────────


async def handle(
    field_name: str, payload: dict[str, Any], *, session: AsyncSession, redis: Redis
) -> str:
    """Apply one single-element envelope of an account or template field."""
    entry = (payload.get("entry") or [{}])[0]
    value = (entry.get("changes") or [{}])[0].get("value") or {}
    if not isinstance(value, dict):
        return "ignored"
    waba_id = _waba_of(entry, value)
    if field_name in TEMPLATE_FIELDS:
        return await _template_event(field_name, value, waba_id=waba_id, session=session)
    apply = _ACCOUNT_APPLIERS.get(field_name)
    if apply is None:
        return "ignored"
    return await _account_event(
        field_name, value, apply, waba_id=waba_id, session=session, redis=redis
    )


def _waba_of(entry: dict[str, Any], value: dict[str, Any]) -> str:
    info = value.get("waba_info")
    if isinstance(info, dict) and info.get("waba_id"):
        return str(info["waba_id"])
    return str(entry.get("id") or "")


async def waba_tenants(session: AsyncSession, waba_id: str) -> list[uuid.UUID]:
    """The businesses with live numbers in ``waba_id`` (ids only)."""
    if not waba_id:
        return []
    rows = await session.execute(sa.text("SELECT resolve_waba_tenants(:w)"), {"w": waba_id})
    tenants = [r[0] for r in rows]
    if session.in_transaction():
        await session.rollback()
    return tenants


def _digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


# ── templates ───────────────────────────────────────────────────────────────


async def _template_event(
    field_name: str, value: dict[str, Any], *, waba_id: str, session: AsyncSession
) -> str:
    name = str(value.get("message_template_name") or value.get("name") or "")
    language = str(value.get("message_template_language") or value.get("language") or "")
    if not waba_id or not name:
        return "ignored"
    tenants = await waba_tenants(session, waba_id)
    existing = await session.scalar(
        sa.select(WhatsAppTemplateStatus).where(
            WhatsAppTemplateStatus.waba_id == waba_id,
            WhatsAppTemplateStatus.template_name == name,
            WhatsAppTemplateStatus.language == language,
        )
    )
    columns: dict[str, Any] = {}
    notice: tuple[str, dict[str, Any]] | None = None
    if field_name == "message_template_status_update":
        status = str(value.get("event") or "").upper()
        if not status:
            return "ignored"
        columns["status"] = status
        columns["reason"] = value.get("reason") if isinstance(value.get("reason"), str) else None
        if isinstance(value.get("message_template_category"), str):
            columns["category"] = value["message_template_category"]
        kind = TEMPLATE_BLOCKED.get(status)
        if kind is not None and (existing is None or existing.status.upper() != status):
            notice = (kind, {"reason": columns["reason"], "status": status})
    elif field_name == "message_template_quality_update":
        quality = str(value.get("new_quality_score") or "").upper()
        if not quality:
            return "ignored"
        columns["quality"] = quality
        before = str(
            value.get("previous_quality_score") or (existing.quality if existing else "") or "GREEN"
        )
        if _QUALITY_RANK.get(quality, 0) > _QUALITY_RANK.get(before.upper(), 0):
            notice = ("template.quality_dropped", {"quality": quality, "previous": before.upper()})
    else:  # template_category_update
        new = value.get("new_category")
        if isinstance(value.get("correct_category"), str):
            # Announced ~24 h before Meta applies it.
            columns["pending_category"] = value["correct_category"]
            notice = (
                "template.recategorized",
                {"category": value["correct_category"], "applied": False},
            )
        elif isinstance(new, str):
            columns["category"] = new
            columns["previous_category"] = value.get("previous_category")
            columns["pending_category"] = None
            notice = ("template.recategorized", {"category": new, "applied": True})
        else:
            return "ignored"

    now = datetime.now(tz=UTC)
    tenant_id = tenants[0] if tenants else (existing.tenant_id if existing else None)
    insert_values = {
        "waba_id": waba_id,
        "template_name": name,
        "language": language,
        "status": columns.get("status") or (existing.status if existing else "UNKNOWN"),
        "tenant_id": tenant_id,
        "last_event_payload": {"field": field_name, "value": value},
        "last_event_at": now,
        **{k: v for k, v in columns.items() if k != "status"},
    }
    stmt = pg_insert(WhatsAppTemplateStatus).values(**insert_values)
    update = {
        k: getattr(stmt.excluded, k)
        for k in insert_values
        if k not in {"waba_id", "template_name", "language"}
    }
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=["waba_id", "template_name", "language"], set_=update
        )
    )
    await session.commit()
    # A template Meta just paused, recategorised or re-scored must be read
    # fresh by the next send, not when the cache happens to expire.
    invalidate_template_cache(waba_id)
    log.info(
        "webhook.meta.template_event",
        field=field_name,
        waba_id=waba_id,
        template_name=name,
        **columns,
    )

    if notice is not None:
        from nexus_api.services.channel_config import announce

        kind, extra = notice
        for tid in tenants:
            await announce(
                tenant_id=tid,
                kind=kind,
                severity="info" if kind == "template.recategorized" else "warning",
                data={"template_name": name, "language": language, **extra},
                dedupe_key=f"{kind}:{waba_id}:{name}:{language}:{extra.get('status') or extra.get('quality') or extra.get('category')}:{extra.get('applied', '')}",
            )
    return "applied"


# ── account ─────────────────────────────────────────────────────────────────


Applier = Callable[[Channel, dict[str, Any]], Change]


def _target_phone(field_name: str, value: dict[str, Any]) -> str:
    return _digits(value.get("display_phone_number") or value.get("phone_number"))


def _target_pnid(field_name: str, value: dict[str, Any]) -> str | None:
    if (
        field_name == "account_alerts"
        and str(value.get("entity_type") or "").upper() == "PHONE_NUMBER"
    ):
        return str(value.get("entity_id") or "") or None
    return None


async def _account_event(
    field_name: str,
    value: dict[str, Any],
    apply: Applier,
    *,
    waba_id: str,
    session: AsyncSession,
    redis: Redis,
) -> str:
    phone = _target_phone(field_name, value)
    pnid = _target_pnid(field_name, value)
    if phone:
        # Names a number: the business that has it, as before spec 050.
        try:
            tenants = [await resolve_tenant(session, redis, "meta", f"+{phone}")]
        except TenantNotFound:
            counters.incr(CHANNEL_UNRESOLVED_EVENT)
            log.warning("channel.unresolved_event", provider="meta", field=field_name)
            return "ignored"
        if session.in_transaction():
            await session.rollback()
    else:
        tenants = await waba_tenants(session, waba_id)
    if not tenants:
        log.info("webhook.meta.account_event_unowned", field=field_name, waba_id=waba_id)
        return "ignored"

    applied = False
    for tenant_id in tenants:
        notices: list[Notice] = []
        async with tenant_scoped_session(session, tenant_id):
            query = sa.select(Channel).where(
                Channel.provider == "meta", Channel.status != ChannelStatus.DISCONNECTED
            )
            if not phone:
                query = query.where(Channel.config["waba_id"].astext == waba_id)
            for channel in (await session.scalars(query)).all():
                if phone and _digits(channel.provider_identifier) != phone:
                    continue
                if pnid and str((channel.config or {}).get("phone_number_id") or "") != pnid:
                    continue
                change = apply(channel, value)
                if not change.changed:
                    continue
                applied = True
                if change.audit is not None:
                    session.add(
                        AuditLog(
                            tenant_id=tenant_id,
                            actor="meta",
                            action=change.audit.pop("action"),
                            target=f"channel:{channel.id}",
                            after_json=change.audit,
                        )
                    )
                for notice in change.notices:
                    notice.data.setdefault("channel_id", str(channel.id))
                    if channel.agent_id is not None:
                        notice.data.setdefault("agent_id", str(channel.agent_id))
                    notices.append(notice)
        if notices:
            from nexus_api.services.channel_config import announce

            for notice in notices:
                await announce(
                    tenant_id=tenant_id,
                    kind=notice.kind,
                    severity=notice.severity,
                    data=notice.data,
                    dedupe_key=f"{notice.dedupe_key}:{notice.data['channel_id']}",
                    to_client=notice.to_client,
                )
    log.info("webhook.meta.account_event", field=field_name, waba_id=waba_id, applied=applied)
    return "applied" if applied else "unchanged"


def _config(channel: Channel, **updates: Any) -> bool:
    """Merge ``updates`` into ``channel.config``; whether anything changed."""
    current = dict(channel.config or {})
    merged = {**current, **updates}
    if merged == current:
        return False
    channel.config = merged
    return True


def _set_problem(channel: Channel, reason: str) -> bool:
    if channel.status is ChannelStatus.DEGRADED and channel.problem_reason == reason:
        return False
    channel.status = ChannelStatus.DEGRADED
    channel.problem_reason = reason
    _config(channel, problem_source="account")
    return True


def _clear_problem(channel: Channel, reasons: frozenset[str]) -> bool:
    cfg = channel.config or {}
    source = cfg.get("problem_source")
    if channel.status is not ChannelStatus.DEGRADED or channel.problem_reason not in reasons:
        return False
    if source not in (None, "account"):
        return False
    channel.status = ChannelStatus.ACTIVE
    channel.problem_reason = None
    channel.config = {k: v for k, v in cfg.items() if k != "problem_source"}
    return True


def _account_update(channel: Channel, value: dict[str, Any]) -> Change:
    event = str(value.get("event") or "").upper()
    reason = ACCOUNT_PROBLEMS.get(event)
    if reason is not None:
        if not _set_problem(channel, reason):
            return Change()
        return Change(
            changed=True,
            audit={"action": "channel.problem", "event": event, "reason": reason},
            notices=[
                Notice(
                    kind="channel.problem",
                    severity="critical",
                    data={"reason": reason},
                    dedupe_key=f"channel.problem:{reason}",
                    to_client=True,
                )
            ],
        )
    if event == "ACCOUNT_RECONNECTED":
        if not _clear_problem(channel, ACCOUNT_REASONS):
            return Change()
        return Change(
            changed=True, audit={"action": "channel.whatsapp.account_state", "event": event}
        )
    if event == "VOLUME_BASED_PRICING_TIER_UPDATE":
        info = value.get("volume_tier_info")
        return Change(
            changed=_config(channel, pricing_tier=info if isinstance(info, dict) else None)
        )
    # Anything else Meta says about the account stays readable, nothing more.
    return Change(changed=_config(channel, last_account_event=event or None))


def _account_alerts(channel: Channel, value: dict[str, Any]) -> Change:
    raw = value.get("alert_info")
    info: dict[str, Any] = raw if isinstance(raw, dict) else {}
    alert = {
        "type": info.get("alert_type"),
        "severity": str(info.get("alert_severity") or "").upper() or None,
        "status": str(info.get("alert_status") or "").upper() or None,
        "at": datetime.now(tz=UTC).isoformat(),
    }
    alerts = [a for a in (channel.config or {}).get("alerts") or [] if isinstance(a, dict)]
    _config(channel, alerts=[*alerts, alert][-ALERTS_KEPT:])
    change = Change(changed=True)
    if alert["severity"] == "CRITICAL" and alert["status"] == "ACTIVE":
        if _set_problem(channel, "account_alert"):
            change.audit = {"action": "channel.whatsapp.account_state", "alert": alert["type"]}
            change.notices.append(
                Notice(
                    kind="channel.account_alert",
                    severity="critical",
                    data={"alert": alert["type"]},
                    dedupe_key=f"channel.account_alert:{alert['type']}",
                    to_client=True,
                )
            )
    elif alert["status"] != "ACTIVE":
        _clear_problem(channel, frozenset({"account_alert"}))
    return change


def _account_review(channel: Channel, value: dict[str, Any]) -> Change:
    decision = str(value.get("decision") or "").upper()
    if not decision:
        return Change()
    changed = _config(channel, account_review=decision)
    if decision in {"REJECTED", "DEFERRED"}:
        if _set_problem(channel, "account_review"):
            return Change(
                changed=True,
                audit={"action": "channel.whatsapp.account_state", "review": decision},
                notices=[
                    Notice(
                        kind="channel.account_review",
                        severity="critical",
                        data={"decision": decision},
                        dedupe_key=f"channel.account_review:{decision}",
                        to_client=True,
                    )
                ],
            )
    elif decision == "APPROVED":
        changed = _clear_problem(channel, frozenset({"account_review"})) or changed
    return Change(changed=changed)


def _capability(channel: Channel, value: dict[str, Any]) -> Change:
    updates: dict[str, Any] = {}
    if value.get("max_daily_conversations_per_business"):
        updates["messaging_limit"] = value["max_daily_conversations_per_business"]
    if value.get("max_phone_numbers_per_waba") is not None:
        updates["max_phone_numbers_per_waba"] = value["max_phone_numbers_per_waba"]
    return Change(changed=_config(channel, **updates))


def _phone_quality(channel: Channel, value: dict[str, Any]) -> Change:
    updates: dict[str, Any] = {}
    if value.get("max_daily_conversations_per_business"):
        updates["messaging_limit"] = value["max_daily_conversations_per_business"]
    if value.get("event"):
        updates["limit_event"] = value["event"]
    return Change(changed=_config(channel, **updates))


def _name_update(channel: Channel, value: dict[str, Any]) -> Change:
    decision = str(value.get("decision") or "").upper()
    if not decision:
        return Change()
    reason = value.get("rejection_reason")
    changed = _config(
        channel,
        name_decision=decision,
        requested_name=value.get("requested_verified_name"),
        name_rejection_reason=reason if decision == "REJECTED" else None,
    )
    if not changed:
        return Change()
    change = Change(
        changed=True,
        audit={"action": "channel.whatsapp.name_decision", "decision": decision, "reason": reason},
    )
    if decision == "REJECTED":
        change.notices.append(
            Notice(
                kind="channel.name_rejected",
                severity="warning",
                data={"reason": reason, "requested_name": value.get("requested_verified_name")},
                dedupe_key=f"channel.name_rejected:{value.get('requested_verified_name')}",
            )
        )
    return change


def _username(channel: Channel, value: dict[str, Any]) -> Change:
    return Change(
        changed=_config(
            channel, username=value.get("username"), username_status=value.get("status")
        )
    )


_ACCOUNT_APPLIERS: dict[str, Applier] = {
    "account_update": _account_update,
    "account_alerts": _account_alerts,
    "account_review_update": _account_review,
    "business_capability_update": _capability,
    "phone_number_quality_update": _phone_quality,
    "phone_number_name_update": _name_update,
    "business_username_updates": _username,
}
