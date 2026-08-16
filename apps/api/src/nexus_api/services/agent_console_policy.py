"""``agent_configs.policies["console"]`` — the structured agent settings a
partner edits in the console (PLAN-CONSOLE-V1 CP-11 + CP-31).

Why a sub-object and not top-level keys: ``policies`` is a loose JSONB
that already carries runtime knobs owned by the platform
(``admin_access.*``, ``llm.respond_model``, ``agent.name``). Everything
the partner can touch lives under one namespaced, *versioned* object so
the runtime can validate it strictly and the platform keys stay out of
reach of the console. ``schema_version`` lets us migrate the shape later
without guessing.

The module is shared by the API (validate + persist) and the worker
(``render_operating_policy`` → system-prompt block, ``turn_cap_reached``
→ forced escalation). It has no FastAPI / SQLAlchemy imports on purpose.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

POLICY_KEY = "console"
SCHEMA_VERSION = 1

Weekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
WEEKDAYS: tuple[Weekday, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
Tone = Literal["formal", "cercano", "neutro"]
EscalationTrigger = Literal["user_asks_human", "angry", "out_of_scope", "after_n_turns"]

_TIME_RE = r"^([01]\d|2[0-3]):[0-5]\d$"
_DEFAULT_TRIGGERS: tuple[EscalationTrigger, ...] = ("user_asks_human", "angry", "out_of_scope")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IdentityPolicy(_Strict):
    name: str = Field(default="", max_length=120)
    persona: str = Field(default="", max_length=2000)


class TonePolicy(_Strict):
    style: Tone = "cercano"
    guidance: str = Field(default="", max_length=2000)


class ScheduleSlot(_Strict):
    day: Weekday
    open: str = Field(pattern=_TIME_RE, description="HH:MM, 24h, local to timezone")
    close: str = Field(pattern=_TIME_RE)

    @model_validator(mode="after")
    def _open_before_close(self) -> ScheduleSlot:
        if self.open >= self.close:
            raise ValueError(f"{self.day}: open ({self.open}) must be before close ({self.close})")
        return self


class SchedulePolicy(_Strict):
    timezone: str = Field(default="UTC", max_length=64)
    weekly: list[ScheduleSlot] = Field(default_factory=list, max_length=21)
    closed_message: str = Field(default="", max_length=1000)

    @field_validator("timezone")
    @classmethod
    def _tz_exists(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown timezone: {v!r}") from exc
        return v


class LanguagesPolicy(_Strict):
    primary: str = Field(default="es", min_length=2, max_length=8)
    allowed: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _primary_in_allowed(self) -> LanguagesPolicy:
        langs = [x.lower() for x in self.allowed]
        if self.primary.lower() not in langs:
            langs.insert(0, self.primary.lower())
        self.allowed = list(dict.fromkeys(langs))
        return self


class EscalationPolicy(_Strict):
    enabled: bool = True
    triggers: list[EscalationTrigger] = Field(default_factory=lambda: list(_DEFAULT_TRIGGERS))
    after_n_turns: int | None = Field(default=None, ge=1, le=100)
    handoff_message: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def _turns_consistent(self) -> EscalationPolicy:
        self.triggers = list(dict.fromkeys(self.triggers))
        if "after_n_turns" in self.triggers and self.after_n_turns is None:
            raise ValueError("after_n_turns trigger requires after_n_turns to be set")
        return self


class AiDisclosurePolicy(_Strict):
    """AI Act art. 50 — the customer must be told they talk to an AI.

    ``enabled`` defaults to **true**; the console records WHO decided
    (``decided_by``/``decided_at``) so a version published with the
    disclosure off is an explicit, attributable choice. A version whose
    policies carry no decision at all cannot be published from the
    console (409, see ``api/console/agents.py``).
    """

    enabled: bool = True
    disclosure_message: str = Field(default="", max_length=500)
    decided_by: str | None = Field(default=None, max_length=255)
    decided_at: datetime | None = None


class ConsolePolicy(_Strict):
    schema_version: int = Field(default=SCHEMA_VERSION, ge=1, le=SCHEMA_VERSION)
    identity: IdentityPolicy = Field(default_factory=IdentityPolicy)
    tone: TonePolicy = Field(default_factory=TonePolicy)
    objective: str = Field(default="", max_length=4000)
    schedule: SchedulePolicy = Field(default_factory=SchedulePolicy)
    languages: LanguagesPolicy = Field(default_factory=LanguagesPolicy)
    escalation: EscalationPolicy = Field(default_factory=EscalationPolicy)
    ai_disclosure: AiDisclosurePolicy = Field(default_factory=AiDisclosurePolicy)


# ── persistence helpers ────────────────────────────────────────────────


def read_console_policy(policies: dict[str, Any] | None) -> ConsolePolicy | None:
    """Parse ``policies["console"]``; ``None`` when absent. Raises
    ``pydantic.ValidationError`` on a malformed object (a platform bug,
    never a partner input error — the API validates on write)."""
    if not policies:
        return None
    raw = policies.get(POLICY_KEY)
    if not isinstance(raw, dict):
        return None
    return ConsolePolicy.model_validate(raw)


def has_disclosure_decision(policies: dict[str, Any] | None) -> bool:
    """CP-31 hard rule input: does this version carry an explicit
    ``ai_disclosure`` object (any ``enabled`` value)?"""
    if not policies:
        return False
    console = policies.get(POLICY_KEY)
    if not isinstance(console, dict):
        return False
    disclosure = console.get("ai_disclosure")
    return isinstance(disclosure, dict) and "enabled" in disclosure


def with_disclosure_default(policies: dict[str, Any], *, actor: str) -> dict[str, Any]:
    """Return a copy of ``policies`` where ``console.ai_disclosure`` exists.
    Staging from the console without a decision → ``enabled=true``,
    attributed to the staging actor. Never overwrites an existing decision."""
    out = dict(policies or {})
    if has_disclosure_decision(out):
        return out
    console = dict(out.get(POLICY_KEY) or {}) if isinstance(out.get(POLICY_KEY), dict) else {}
    console["ai_disclosure"] = AiDisclosurePolicy(
        enabled=True, decided_by=actor, decided_at=datetime.now(UTC)
    ).model_dump(mode="json")
    console.setdefault("schema_version", SCHEMA_VERSION)
    out[POLICY_KEY] = console
    return out


def merge_console_policy(
    policies: dict[str, Any], policy: ConsolePolicy, *, actor: str
) -> dict[str, Any]:
    """Return a copy of ``policies`` with ``console`` replaced by ``policy``,
    stamping the disclosure decision with ``actor`` when the caller did
    not attribute it. Platform keys outside ``console`` are untouched."""
    out = dict(policies or {})
    disclosure = policy.ai_disclosure
    if disclosure.decided_by is None or disclosure.decided_at is None:
        disclosure = disclosure.model_copy(
            update={"decided_by": actor, "decided_at": datetime.now(UTC)}
        )
        policy = policy.model_copy(update={"ai_disclosure": disclosure})
    out[POLICY_KEY] = policy.model_dump(mode="json")
    return out


# ── runtime rendering ──────────────────────────────────────────────────

_DAY_LABEL = {
    "mon": "Monday",
    "tue": "Tuesday",
    "wed": "Wednesday",
    "thu": "Thursday",
    "fri": "Friday",
    "sat": "Saturday",
    "sun": "Sunday",
}
_TONE_LABEL = {
    "formal": "formal (usted, precise, no slang)",
    "cercano": "warm and close (tú, friendly, concise)",
    "neutro": "neutral and professional",
}
_TRIGGER_LABEL = {
    "user_asks_human": "the customer asks for a human",
    "angry": "the customer is angry or distressed",
    "out_of_scope": "the request is out of scope",
    "after_n_turns": "the conversation exceeds the turn limit",
}


def _now_in(tz: str, now: datetime | None) -> datetime:
    base = now or datetime.now(UTC)
    try:
        return base.astimezone(ZoneInfo(tz))
    except (ZoneInfoNotFoundError, ValueError):
        return base.astimezone(UTC)


def is_open_now(schedule: SchedulePolicy, *, now: datetime | None = None) -> bool | None:
    """``True``/``False`` against the weekly schedule; ``None`` when no
    schedule is configured (always open)."""
    if not schedule.weekly:
        return None
    local = _now_in(schedule.timezone, now)
    day = WEEKDAYS[local.weekday()]
    hhmm = local.strftime("%H:%M")
    return any(s.day == day and s.open <= hhmm < s.close for s in schedule.weekly)


def render_operating_policy(policy: ConsolePolicy, *, now: datetime | None = None) -> str:
    """The "Operating policy" system-prompt block the worker injects.

    Deterministic, compact, English (the model follows it, the customer
    never sees it). Includes the *current* open/closed state so the
    model does not have to compute timezones itself.
    """
    lines: list[str] = ["Operating policy (set by the business — follow it):"]
    if policy.identity.name:
        lines.append(f"- You are {policy.identity.name}.")
    if policy.identity.persona:
        lines.append(f"- Persona: {policy.identity.persona}")
    lines.append(f"- Tone: {_TONE_LABEL[policy.tone.style]}.")
    if policy.tone.guidance:
        lines.append(f"  Tone guidance: {policy.tone.guidance}")
    if policy.objective:
        lines.append(f"- Objective: {policy.objective}")

    langs = policy.languages
    lines.append(
        f"- Languages: reply in {langs.primary} by default; allowed: {', '.join(langs.allowed)}. "
        "If the customer writes in an allowed language, answer in it; otherwise use the default."
    )

    sched = policy.schedule
    if sched.weekly:
        by_day: dict[str, list[str]] = {}
        for slot in sched.weekly:
            by_day.setdefault(slot.day, []).append(f"{slot.open}-{slot.close}")
        parts = [f"{_DAY_LABEL[d]} {', '.join(by_day[d])}" for d in WEEKDAYS if d in by_day]
        lines.append(f"- Business hours ({sched.timezone}): " + "; ".join(parts) + ".")
        local = _now_in(sched.timezone, now)
        state = "OPEN" if is_open_now(sched, now=now) else "CLOSED"
        lines.append(
            f"  Right now it is {local.strftime('%A %H:%M')} local time — the business is {state}."
        )
        if sched.closed_message:
            lines.append(f'  When closed, say: "{sched.closed_message}"')
        else:
            lines.append(
                "  When closed, say so, give the next opening time and offer to take a message."
            )

    esc = policy.escalation
    if esc.enabled:
        triggers = [_TRIGGER_LABEL[t] for t in esc.triggers]
        if esc.after_n_turns is not None:
            triggers = [
                t.replace("the turn limit", f"{esc.after_n_turns} turns") if "turn" in t else t
                for t in triggers
            ]
        lines.append("- Escalate to a human when: " + "; ".join(triggers) + ".")
        if esc.handoff_message:
            lines.append(f'  Handoff message: "{esc.handoff_message}"')
    else:
        lines.append("- Escalation to a human is disabled: resolve within scope or say you cannot.")

    disc = policy.ai_disclosure
    if disc.enabled:
        msg = disc.disclosure_message or "you are an AI assistant, not a person"
        lines.append(
            f"- AI disclosure (mandatory): make clear at the start and whenever asked that {msg}. "
            "Never claim to be human."
        )
    return "\n".join(lines)


def turn_cap_reached(policy: ConsolePolicy | None, *, user_turns: int) -> bool:
    """``True`` when the escalation policy says "hand off after N turns"
    and the conversation already has ``user_turns`` customer messages
    before this one (so the (N)th customer message triggers it)."""
    if policy is None or not policy.escalation.enabled:
        return False
    if "after_n_turns" not in policy.escalation.triggers or policy.escalation.after_n_turns is None:
        return False
    return user_turns + 1 >= policy.escalation.after_n_turns


__all__ = [
    "POLICY_KEY",
    "SCHEMA_VERSION",
    "WEEKDAYS",
    "AiDisclosurePolicy",
    "ConsolePolicy",
    "EscalationPolicy",
    "IdentityPolicy",
    "LanguagesPolicy",
    "SchedulePolicy",
    "ScheduleSlot",
    "TonePolicy",
    "has_disclosure_decision",
    "is_open_now",
    "merge_console_policy",
    "read_console_policy",
    "render_operating_policy",
    "turn_cap_reached",
    "with_disclosure_default",
]
