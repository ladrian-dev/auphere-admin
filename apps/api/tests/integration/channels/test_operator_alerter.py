"""Operator alerter: writes operator_notifications + sends WhatsApp templates
in response to two specific audit_log actions."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.streams.operator_alerts import _process_pending

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AuditLog,
    OperatorNotification,
    OperatorNotificationStatus,
)

pytestmark = pytest.mark.asyncio


async def _seed_audit(
    *, tenant_info: dict[str, Any], action: str, after_json: dict | None = None
) -> uuid.UUID:
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_info["tenant_id"]):
        audit = AuditLog(
            tenant_id=tenant_info["tenant_id"],
            actor="system:test",
            action=action,
            target=f"tenant:{tenant_info['tenant_id']}",
            before_json=None,
            after_json=after_json or {},
        )
        session.add(audit)
        await session.flush()
        await session.refresh(audit)
        audit_id = audit.id
    return audit_id


async def _read_notifications_count(tenant_id: uuid.UUID, audit_log_id: uuid.UUID) -> int:
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        result = await session.execute(
            sa.select(sa.func.count())
            .select_from(OperatorNotification)
            .where(OperatorNotification.audit_log_id == audit_log_id)
        )
        return int(result.scalar_one())


async def _read_notification(tenant_id: uuid.UUID, audit_log_id: uuid.UUID) -> OperatorNotification:
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        result = await session.execute(
            sa.select(OperatorNotification).where(OperatorNotification.audit_log_id == audit_log_id)
        )
        return result.scalar_one()


async def test_alerter_sends_escalation_template_once(
    two_tenants_with_channels,
    fake_adapter,
):
    info = two_tenants_with_channels["a"]
    audit_id = await _seed_audit(
        tenant_info=info,
        action="conversation.escalated",
        after_json={"customer_id": str(info["customer_id"]), "reason": "queja formal"},
    )

    sm = get_sessionmaker()
    await _process_pending(sm, {"meta": fake_adapter})
    # Run a second time — it must NOT re-notify.
    await _process_pending(sm, {"meta": fake_adapter})

    assert len(fake_adapter.template_calls) == 1
    call = fake_adapter.template_calls[0]
    assert call["template_name"] == "alert_escalation_v1"
    assert call["from_phone"] == info["business_phone"]
    # owner_phone of tenant A — see two_tenants_with_channels fixture.
    assert call["recipient"] == "+56999990001"
    # Body params: [customer_label, reason]. Customer has identifier as fallback.
    assert call["params"]["body"][1] == "queja formal"

    notif = await _read_notification(info["tenant_id"], audit_id)
    assert notif.status is OperatorNotificationStatus.SENT
    assert notif.template_name == "alert_escalation_v1"
    assert notif.sent_at is not None


async def test_alerter_sends_needs_reauth_template(
    two_tenants_with_channels,
    fake_adapter,
):
    info = two_tenants_with_channels["a"]
    audit_id = await _seed_audit(
        tenant_info=info,
        action="integration.agendapro.needs_reauth",
        after_json={"checked_at": "2026-05-09T12:00:00+00:00", "notes": "login form returned"},
    )

    sm = get_sessionmaker()
    await _process_pending(sm, {"meta": fake_adapter})

    assert len(fake_adapter.template_calls) == 1
    assert fake_adapter.template_calls[0]["template_name"] == "alert_needs_reauth_v1"
    notif = await _read_notification(info["tenant_id"], audit_id)
    assert notif.status is OperatorNotificationStatus.SENT


async def test_alerter_isolation_two_tenants(
    two_tenants_with_channels,
    fake_adapter,
):
    info_a = two_tenants_with_channels["a"]
    info_b = two_tenants_with_channels["b"]
    audit_a = await _seed_audit(
        tenant_info=info_a,
        action="conversation.escalated",
        after_json={"customer_id": str(info_a["customer_id"]), "reason": "A reason"},
    )
    audit_b = await _seed_audit(
        tenant_info=info_b,
        action="conversation.escalated",
        after_json={"customer_id": str(info_b["customer_id"]), "reason": "B reason"},
    )

    sm = get_sessionmaker()
    await _process_pending(sm, {"meta": fake_adapter})

    assert len(fake_adapter.template_calls) == 2
    by_recipient = {c["recipient"]: c for c in fake_adapter.template_calls}
    # owner_phones distintos por tenant
    assert by_recipient["+56999990001"]["from_phone"] == info_a["business_phone"]
    assert by_recipient["+56999990002"]["from_phone"] == info_b["business_phone"]
    # Each tenant got its own notification ledger row.
    assert await _read_notifications_count(info_a["tenant_id"], audit_a) == 1
    assert await _read_notifications_count(info_b["tenant_id"], audit_b) == 1


async def test_alerter_marks_failed_when_send_fails(
    two_tenants_with_channels,
    fake_adapter,
):
    info = two_tenants_with_channels["a"]
    fake_adapter.fail_template_with = RuntimeError("provider unavailable")
    audit_id = await _seed_audit(
        tenant_info=info,
        action="integration.agendapro.needs_reauth",
        after_json={},
    )

    sm = get_sessionmaker()
    await _process_pending(sm, {"meta": fake_adapter})

    notif = await _read_notification(info["tenant_id"], audit_id)
    assert notif.status is OperatorNotificationStatus.FAILED
    assert "RuntimeError" in (notif.last_error or "")


async def test_alerter_skips_unrelated_audit_actions(
    two_tenants_with_channels,
    fake_adapter,
):
    """Audit rows for actions outside the watch list must not trigger sends."""
    info = two_tenants_with_channels["a"]
    await _seed_audit(
        tenant_info=info,
        action="agent_config.promoted",  # not on the alert list
        after_json={"version": 1},
    )

    sm = get_sessionmaker()
    await _process_pending(sm, {"meta": fake_adapter})

    assert len(fake_adapter.template_calls) == 0


async def test_an_escalation_reaches_every_payment_reviewer(
    two_tenants_with_channels,
    fake_adapter,
):
    """Spec 025: when the agent hands a conversation over, the business's
    payment reviewers hear it too, from the business number, once each; and
    the alert names the customer of the escalated conversation."""
    from nexus_api.db.models import AgentConfig, AgentConfigStatus

    info = two_tenants_with_channels["a"]
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, info["tenant_id"]):
        session.add(
            AgentConfig(
                tenant_id=info["tenant_id"],
                version=1,
                status=AgentConfigStatus.ACTIVE,
                system_prompt_rendered="x",
                policies={
                    "payment_review": {
                        "reviewers": [
                            {"phone": "+56991280655", "name": "Daniela"},
                            {"phone": "+56989829063", "name": None},
                        ]
                    }
                },
            )
        )
    await _seed_audit(
        tenant_info=info,
        action="conversation.escalated",
        after_json={"status": "escalated", "reason": "comuna fuera de la tabla"},
    )
    # escalate.escalate_to_human audits the conversation as the target.
    async with sm() as session, tenant_scoped_session(session, info["tenant_id"]):
        await session.execute(
            sa.update(AuditLog)
            .where(AuditLog.action == "conversation.escalated")
            .values(target=str(info["conversation_id"]))
        )

    await _process_pending(sm, {"meta": fake_adapter})

    recipients = sorted(c["recipient"] for c in fake_adapter.template_calls)
    # Both reviewers and the tenant's owner phone, each once.
    assert recipients == ["+56989829063", "+56991280655", "+56999990001"]
    for call in fake_adapter.template_calls:
        assert call["template_name"] == "alert_escalation_v1"
        assert call["from_phone"] == info["business_phone"]
        assert call["params"]["body"] == [info["customer_identifier"], "comuna fuera de la tabla"]
