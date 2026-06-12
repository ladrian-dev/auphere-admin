"""In-process WhatsApp provider 5xx burst detector.

When the outbound dispatcher catches >=5 ``MetaAPIError`` with status
500-599 within a 2-minute sliding window for a single tenant, this
tracker emits exactly one ``channel.whatsapp_5xx_burst`` audit row. The
operator alerter consumes the audit and notifies the operator via WhatsApp
template ``alert_whatsapp_burst_v1``.

Per-process state — block H runs a single worker; multi-replica is a
phase 2+ concern (a Redis-backed counter would replace this when we
scale out, same shape).
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import defaultdict, deque

import structlog
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import AuditLog

log = structlog.get_logger(__name__)

WINDOW_SECONDS = 120.0
THRESHOLD = 5
COOLDOWN_SECONDS = 300.0  # one audit per (tenant) per 5min after firing


class WhatsAppBurstTracker:
    """Thread-safe sliding-window detector. Uses ``deque`` per tenant.

    ``record_failure`` is called from the dispatcher's failure path with
    the tenant_id and HTTP status code (or 0 for transport errors which
    we treat as 5xx-equivalent — they signal a problem on the provider's side
    or the network between us). Returns True iff this call crossed the
    threshold and an audit was emitted.
    """

    def __init__(
        self,
        *,
        window_seconds: float = WINDOW_SECONDS,
        threshold: int = THRESHOLD,
        cooldown_seconds: float = COOLDOWN_SECONDS,
    ) -> None:
        self._window = window_seconds
        self._threshold = threshold
        self._cooldown = cooldown_seconds
        self._failures: dict[uuid.UUID, deque[float]] = defaultdict(deque)
        self._last_audit_at: dict[uuid.UUID, float] = {}
        self._lock = threading.Lock()

    def _is_relevant(self, status_code: int) -> bool:
        return status_code == 0 or 500 <= status_code <= 599

    def _trim(self, dq: deque[float], now: float) -> None:
        cutoff = now - self._window
        while dq and dq[0] < cutoff:
            dq.popleft()

    def should_alert(self, tenant_id: uuid.UUID, status_code: int) -> bool:
        if not self._is_relevant(status_code):
            return False
        now = time.monotonic()
        with self._lock:
            dq = self._failures[tenant_id]
            dq.append(now)
            self._trim(dq, now)
            if len(dq) < self._threshold:
                return False
            # Default to -inf so a never-alerted tenant always clears the
            # cooldown check. Using 0.0 was a latent bug: ``time.monotonic()``
            # references an arbitrary point (boot time on Linux/macOS), so on
            # a CI VM with uptime < cooldown_seconds, ``now - 0.0`` could be
            # smaller than the cooldown and falsely suppress the first audit.
            last = self._last_audit_at.get(tenant_id, float("-inf"))
            if now - last < self._cooldown:
                return False
            self._last_audit_at[tenant_id] = now
            dq.clear()
            return True

    async def record_failure_and_maybe_audit(
        self,
        tenant_id: uuid.UUID,
        status_code: int,
        *,
        error_message: str = "",
    ) -> bool:
        """Mark the failure and, if the threshold tripped, persist the
        audit row in its own short-lived tenant-scoped session so the
        outbound dispatcher's session stays clean."""
        if not self.should_alert(tenant_id, status_code):
            return False
        try:
            sm = get_sessionmaker()
            async with sm() as session, tenant_scoped_session(session, tenant_id):
                audit = AuditLog(
                    tenant_id=tenant_id,
                    actor="system:outbound_dispatcher",
                    action="channel.whatsapp_5xx_burst",
                    target=f"tenant:{tenant_id}",
                    before_json=None,
                    after_json={
                        "threshold": self._threshold,
                        "window_seconds": int(self._window),
                        "last_status_code": status_code,
                        "last_error": error_message[:500],
                    },
                )
                session.add(audit)
                await session.commit()
            log.warning(
                "outbound.dispatcher.whatsapp_5xx_burst",
                tenant_id=str(tenant_id),
                window_s=int(self._window),
            )
            return True
        except Exception as exc:
            log.error(
                "burst_tracker.audit_failed",
                tenant_id=str(tenant_id),
                error=str(exc),
            )
            return False


_default_tracker: WhatsAppBurstTracker | None = None
_tracker_lock = threading.Lock()


def get_default_tracker() -> WhatsAppBurstTracker:
    global _default_tracker
    with _tracker_lock:
        if _default_tracker is None:
            _default_tracker = WhatsAppBurstTracker()
        return _default_tracker


def reset_default_tracker() -> None:
    """Test helper."""
    global _default_tracker
    with _tracker_lock:
        _default_tracker = None
