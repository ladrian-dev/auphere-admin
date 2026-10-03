"""Spec 024: «A quién responde» — the admin-only whitelist as the console
sees it.

The runtime already has the mechanism: ``policies.admin_access`` with
``admin_only`` and ``admin_phones`` (``core/admin_gate.py``). The partner API
writes it, the onboarding wizard fills it for admin-only templates, and the
worker enforces it. What was missing is a screen. This module is the one
translation between that runtime key and the ``audience`` the console
reads and writes, so the settings endpoint, the client list and the tests
all see the same thing.

Rules, pinned by ``tests/unit/test_agent_audience.py``:

- ``admin_access`` stays the single source of truth; nothing is copied.
- Phones are normalised with the same ``to_e164`` the partner API uses and
  filtered with the same ``usable_admin_phones`` the gate uses, so a number
  saved from the console and one saved by the API behave identically.
- ``everyone`` turns ``admin_only`` off but keeps the numbers: going back
  to the list does not force the partner to retype it.
- An admin-only template (cobranza) is *locked*: the list can be edited,
  the mode cannot be opened to everyone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from nexus_channels.whatsapp_meta.phone import to_e164

from nexus_api.core.admin_gate import usable_admin_phones
from nexus_api.services.templating.seed_templates import load_seed_template

AudienceMode = Literal["everyone", "list"]


class AudienceError(Exception):
    """Base class: the console shows these as validation errors."""

    code = "audience_error"


class AudienceInvalidPhone(AudienceError):
    code = "audience_invalid_phone"

    def __init__(self, phone: str) -> None:
        super().__init__(f"invalid phone: {phone!r}")
        self.phone = phone


class AudienceEmpty(AudienceError):
    code = "audience_empty"

    def __init__(self) -> None:
        super().__init__("a list audience needs at least one usable phone")


class AudienceLocked(AudienceError):
    code = "audience_locked"

    def __init__(self) -> None:
        super().__init__("this agent's template is admin-only; the mode cannot be opened")


@dataclass(frozen=True)
class AudienceNumber:
    phone: str
    name: str | None = None


@dataclass(frozen=True)
class Audience:
    mode: AudienceMode
    numbers: list[AudienceNumber] = field(default_factory=list)
    locked: bool = False


def is_locked_template(seed_template_ref: str | None) -> bool:
    """True when the template the agent was seeded from declares
    ``admin_access.admin_only``. A template that does not load is not
    locked: better an editable mode than a screen that refuses for a
    reason nobody can see."""
    if not seed_template_ref:
        return False
    for name in (seed_template_ref, f"{seed_template_ref}_v1"):
        try:
            template = load_seed_template(name)
        except Exception:
            continue
        access = template.policies_default.get("admin_access")
        return bool(isinstance(access, dict) and access.get("admin_only"))
    return False


def _access_of(policies: dict[str, Any] | None) -> dict[str, Any]:
    access = (policies or {}).get("admin_access")
    return dict(access) if isinstance(access, dict) else {}


def _meta_by_phone(access: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for entry in access.get("admins") or []:
        if isinstance(entry, dict) and entry.get("phone"):
            out[str(entry["phone"])] = entry
    return out


def audience_of(policies: dict[str, Any] | None, *, locked: bool = False) -> Audience:
    """Read ``admin_access`` as the console shows it."""
    access = _access_of(policies)
    meta = _meta_by_phone(access)
    numbers = [
        AudienceNumber(phone=str(p), name=(meta.get(str(p)) or {}).get("name") or None)
        for p in (access.get("admin_phones") or [])
    ]
    mode: AudienceMode = "list" if access.get("admin_only") else "everyone"
    return Audience(mode=mode, numbers=numbers, locked=locked)


def count_of(policies: dict[str, Any] | None) -> tuple[AudienceMode, int]:
    """What the client list needs: the mode and how many numbers can
    actually match a sender."""
    access = _access_of(policies)
    if not access.get("admin_only"):
        return "everyone", 0
    return "list", len(usable_admin_phones(list(access.get("admin_phones") or [])))


def apply_audience(
    policies: dict[str, Any] | None,
    *,
    mode: AudienceMode,
    numbers: list[AudienceNumber],
    locked: bool = False,
) -> dict[str, Any]:
    """Return a copy of ``policies`` with ``admin_access`` rewritten.

    Raises ``AudienceLocked`` when opening a locked agent,
    ``AudienceInvalidPhone`` for a phone that cannot match a sender, and
    ``AudienceEmpty`` for a list mode without any usable phone.
    """
    if locked and mode == "everyone":
        raise AudienceLocked()

    access = _access_of(policies)
    previous = _meta_by_phone(access)

    phones: list[str] = []
    admins: list[dict[str, Any]] = []
    for number in numbers:
        raw = (number.phone or "").strip()
        e164 = to_e164(raw)
        if not e164 or not usable_admin_phones([e164]):
            raise AudienceInvalidPhone(raw)
        if e164 in phones:
            continue
        phones.append(e164)
        role = str((previous.get(e164) or {}).get("role") or "full").lower()
        admins.append(
            {
                "phone": e164,
                "name": (number.name or "").strip() or None,
                "role": "readonly" if role == "readonly" else "full",
            }
        )

    if mode == "list" and not phones:
        raise AudienceEmpty()

    out = dict(policies or {})
    access["admin_only"] = mode == "list"
    if mode == "list" or phones:
        access["admin_phones"] = phones
        access["admins"] = admins
    out["admin_access"] = access
    return out


__all__ = [
    "Audience",
    "AudienceEmpty",
    "AudienceError",
    "AudienceInvalidPhone",
    "AudienceLocked",
    "AudienceMode",
    "AudienceNumber",
    "apply_audience",
    "audience_of",
    "count_of",
    "is_locked_template",
]
