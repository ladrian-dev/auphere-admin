"""Spec 025: who reviews payments — ``policies.payment_review.reviewers``.

The list travels with the agent version like the rest of Ajustes del agente
(draft, publish, revert). Phones are normalised and filtered with the same
helpers as «A quién responde» (spec 024), so a reviewer saved here matches a
sender exactly like an allowed number does. An empty list means no payment
review: the agent hands over to a person, as before spec 025.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nexus_channels.whatsapp_meta.phone import to_e164

from nexus_api.core.admin_gate import usable_admin_phones

POLICY_KEY = "payment_review"
MAX_REVIEWERS = 10


class ReviewerError(Exception):
    code = "payment_reviewer_error"


class ReviewerInvalidPhone(ReviewerError):
    code = "payment_reviewer_invalid_phone"

    def __init__(self, phone: str) -> None:
        super().__init__(f"invalid phone: {phone!r}")
        self.phone = phone


class TooManyReviewers(ReviewerError):
    code = "payment_reviewers_too_many"

    def __init__(self) -> None:
        super().__init__(f"at most {MAX_REVIEWERS} reviewers")


@dataclass(frozen=True)
class Reviewer:
    phone: str
    name: str | None = None


def reviewers_of(policies: dict[str, Any] | None) -> list[Reviewer]:
    """The reviewers as stored. Tolerant: anything malformed reads as none."""
    block = (policies or {}).get(POLICY_KEY)
    if not isinstance(block, dict):
        return []
    out: list[Reviewer] = []
    for entry in block.get("reviewers") or []:
        if isinstance(entry, dict) and entry.get("phone"):
            out.append(Reviewer(phone=str(entry["phone"]), name=entry.get("name") or None))
    return out


def apply_reviewers(policies: dict[str, Any] | None, reviewers: list[Reviewer]) -> dict[str, Any]:
    """Return a copy of ``policies`` with the reviewer list rewritten."""
    if len(reviewers) > MAX_REVIEWERS:
        raise TooManyReviewers()
    stored: list[dict[str, Any]] = []
    seen: set[str] = set()
    for reviewer in reviewers:
        raw = (reviewer.phone or "").strip()
        e164 = to_e164(raw)
        if not e164 or not usable_admin_phones([e164]):
            raise ReviewerInvalidPhone(raw)
        if e164 in seen:
            continue
        seen.add(e164)
        stored.append({"phone": e164, "name": (reviewer.name or "").strip() or None})
    out = dict(policies or {})
    out[POLICY_KEY] = {"reviewers": stored}
    return out


__all__ = [
    "MAX_REVIEWERS",
    "POLICY_KEY",
    "Reviewer",
    "ReviewerError",
    "ReviewerInvalidPhone",
    "TooManyReviewers",
    "apply_reviewers",
    "reviewers_of",
]
