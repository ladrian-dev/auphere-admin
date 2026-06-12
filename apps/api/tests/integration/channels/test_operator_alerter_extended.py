"""Block H: operator alerter — 3 new audit actions → WhatsApp templates.

The alerter (block F) ledgers + dispatches WhatsApp templates for
``conversation.escalated`` + ``integration.agendapro.needs_reauth``.
Block H adds three more action handlers:

- ``cost.daily_threshold_exceeded`` → ``alert_cost_threshold_v1``.
- ``isolation.violation_detected`` → ``alert_isolation_v1``.
- ``channel.whatsapp_5xx_burst`` → ``alert_whatsapp_burst_v1``.

These tests assert the action → template mapping + the rendered body
params shape so the YAML templates and runtime stay in sync.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from nexus_worker.streams.operator_alerts import _process_pending

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import AuditLog

pytestmark = pytest.mark.asyncio


async def _seed_audit(
    *, tenant_info: dict[str, Any], action: str, after_json: dict[str, Any]
) -> uuid.UUID:
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_info["tenant_id"]):
        audit = AuditLog(
            tenant_id=tenant_info["tenant_id"],
            actor="system:test",
            action=action,
            target=f"tenant:{tenant_info['tenant_id']}",
            before_json=None,
            after_json=after_json,
        )
        session.add(audit)
        await session.flush()
        await session.refresh(audit)
        return audit.id


async def test_alerter_sends_cost_threshold_template(two_tenants_with_channels, fake_adapter):
    info = two_tenants_with_channels["a"]
    await _seed_audit(
        tenant_info=info,
        action="cost.daily_threshold_exceeded",
        after_json={
            "day": "2026-05-09",
            "cost_usd_total": "42.50",
            "threshold_usd": "40.00",
            "message_count": 320,
        },
    )
    sm = get_sessionmaker()
    await _process_pending(sm, {"meta": fake_adapter})

    assert len(fake_adapter.template_calls) == 1
    call = fake_adapter.template_calls[0]
    assert call["template_name"] == "alert_cost_threshold_v1"
    assert "USD 42.50" in call["params"]["body"][0]
    assert "USD 40.00" in call["params"]["body"][0]


async def test_alerter_sends_isolation_template(two_tenants_with_channels, fake_adapter):
    info = two_tenants_with_channels["a"]
    await _seed_audit(
        tenant_info=info,
        action="isolation.violation_detected",
        after_json={
            "metric": "isolation.tool_whitelist_violation",
            "count": 3,
            "last_at": "2026-05-09T12:00:00+00:00",
            "window": "1h",
        },
    )
    sm = get_sessionmaker()
    await _process_pending(sm, {"meta": fake_adapter})

    assert len(fake_adapter.template_calls) == 1
    call = fake_adapter.template_calls[0]
    assert call["template_name"] == "alert_isolation_v1"
    assert call["params"]["body"] == ["isolation.tool_whitelist_violation", "3"]


async def test_alerter_sends_whatsapp_burst_template(two_tenants_with_channels, fake_adapter):
    info = two_tenants_with_channels["a"]
    await _seed_audit(
        tenant_info=info,
        action="channel.whatsapp_5xx_burst",
        after_json={
            "threshold": 5,
            "window_seconds": 120,
            "last_status_code": 503,
            "last_error": "upstream",
        },
    )
    sm = get_sessionmaker()
    await _process_pending(sm, {"meta": fake_adapter})

    assert len(fake_adapter.template_calls) == 1
    call = fake_adapter.template_calls[0]
    assert call["template_name"] == "alert_whatsapp_burst_v1"
    assert call["params"]["body"] == ["5"]
