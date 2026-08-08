"""WhatsApp provider 5xx burst detector — Redis-backed (WP-08).

When the outbound dispatcher catches >=5 ``MetaAPIError`` with status
500-599 within the window for a single tenant, this tracker emits exactly
one ``channel.whatsapp_5xx_burst`` audit row. The operator alerter consumes
the audit and notifies the operator via WhatsApp template
``alert_whatsapp_burst_v1``.

WP-08 moved the state out of the process: counters are ``INCR`` + ``EXPIRE``
on ``nexus:burst:{tenant}:{window}`` and the cooldown is a ``SET NX EX``
marker, so N egress replicas see one shared count and a burst spread across
replicas still trips exactly one audit. The sliding window became a fixed
bucket (``now // window_seconds``) — strikes split across a bucket boundary
can take up to 2x the window to trip, which is an acceptable trade for
multi-replica correctness.

Failure policy: any Redis error suppresses the alert (log + False). The
tracker is an alarm, not a control path — it must never break a send.
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any

import structlog
from nexus_api.core.redis_client import get_redis
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import AuditLog

log = structlog.get_logger(__name__)

WINDOW_SECONDS = 120.0
THRESHOLD = 5
COOLDOWN_SECONDS = 300.0  # one audit per tenant per 5min after firing


class WhatsAppBurstTracker:
    """Redis-windowed detector shared by every egress replica.

    ``should_alert`` is async (Redis I/O). It counts the failure and
    returns True iff this call crossed the threshold outside the cooldown.
    """

    def __init__(
        self,
        *,
        window_seconds: float = WINDOW_SECONDS,
        threshold: int = THRESHOLD,
        cooldown_seconds: float = COOLDOWN_SECONDS,
        redis: Any | None = None,
    ) -> None:
        self._window = window_seconds
        self._threshold = threshold
        self._cooldown = cooldown_seconds
        self._redis = redis

    def _get_redis(self) -> Any:
        return self._redis if self._redis is not None else get_redis()

    def _is_relevant(self, status_code: int) -> bool:
        # 0 = transport error — provider-side or network trouble, treated
        # as 5xx-equivalent.
        return status_code == 0 or 500 <= status_code <= 599

    async def should_alert(self, tenant_id: uuid.UUID, status_code: int) -> bool:
        if not self._is_relevant(status_code):
            return False
        try:
            redis = self._get_redis()
            bucket = int(time.time() // self._window)
            count_key = f"nexus:burst:{tenant_id}:{bucket}"
            count = int(await redis.incr(count_key))
            # 2x window so a bucket straddling a boundary still counts.
            await redis.expire(count_key, int(self._window * 2))
            if count < self._threshold:
                return False
            cooldown_key = f"nexus:burst:cooldown:{tenant_id}"
            fresh = await redis.set(cooldown_key, "1", nx=True, ex=int(self._cooldown))
            if not fresh:
                return False
            # Reset the bucket so the next burst counts from zero instead of
            # re-tripping the moment the cooldown expires.
            await redis.delete(count_key)
            return True
        except Exception as exc:
            log.warning(
                "burst_tracker.redis_failed",
                tenant_id=str(tenant_id),
                error=str(exc),
            )
            return False

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
        if not await self.should_alert(tenant_id, status_code):
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
