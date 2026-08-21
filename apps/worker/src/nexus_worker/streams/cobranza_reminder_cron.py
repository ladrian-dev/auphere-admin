"""Cobranza due-date reminders — a daily sweep at the business's local hour,
plus the same engine on demand from ``billing.send_reminders``.

History, because it explains the shape of this module. The original version
swept every tenant hourly on its own. ADR-027 (2026-07-26) removed that and
made reminders admin-triggered only. The 2026-08-21 audit of Muna showed the
result: **not one reminder went out in six weeks**, and 55 of 58 accounts with
a balance had permanently missed their windows. Two reasons, and both are
fixed here:

1. Nobody triggered it. An on-demand action that has to be requested on
   exactly the right day is an action that never happens. The daily cron is
   back (ADR-035), now at the tenant's LOCAL hour instead of a UTC tick.
2. The windows were exact-day equalities (``delta == 3``). Miss the day and
   the account was never chased again. They are RANGES now.

Per account (pending balance, not CANCELLED, with a phone and a due date):

    due in 1..3 days   → ``recordatorio_pago_proximo``   (stage ``T-3``)
    due today          → ``recordatorio_pago_proximo``   (stage ``T0``)
    7+ days overdue    → ``recordatorio_pago_vencido``   (stage ``T+7``)

Each stage fires ONCE per (account, due date) — see ``_queue_reminder``. That
is why the due date is part of the idempotency key and not just the account:
the anti-duplicate policy in the prompt tells admins to add a new charge to an
EXISTING account rather than create a second one, so the same account id
legitimately comes back around with a new due date, and keying on the account
alone would silence it forever.

Guards, in order:
1. **Template approval** — the tenant's WABA must report the template as
   APPROVED (Meta rejects unapproved sends anyway).
2. **Age cap** — an account more than ``max_overdue_days`` past due is left
   alone. Switching the cron on against a portfolio nobody has chased in
   months should not fire a year-old debt at a customer.
3. **Run cap** — at most ``max_per_run`` reminders per sweep, most urgent
   first, and what got deferred is LOGGED. A cap that truncates silently
   reads as "there was nothing else to send".
4. **Opt-out** — a debtor who replied BAJA/STOP is skipped, on ANY of the
   business's numbers (see ``_queue_reminder``).
5. **Idempotency** — (account, stage, due date) already sent is never re-sent,
   so the daily sweep and a manual run on the same day are both safe.

Reminders are queued as pending template messages; the existing outbound
dispatcher delivers them (retries, wamid, status callbacks included).

Which number they leave from: the channel tagged ``role=notifications``. A
business with a single active WhatsApp line keeps the old behaviour (that line
is used, tagged or not). A business with two and no tag gets a refusal rather
than a guess — see :mod:`nexus_api.services.channel_routing`.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import sqlalchemy as sa
import structlog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AgentConfig,
    AgentConfigStatus,
    Channel,
    Message,
    MessageDirection,
    MessageStatus,
    Tenant,
    TenantStatus,
    WhatsAppOptOut,
)
from nexus_api.services.channel_routing import (
    CHANNEL_ROLE_NOTIFICATIONS,
    ChannelResolutionError,
    describe_channel,
    resolve_whatsapp_channel,
)
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)

MAX_PAGES = 20

TEMPLATE_PROXIMO = "recordatorio_pago_proximo"
TEMPLATE_VENCIDO = "recordatorio_pago_vencido"
LANGUAGE = "es"

#: Stage windows, in the order they are evaluated. ``lo``/``hi`` bound
#: ``delta = (due - today).days`` inclusively; ``None`` means unbounded.
#: Ordered by urgency — it is also the order the run cap truncates in.
_STAGES: tuple[tuple[str, str, int | None, int | None], ...] = (
    # (stage, template, lo, hi)
    ("T0", TEMPLATE_PROXIMO, 0, 0),  # vence hoy
    ("T-3", TEMPLATE_PROXIMO, 1, 3),  # vence en 1..3 días
    ("T+7", TEMPLATE_VENCIDO, None, -7),  # 7 o más días vencida
)

# ── cron defaults (overridable per tenant in policies.reminders) ──────────

DEFAULT_TICK_SECONDS = 3600.0
#: Local hour of day the sweep runs at. 9am is inside any reasonable
#: contact window for a collections vertical.
DEFAULT_HOUR_LOCAL = 9
#: Debts older than this are not chased automatically. An admin can still
#: ask for them explicitly via ``billing.send_reminders``.
DEFAULT_MAX_OVERDUE_DAYS = 30
#: Ceiling per sweep, so switching the cron on for a neglected portfolio
#: does not fan out hundreds of messages in one minute.
DEFAULT_MAX_PER_RUN = 50

#: Redis key marking "this tenant already swept on this local day". The
#: guard is an optimisation, not the correctness boundary — that is the
#: per-(account, stage, due) idempotency in ``_queue_reminder``, which
#: holds even if this key is lost.
_DAY_MARKER_TTL_SECONDS = 60 * 60 * 36


class ReminderConfig:
    """Per-tenant reminder settings, read from ``policies.reminders``."""

    __slots__ = ("enabled", "hour_local", "max_overdue_days", "max_per_run")

    def __init__(self, raw: Any = None) -> None:
        data = raw if isinstance(raw, dict) else {}
        self.enabled = bool(data.get("enabled", False))
        self.hour_local = _clamp_int(data.get("hour_local"), DEFAULT_HOUR_LOCAL, 0, 23)
        self.max_overdue_days = _clamp_int(
            data.get("max_overdue_days"), DEFAULT_MAX_OVERDUE_DAYS, 7, 3650
        )
        self.max_per_run = _clamp_int(data.get("max_per_run"), DEFAULT_MAX_PER_RUN, 1, 1000)


def _clamp_int(value: Any, default: int, lo: int, hi: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, parsed))


def _zone(tz_name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        log.warning("cobranza_reminder.unknown_timezone", timezone=tz_name)
        return ZoneInfo("UTC")


def local_today(tz_name: str | None, *, now: datetime | None = None) -> date:
    """The business's calendar date — never UTC's.

    A tenant in ``America/Caracas`` (UTC-4) is still on the previous day
    while UTC has already rolled over. With windows this narrow, computing
    "today" in UTC shifts a whole stage for every evening run.
    """
    return (now or datetime.now(UTC)).astimezone(_zone(tz_name)).date()


# ── the cron ─────────────────────────────────────────────────────────────


async def run_cobranza_reminder_cron(
    *,
    stop: asyncio.Event,
    redis: Any,
    tick_seconds: float = DEFAULT_TICK_SECONDS,
) -> None:
    """Background task: one pass per ``tick_seconds`` (default hourly).

    Each pass, for every ACTIVE tenant whose active agent has
    ``policies.reminders.enabled``, fires the sweep when the tenant's LOCAL
    clock is at its configured hour — at most once per local day.
    """
    log.info("cobranza_reminder_cron.start", tick_seconds=tick_seconds)
    while not stop.is_set():
        try:
            await _cron_pass(redis)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("cobranza_reminder_cron.tick_failed", error=str(exc))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info("cobranza_reminder_cron.stopped")


async def _cron_pass(redis: Any, *, now: datetime | None = None) -> None:
    """One sweep pass over every active tenant.

    The tenant list and the per-tenant config are read in SEPARATE sessions on
    purpose. ``tenants`` is the root mapping and carries no RLS, but
    ``agent_configs`` is RLS-**forced** and fails closed: a policy that reads
    ``current_setting('app.tenant_id')`` returns NULL without it, so the row is
    excluded. Joining the two on an unscoped session returns zero rows — no
    error, no log, a cron that simply never fires. That is precisely the class
    of silent failure this module exists to stop repeating.
    """
    sm = get_sessionmaker()
    async with sm() as session:
        tenants = (
            await session.execute(
                sa.select(Tenant.id, Tenant.name, Tenant.timezone).where(
                    Tenant.status == TenantStatus.ACTIVE
                )
            )
        ).all()

    now_utc = now or datetime.now(UTC)
    for tenant_id, tenant_name, tz_name in tenants:
        async with sm() as session, tenant_scoped_session(session, tenant_id):
            policies = await session.scalar(
                sa.select(AgentConfig.policies)
                .where(AgentConfig.status == AgentConfigStatus.ACTIVE)
                .order_by(AgentConfig.version.desc())
                .limit(1)
            )
        config = ReminderConfig((policies or {}).get("reminders"))
        if not config.enabled:
            continue
        local = now_utc.astimezone(_zone(tz_name))
        if local.hour != config.hour_local:
            continue
        if not await _claim_local_day(redis, tenant_id, local.date()):
            continue
        try:
            result = await send_due_reminders_for_tenant(
                tenant_id,
                tenant_name or "",
                today=local.date(),
                config=config,
                source="cron",
            )
        except Exception as exc:
            log.error(
                "cobranza_reminder_cron.tenant_failed",
                tenant_id=str(tenant_id),
                error=f"{type(exc).__name__}: {exc}",
            )
            continue
        log.info(
            "cobranza_reminder_cron.swept",
            tenant_id=str(tenant_id),
            local_day=local.date().isoformat(),
            status=result.get("status"),
            queued=result.get("queued"),
            deferred=result.get("deferred"),
        )


async def _claim_local_day(redis: Any, tenant_id: uuid.UUID, local_day: date) -> bool:
    """True the first time this tenant is swept on ``local_day``.

    Best-effort: if Redis is unreachable we sweep anyway. Re-sending is not
    a risk — the (account, stage, due) idempotency below is what actually
    prevents a duplicate reminder, and it lives in Postgres.
    """
    key = f"nexus:cobranza_reminder:{tenant_id}:{local_day.isoformat()}"
    try:
        claimed = await redis.set(key, "1", nx=True, ex=_DAY_MARKER_TTL_SECONDS)
    except Exception as exc:
        log.warning(
            "cobranza_reminder_cron.day_marker_unavailable",
            tenant_id=str(tenant_id),
            error=str(exc),
        )
        return True
    return bool(claimed)


# ── the engine (shared by the cron and billing.send_reminders) ────────────


async def send_due_reminders_for_tenant(
    tenant_id: uuid.UUID,
    tenant_name: str,
    *,
    today: date | None = None,
    config: ReminderConfig | None = None,
    source: str = "manual",
) -> dict[str, Any]:
    """Queue every due-date reminder for ONE business, right now.

    Returns a summary the agent (or the cron log) can report back:

        {"status": "ok"|"no_connector"|"no_channel"|
                    "templates_not_approved"|"no_due_accounts",
         "queued": int,
         "deferred": int,
         "recipients": [{"cliente", "stage", "monto", "fecha"}, ...]}

    Idempotency (account+stage+due already sent) means a repeat call the
    same day queues nothing new.
    """
    # Lazy import: keeps the MCP surface off this module's import path.
    from nexus_mcp.servers.amigable_cobro.tools import (
        AmigableCobroNotConfigured,
        _load_amigable_client,
    )

    sm = get_sessionmaker()
    try:
        client = await _load_amigable_client(tenant_id)
    except AmigableCobroNotConfigured:
        return {"status": "no_connector", "queued": 0, "deferred": 0, "recipients": []}

    async with sm() as session, tenant_scoped_session(session, tenant_id):
        if today is None or config is None:
            # The manual path (``billing.send_reminders``) arrives with
            # neither, so resolve both from the tenant here: the local date
            # so "today" is the business's, and the caps so a manual run
            # obeys the same age/volume limits as the cron.
            tz_name = await session.scalar(sa.select(Tenant.timezone).where(Tenant.id == tenant_id))
            policies: dict[str, Any] = (
                await session.scalar(
                    sa.select(AgentConfig.policies)
                    .where(AgentConfig.status == AgentConfigStatus.ACTIVE)
                    .order_by(AgentConfig.version.desc())
                    .limit(1)
                )
            ) or {}
            if config is None:
                config = ReminderConfig(policies.get("reminders"))
            if today is None:
                today = local_today(tz_name)
        try:
            channel = await resolve_whatsapp_channel(
                session,
                role=CHANNEL_ROLE_NOTIFICATIONS,
                provider="meta",
                purpose="cobranza_reminder",
            )
        except ChannelResolutionError as exc:
            # Reported back to the admin who asked for the run, verbatim.
            # "No channel" and "you have two numbers and neither is the
            # notifications line" need different fixes, so they must not
            # collapse into the same status.
            log.warning(
                "cobranza_reminder.channel_unresolved",
                tenant_id=str(tenant_id),
                reason=exc.reason,
                detail=str(exc),
            )
            return {
                "status": "no_channel" if exc.reason == "whatsapp_not_connected" else exc.reason,
                "queued": 0,
                "deferred": 0,
                "recipients": [],
                "detail": str(exc),
            }
        log.info(
            "cobranza_reminder.channel_resolved",
            tenant_id=str(tenant_id),
            source=source,
            today=today.isoformat(),
            **describe_channel(channel),
        )
        approved = await _approved_templates(session)
    if not approved:
        return {
            "status": "templates_not_approved",
            "queued": 0,
            "deferred": 0,
            "recipients": [],
        }

    accounts = await _scan_accounts(client, tenant_id=tenant_id)
    plans = _plan_reminders(accounts, today=today, approved=approved, config=config)
    deferred = max(0, len(plans) - config.max_per_run)
    if deferred:
        # Never truncate in silence: a cap that hides what it dropped reads
        # exactly like "there was nothing else to send".
        log.warning(
            "cobranza_reminder.run_cap_reached",
            tenant_id=str(tenant_id),
            cap=config.max_per_run,
            eligible=len(plans),
            deferred=deferred,
        )
        plans = plans[: config.max_per_run]

    recipients: list[dict[str, Any]] = []
    for raw, stage, template_name, due in plans:
        async with sm() as session, tenant_scoped_session(session, tenant_id):
            queued = await _queue_reminder(
                session,
                tenant_id=tenant_id,
                channel=channel,
                account=raw,
                stage=stage,
                template_name=template_name,
                due=due,
                business_name=tenant_name,
            )
            if queued is not None:
                await session.commit()
                recipients.append(queued)
    if recipients:
        log.info(
            "cobranza_reminder.queued",
            tenant_id=str(tenant_id),
            source=source,
            reminders=len(recipients),
        )
    return {
        "status": "ok" if recipients else "no_due_accounts",
        "queued": len(recipients),
        "deferred": deferred,
        "recipients": recipients,
    }


async def _approved_templates(session: AsyncSession) -> set[str]:
    """Names of our reminder templates that Meta reports as APPROVED."""
    from nexus_api.services.whatsapp_templates import fetch_templates

    try:
        templates, _waba = await fetch_templates(session)
    except Exception as exc:  # connector/credentials hiccup — skip this tick
        log.warning("cobranza_reminder_cron.templates_unavailable", error=str(exc))
        return set()
    wanted = {TEMPLATE_PROXIMO, TEMPLATE_VENCIDO}
    return {
        t.name
        for t in templates
        if t.name in wanted
        and (t.status or "").upper() == "APPROVED"
        and (t.language or "").lower().startswith(LANGUAGE)
    }


async def _scan_accounts(
    client: Any, *, tenant_id: uuid.UUID | None = None
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    page = 1
    last_page = 1
    while page <= MAX_PAGES:
        raw, meta = await client.list_cuentas(page=page)
        out.extend(r for r in raw if isinstance(r, dict))
        last_page = int(meta.get("last_page") or page)
        if page >= last_page:
            break
        page += 1
    if last_page > MAX_PAGES:
        # The portfolio outgrew the scan. Silently reminding only the first
        # N pages would look identical to "everyone else is up to date".
        log.warning(
            "cobranza_reminder.page_cap_reached",
            tenant_id=str(tenant_id) if tenant_id else None,
            scanned_pages=MAX_PAGES,
            last_page=last_page,
        )
    return out


def _parse_due(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _reminder_for(
    account: dict[str, Any],
    *,
    today: date,
    approved: set[str],
    config: ReminderConfig | None = None,
) -> tuple[str, str, date] | None:
    """Return (stage, template_name, due_date) when this account is due for a
    reminder today, else None."""
    config = config or ReminderConfig({})
    if str(account.get("status") or "").upper() == "CANCELLED":
        return None
    total = float(account.get("total_amount") or 0)
    paid = float(account.get("paid_amount") or 0)
    if round(total - paid, 2) <= 0:
        return None  # nothing owed
    if not str(account.get("client_phone") or "").strip():
        return None  # no phone on file — can't reach them
    due = _parse_due(account.get("due_date"))
    if due is None:
        return None
    delta = (due - today).days
    # Age cap: a debt this old is a conversation for a human, not a
    # template fired by a cron the morning someone switched it on.
    if delta < 0 and -delta > config.max_overdue_days:
        return None
    for stage, template_name, lo, hi in _STAGES:
        if lo is not None and delta < lo:
            continue
        if hi is not None and delta > hi:
            continue
        if template_name in approved:
            return stage, template_name, due
        return None
    return None


def _plan_reminders(
    accounts: list[dict[str, Any]],
    *,
    today: date,
    approved: set[str],
    config: ReminderConfig,
) -> list[tuple[dict[str, Any], str, str, date]]:
    """Every account due for a reminder, most urgent first.

    Ordering matters because ``max_per_run`` truncates this list: "vence
    hoy" must not be dropped in favour of a debt that has been overdue for
    three weeks.
    """
    priority = {stage: i for i, (stage, _t, _lo, _hi) in enumerate(_STAGES)}
    plans: list[tuple[dict[str, Any], str, str, date]] = []
    for raw in accounts:
        plan = _reminder_for(raw, today=today, approved=approved, config=config)
        if plan is None:
            continue
        stage, template_name, due = plan
        plans.append((raw, stage, template_name, due))
    # Within a stage, the closest due date first.
    plans.sort(key=lambda p: (priority.get(p[1], 99), abs((p[3] - today).days)))
    return plans


def _fmt_amount(value: float) -> str:
    """Spanish formatting: 1668.5 -> ``$1.668,50`` (dot thousands, comma cents)."""
    whole, _, cents = f"{value:.2f}".partition(".")
    grouped = f"{int(whole):,}".replace(",", ".")
    return f"${grouped},{cents}"


async def _queue_reminder(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    channel: Channel,
    account: dict[str, Any],
    stage: str,
    template_name: str,
    due: date,
    business_name: str,
) -> dict[str, Any] | None:
    """Queue one reminder. Returns a summary dict, or None when skipped
    (no phone / opt-out / already sent)."""
    from nexus_channels.whatsapp_meta.phone import to_e164

    from nexus_worker.persistence.messages import (
        upsert_conversation_for_customer,
        upsert_customer,
    )

    account_id = str(account.get("id") or "")
    e164 = to_e164(str(account.get("client_phone") or ""))
    if not e164:
        return None
    # Meta's ``from`` format — must match what the inbound webhook stores or
    # customers/opt-outs fork per format.
    wa_identifier = e164.removeprefix("+")

    # The due date is part of the key on purpose. Keying on (account, stage)
    # alone meant an account that had already been chased was silenced
    # forever — even after the admin added a new charge with a new due date,
    # which is exactly what the anti-duplicate rule in the prompt tells them
    # to do instead of opening a second account.
    already = await session.scalar(
        sa.select(Message.id)
        .where(
            Message.tenant_id == tenant_id,
            Message.template_payload["cobranza_account"].astext == account_id,
            Message.template_payload["cobranza_stage"].astext == stage,
            Message.template_payload["cobranza_due"].astext == due.isoformat(),
        )
        .limit(1)
    )
    if already is not None:
        return None

    # Opt-out is checked across EVERY channel of the tenant, not just the one
    # we are about to send from. The table is keyed per channel because that
    # is where the STOP arrived, but a debtor who said BAJA means "stop
    # chasing me", not "stop chasing me from this number". Once a business
    # runs two lines, the per-channel check would let a reminder through on
    # the second one — a compliance failure in a collections vertical, and
    # one nobody would notice until a debtor complained.
    #
    # RLS scopes the query to the tenant, so this is exactly "any active
    # opt-out this business holds for this phone".
    opted_out = await session.scalar(
        sa.select(WhatsAppOptOut.id).where(
            WhatsAppOptOut.recipient_phone == wa_identifier,
            WhatsAppOptOut.opted_in_at.is_(None),
        )
    )
    if opted_out is not None:
        log.info(
            "cobranza_reminder.skipped_opt_out",
            tenant_id=str(tenant_id),
            channel_id=str(channel.id),
            account=account_id,
            stage=stage,
        )
        return None

    total = float(account.get("total_amount") or 0)
    paid = float(account.get("paid_amount") or 0)
    variables = {
        "cliente": str(account.get("client_name") or "").strip() or "cliente",
        "negocio": business_name,
        "monto": _fmt_amount(round(total - paid, 2)),
        "fecha": due.strftime("%d/%m/%Y"),
    }

    customer = await upsert_customer(session, identifier=wa_identifier)
    conversation = await upsert_conversation_for_customer(
        session, channel_id=channel.id, customer_id=customer.id
    )
    session.add(
        Message(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            direction=MessageDirection.OUTBOUND,
            status=MessageStatus.PENDING,
            content=f"[template:{template_name}]",
            tool_calls=[],
            actor_kind="system",
            template_payload={
                "name": template_name,
                "language": LANGUAGE,
                "params": {"body": variables},
                # Idempotency markers (ignored by the dispatcher).
                "cobranza_account": account_id,
                "cobranza_stage": stage,
                "cobranza_due": due.isoformat(),
            },
        )
    )
    return {
        "cliente": variables["cliente"],
        "stage": stage,
        "monto": variables["monto"],
        "fecha": variables["fecha"],
    }
