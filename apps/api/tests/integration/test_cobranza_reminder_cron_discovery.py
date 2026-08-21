"""The daily cobranza sweep must actually FIND the tenants it is meant to sweep.

This exists because the first cut of ``_cron_pass`` read the tenant list and
the per-tenant reminder config in one unscoped join. ``tenants`` carries no
RLS, but ``agent_configs`` is RLS-**forced** and its policy fails closed:
without ``app.tenant_id`` the predicate is NULL and every row is excluded. The
join returned zero rows — no error, no log line, a cron that would simply never
have fired. That is the same shape of silent failure that left Muna with zero
reminders for six weeks, so it gets a test rather than a comment.

The sweep itself is stubbed: what is under test is discovery and gating, not
the Amigable Cobro round-trip.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from nexus_worker.streams import cobranza_reminder_cron as cron

pytestmark = [pytest.mark.asyncio]


class _FakeRedis:
    """Always grants the daily claim, and records the keys asked for."""

    def __init__(self) -> None:
        self.keys: list[str] = []

    async def set(self, key: str, _value: str, **_kw: Any) -> bool:
        self.keys.append(key)
        return True


async def _tenant_with_reminders(
    db_session,
    *,
    enabled: bool,
    hour_local: int,
    timezone: str = "America/Caracas",
) -> uuid.UUID:
    from nexus_api.db.models import (
        AgentConfig,
        AgentConfigStatus,
        Tenant,
        TenantPlan,
        TenantStatus,
    )

    tenant_id = uuid.uuid4()
    db_session.add(
        Tenant(
            id=tenant_id,
            name="Muna Test",
            slug=f"muna-{tenant_id.hex[:6]}",
            plan=TenantPlan.PRO,
            status=TenantStatus.ACTIVE,
            timezone=timezone,
        )
    )
    # Commit the tenant before the config: the FK is checked immediately and
    # the two inserts otherwise land in the same flush in an undefined order.
    await db_session.commit()
    db_session.add(
        AgentConfig(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            version=1,
            status=AgentConfigStatus.ACTIVE,
            system_prompt_rendered="Eres Sofía.",
            channels=[],
            tools=["billing.send_reminders"],
            policies={
                "admin_access": {"admin_only": True, "admin_phones": ["+584249398142"]},
                "reminders": {
                    "enabled": enabled,
                    "hour_local": hour_local,
                    "max_overdue_days": 30,
                    "max_per_run": 50,
                },
            },
            seed_template_ref="cobranza_v1",
        )
    )
    await db_session.commit()
    return tenant_id


async def test_finds_the_tenant_despite_rls_on_agent_configs(db_session, monkeypatch) -> None:
    """The regression: config lives behind forced RLS, discovery must scope."""
    # 13:00 UTC == 09:00 in America/Caracas.
    tenant_id = await _tenant_with_reminders(db_session, enabled=True, hour_local=9)
    swept: list[tuple[uuid.UUID, Any]] = []

    async def _fake_sweep(tid: uuid.UUID, _name: str, **kw: Any) -> dict[str, Any]:
        swept.append((tid, kw))
        return {"status": "no_due_accounts", "queued": 0, "deferred": 0, "recipients": []}

    monkeypatch.setattr(cron, "send_due_reminders_for_tenant", _fake_sweep)
    await cron._cron_pass(_FakeRedis(), now=datetime(2026, 8, 21, 13, 0, tzinfo=UTC))

    assert [t for t, _ in swept] == [tenant_id], "the cron never discovered the tenant"
    # And it swept with the BUSINESS's date, not UTC's.
    assert swept[0][1]["today"].isoformat() == "2026-08-21"
    assert swept[0][1]["source"] == "cron"


async def test_skips_tenant_with_reminders_disabled(db_session, monkeypatch) -> None:
    await _tenant_with_reminders(db_session, enabled=False, hour_local=9)
    swept: list[uuid.UUID] = []

    async def _fake_sweep(tid: uuid.UUID, _name: str, **_kw: Any) -> dict[str, Any]:
        swept.append(tid)
        return {"status": "ok", "queued": 0, "deferred": 0, "recipients": []}

    monkeypatch.setattr(cron, "send_due_reminders_for_tenant", _fake_sweep)
    await cron._cron_pass(_FakeRedis(), now=datetime(2026, 8, 21, 13, 0, tzinfo=UTC))
    assert swept == []


async def test_fires_on_the_local_hour_not_the_utc_hour(db_session, monkeypatch) -> None:
    """09:00 in Caracas is 13:00 UTC. A cron gating on the UTC hour would fire
    at 05:00 local — inside the night, and on the wrong calendar day for the
    evening edge cases."""
    tenant_id = await _tenant_with_reminders(db_session, enabled=True, hour_local=9)
    swept: list[uuid.UUID] = []

    async def _fake_sweep(tid: uuid.UUID, _name: str, **_kw: Any) -> dict[str, Any]:
        swept.append(tid)
        return {"status": "ok", "queued": 0, "deferred": 0, "recipients": []}

    monkeypatch.setattr(cron, "send_due_reminders_for_tenant", _fake_sweep)

    # 09:00 UTC == 05:00 Caracas → must NOT fire.
    await cron._cron_pass(_FakeRedis(), now=datetime(2026, 8, 21, 9, 0, tzinfo=UTC))
    assert swept == []

    # 13:00 UTC == 09:00 Caracas → fires.
    await cron._cron_pass(_FakeRedis(), now=datetime(2026, 8, 21, 13, 0, tzinfo=UTC))
    assert swept == [tenant_id]


async def test_claims_the_local_day_once(db_session, monkeypatch) -> None:
    tenant_id = await _tenant_with_reminders(db_session, enabled=True, hour_local=9)
    redis = _FakeRedis()

    async def _fake_sweep(_tid: uuid.UUID, _name: str, **_kw: Any) -> dict[str, Any]:
        return {"status": "ok", "queued": 0, "deferred": 0, "recipients": []}

    monkeypatch.setattr(cron, "send_due_reminders_for_tenant", _fake_sweep)
    await cron._cron_pass(redis, now=datetime(2026, 8, 21, 13, 0, tzinfo=UTC))
    assert redis.keys == [f"nexus:cobranza_reminder:{tenant_id}:2026-08-21"]
