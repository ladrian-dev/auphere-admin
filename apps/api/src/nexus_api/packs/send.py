"""Idempotent send on (thread_id, step_id, run_id). Claim BEFORE wait_reply."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.db.models.workflow import WorkflowSendReceipt


async def claim_send(
    session: AsyncSession,
    *,
    partner_id: uuid.UUID,
    thread_id: str,
    step_id: str,
    run_id: str,
) -> bool:
    """Insert the receipt. Return True if this call owns the send.

    The row is committed by the caller **before** ``wait_reply`` / interrupt.
    A replay of the same key returns False and must not hit Meta.
    """
    await apply_partner_to_session(session, partner_id)
    stmt = (
        pg_insert(WorkflowSendReceipt)
        .values(
            partner_id=partner_id,
            thread_id=thread_id,
            step_id=step_id,
            run_id=run_id,
        )
        .on_conflict_do_nothing(constraint="uq_workflow_send_receipts_key")
        .returning(WorkflowSendReceipt.id)
    )
    claimed = (await session.execute(stmt)).scalar_one_or_none()
    return claimed is not None


async def send_if_new(
    session: AsyncSession,
    *,
    partner_id: uuid.UUID,
    thread_id: str,
    step_id: str,
    run_id: str,
    sender: Any,
) -> bool:
    """Claim first, then send. Replay skips ``sender``."""
    owned = await claim_send(
        session,
        partner_id=partner_id,
        thread_id=thread_id,
        step_id=step_id,
        run_id=run_id,
    )
    if not owned:
        return False
    result = sender()
    if hasattr(result, "__await__"):
        await result
    return True
