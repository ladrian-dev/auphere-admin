"""Schemas of lane D (``home-usage``): the console home, usage (units,
projection, cap, series, alerts), audit vocabulary and receipts.

Same two rules as ``schemas.py`` (pinned by ``tests/isolation``): no
internal tenant ids — a partner speaks ``external_client_ref`` — and no
message bodies (C8). Usage is **units, never cost** (C9): the only thing
said about ``cost_usd`` is *how many rows have none* (``unpriced_records``),
which is an operational hint, not a price.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from .schemas import UsageReportOut

# ── home (CP-08) ───────────────────────────────────────────────────────


class HomeClientsOut(BaseModel):
    active: int
    total: int
    provisioning: int
    paused: int


class HomeConversationsOut(BaseModel):
    """Conversations started in the natural month (UTC), all clients."""

    count: int
    since: datetime
    until: datetime


class HomeUsageOut(BaseModel):
    """Channel messages of the natural month vs. the partner's cap (0087)."""

    units: float
    meter: str = "channel.message"
    cap: int | None
    percent: float | None
    projected_month_units: float
    basis_days: int


class IncidentClientOut(BaseModel):
    """A client with at least one incident. ``issues`` is a closed vocabulary:
    ``whatsapp_degraded`` (degraded OR disconnected) · ``no_active_agent``
    · ``failed_messages_24h`` · ``out_of_quota`` (spec 016: the channel gate
    is closed for this client)."""

    external_client_ref: str
    client_name: str | None
    issues: list[str]
    failed_messages_24h: int
    href: str


class HomeIncidentsOut(BaseModel):
    count: int
    refs: list[IncidentClientOut]


PendingKind = Literal["client_provisioning", "invitations_pending", "usage_alerts_unread"]


class PendingItemOut(BaseModel):
    kind: PendingKind
    external_client_ref: str | None = None
    client_name: str | None = None
    count: int = 1
    href: str


class HomePendingOut(BaseModel):
    count: int
    items: list[PendingItemOut]


# ── spec 026 · what the partner has to do today ───────────────────────

AttentionKind = Literal[
    "out_of_quota",
    "no_active_agent",
    "whatsapp_disconnected",
    "needs_reauth",
    "quality_red",
    "failed_messages",
    "template_rejected",
    "draft_unpublished",
    "provisioning",
]


class AttentionItemOut(BaseModel):
    """One problem of one client, with where it is fixed. ``severity`` 1 is
    the worst (the agent cannot answer at all)."""

    kind: AttentionKind
    severity: int
    external_client_ref: str
    client_name: str | None
    count: int | None = None
    href: str


class HomeAttentionOut(BaseModel):
    items: list[AttentionItemOut]
    #: Clients with nothing to fix — «todos atendiendo» when it equals total.
    clients_ok: int


class ReviewClientOut(BaseModel):
    external_client_ref: str
    client_name: str | None
    escalated: int
    payments: int
    unanswered: int
    href: str


class HomeToReviewOut(BaseModel):
    """What waits for a person, across the portfolio (7-day window)."""

    escalated: int
    payments: int
    unanswered: int
    clients: list[ReviewClientOut]


class TrendClientOut(BaseModel):
    """``external_client_ref`` is ``None`` for «el resto» (clients beyond
    the five with most activity)."""

    external_client_ref: str | None
    client_name: str | None
    series: list[int]


class HomeTrendOut(BaseModel):
    """Customer conversations per UTC day: the last 7 days against the 7
    before. ``previous`` is ``None`` when nothing happened then — no change
    is invented from zero."""

    days: list[date]
    series: list[int]
    current: int
    previous: int | None
    by_client: list[TrendClientOut]


class CreditRiskOut(BaseModel):
    external_client_ref: str
    client_name: str | None
    remaining: int
    days_left: float
    href: str


class HomeCreditOut(BaseModel):
    """Credit in units (never money). ``days_left`` is ``None`` when there
    was no spend in 7 days."""

    available: int | None
    spent_7d: int
    daily_average: float
    days_left: float | None
    at_risk: list[CreditRiskOut]


class PortfolioRowOut(BaseModel):
    external_client_ref: str
    client_name: str | None
    status: str
    conversations_7d: int
    series_7d: list[int]
    last_activity_at: datetime | None
    credit_cap: int | None
    credit_remaining: int | None
    attention: int
    href: str


class HomeOut(BaseModel):
    """One response. A block is ``null`` when the principal lacks the
    permission that guards it or when its query failed (partial error —
    the other blocks still render). The five original blocks stay for the
    Companion (``console.get_quota``); the page reads the spec 026 ones."""

    clients: HomeClientsOut | None
    conversations_period: HomeConversationsOut | None
    usage_units: HomeUsageOut | None
    agents_with_incidents: HomeIncidentsOut | None
    pending_actions: HomePendingOut | None
    attention: HomeAttentionOut | None = None
    to_review: HomeToReviewOut | None = None
    conversations_trend: HomeTrendOut | None = None
    credit: HomeCreditOut | None = None
    portfolio: list[PortfolioRowOut] | None = None
    errors: list[str] = Field(default_factory=list, description="Blocks that failed")
    generated_in_ms: int


# ── usage (CP-22 / CP-24) ──────────────────────────────────────────────


class UsageMonthOut(BaseModel):
    """Natural-month figures for the cap gauge and the projection."""

    since: datetime
    until: datetime
    units: float
    meter: str = "channel.message"
    cap: int | None
    percent: float | None
    projected_month_units: float
    basis_days: int
    days_in_month: int


class UsageReportV2Out(UsageReportOut):
    """Superset of the original report: same buckets and totals, plus the
    month block and the count of rows still without a price."""

    month: UsageMonthOut
    unpriced_records: int


class UsageSeriesPointOut(BaseModel):
    day: date
    by_meter: dict[str, float]


class UsageSeriesOut(BaseModel):
    since: datetime
    until: datetime
    source: str
    meters: list[str]
    points: list[UsageSeriesPointOut]


class UsageAlertsOut(BaseModel):
    cap_messages_month: int | None
    recipients: list[str]
    enabled: bool
    month_units: float
    percent: float | None


class UsageAlertsIn(BaseModel):
    cap_messages_month: int | None = Field(default=None, ge=0, le=1_000_000_000)
    recipients: list[EmailStr] = Field(default_factory=list, max_length=20)
    enabled: bool = True


# ── audit (CP-28) ──────────────────────────────────────────────────────


class AuditVocabularyEntryOut(BaseModel):
    action: str
    category: str
    severity: str
    summary: str


class AuditVocabularyOut(BaseModel):
    lang: str
    entries: list[AuditVocabularyEntryOut]
