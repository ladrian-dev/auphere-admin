"""Spec 005 · R7.5 — the twelve months run out, and it is written down.

This is the only place in the system where an automated job **lowers** a
balance, so it is worth being precise about why that does not contradict
ADR-037 D3.

D3 forbids an **external notice** from subtracting: a duplicated event read
backwards, a refund misinterpreted, a test event reaching production — any of
those becoming money that vanishes from someone's account. This is not that.
It is our own rule, on a date we set, applied by our own job, and **it leaves a
ledger entry**. The difference is who decides, not whether it goes down.

The entry's ``idempotency_key`` names the reason, which also makes the job
safe to run every day: the second attempt hits the unique constraint that has
guarded the ledger since migration 0094.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
import structlog

log = structlog.get_logger(__name__)

#: What the ledger entry is called. Greppable on purpose: the day someone asks
#: "where did this partner's credit go", this is the word they will search for.
LEDGER_REASON = "credit_expired"


def _key(partner_id: uuid.UUID, expires_at: datetime) -> str:
    """One entry per partner and expiry date.

    Including the date means a partner who cancels, comes back and cancels
    again years later expires twice — correctly — while the daily job never
    doubles a single expiry.
    """
    return f"{LEDGER_REASON}:{partner_id}:{expires_at.date().isoformat()}"


async def expire_due_credit(session: Any, *, now: datetime | None = None) -> list[dict[str, Any]]:
    """Zero the purchased buckets whose date has passed. Returns what expired.

    A live account is never touched: its ``purchased_expires_at`` is ``NULL``,
    and ``NULL`` does not satisfy the comparison. That is the whole point of
    writing the invariant as an absence — this query cannot get a live account
    wrong even if someone edits it carelessly.
    """
    stamp = now or datetime.now(UTC)

    due = (
        (
            await session.execute(
                sa.text(
                    "SELECT partner_id, purchased_remaining, purchased_expires_at "
                    "  FROM partner_wallets "
                    " WHERE purchased_expires_at IS NOT NULL "
                    "   AND purchased_expires_at <= :now "
                    "   AND purchased_remaining > 0 "
                    " FOR UPDATE"
                ),
                {"now": stamp},
            )
        )
        .mappings()
        .all()
    )

    expired: list[dict[str, Any]] = []
    for row in due:
        partner_id = row["partner_id"]
        qty = int(row["purchased_remaining"])
        key = _key(partner_id, row["purchased_expires_at"])

        # The entry goes in FIRST. If it clashes, this expiry is already
        # written and the balance was already zeroed: nothing else to do.
        written = await session.execute(
            sa.text(
                "INSERT INTO usage_ledger (id, partner_id, qty, bucket, idempotency_key) "
                "VALUES (:i, :p, :q, 'purchased', :k) "
                "ON CONFLICT (idempotency_key) DO NOTHING "
                "RETURNING id"
            ),
            {"i": str(uuid.uuid4()), "p": str(partner_id), "q": qty, "k": key},
        )
        if written.first() is None:
            continue

        await session.execute(
            sa.text("UPDATE partner_wallets SET purchased_remaining = 0 WHERE partner_id = :p"),
            {"p": str(partner_id)},
        )
        expired.append({"partner_id": partner_id, "qty": qty})
        log.info("metering.credit_expired", partner_id=str(partner_id), qty=qty)

    return expired


#: Daily. The expiry is a date, not an event, so there is nothing to react to
#: and nothing gained by looking more often. Idempotent by the ledger's unique
#: key, so a tick that repeats costs one query and writes nothing.
DEFAULT_TICK_SECONDS = 86_400.0


async def sweep_once(sm: Any) -> int:
    """One sweep. Returns how many partners expired, for the log and tests."""
    async with sm() as session:
        expired = await expire_due_credit(session)
        await session.commit()
    if expired:
        log.info("expire_credit_cron.swept", partners=len(expired))
    return len(expired)


async def run_expire_credit_cron(*, stop: Any, tick_seconds: float = DEFAULT_TICK_SECONDS) -> None:
    """Background task. Returns when ``stop`` is set."""
    import asyncio
    import contextlib

    from nexus_api.db.base import get_sessionmaker

    log.info("expire_credit_cron.start", tick_seconds=tick_seconds)
    sm = get_sessionmaker()
    while not stop.is_set():
        try:
            await sweep_once(sm)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Money that should have expired and did not is a smaller problem
            # than a scheduler that dies: the next tick catches up, because
            # the query looks at a date and not at what happened since.
            log.error("expire_credit_cron.tick_failed", error=str(exc))
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
    log.info("expire_credit_cron.stopped")
