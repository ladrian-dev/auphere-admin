"""El resultado de un envío, el mismo para APNs y FCM."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Outcome = Literal["sent", "failed", "retry", "unregistered"]


@dataclass(frozen=True)
class SendResult:
    outcome: Outcome
    provider_message_id: str | None = None
    error_code: str | None = None


NOT_CONFIGURED = SendResult(outcome="failed", error_code="provider_not_configured")
