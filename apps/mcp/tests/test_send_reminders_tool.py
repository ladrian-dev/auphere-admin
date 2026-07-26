"""Unit tests for ``billing.send_reminders`` — the on-demand reminder tool.

The whole point of this tool is that reminders go out ONLY on an explicit,
confirmed admin request. These tests pin the two guarantees that enforce it:
the ``confirm`` gate, and that a confirmed call delegates to the tenant sweep
and reports its summary back.
"""

from __future__ import annotations

import uuid

import pytest
from nexus_api.core.tenant_context import tenant_context

from nexus_mcp.servers.amigable_cobro import tools as amigable_tools
from nexus_mcp.servers.amigable_cobro.schemas import SendRemindersInput

pytestmark = [pytest.mark.unit]


async def test_refuses_without_confirmation() -> None:
    """confirm=False must NEVER send — no tenant lookup, no sweep."""
    out = await amigable_tools.SendReminders().run(SendRemindersInput(confirm=False))
    assert out.status == "not_confirmed"
    assert out.queued == 0
    assert out.recipients == []


async def test_confirmed_call_delegates_and_reports(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id = uuid.uuid4()
    calls: list[tuple] = []

    async def _fake_tenant_name(tid: uuid.UUID) -> str:
        return "Barbería López"

    async def _fake_sweep(tid, name, **kw):
        calls.append((tid, name))
        return {
            "status": "ok",
            "queued": 2,
            "recipients": [
                {"cliente": "Juan", "stage": "T-3", "monto": "$50,00", "fecha": "23/07/2026"},
                {"cliente": "Ana", "stage": "T0", "monto": "$10,00", "fecha": "20/07/2026"},
            ],
        }

    monkeypatch.setattr(amigable_tools, "_tenant_name", _fake_tenant_name)
    monkeypatch.setattr(
        "nexus_worker.streams.cobranza_reminder_cron.send_due_reminders_for_tenant",
        _fake_sweep,
    )

    with tenant_context(tenant_id):
        out = await amigable_tools.SendReminders().run(SendRemindersInput(confirm=True))

    assert calls == [(tenant_id, "Barbería López")]
    assert out.status == "ok"
    assert out.queued == 2
    assert [r.cliente for r in out.recipients] == ["Juan", "Ana"]


async def test_confirmed_call_surfaces_no_connector(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_tenant_name(tid: uuid.UUID) -> str:
        return "Sin Conector"

    async def _fake_sweep(tid, name, **kw):
        return {"status": "no_connector", "queued": 0, "recipients": []}

    monkeypatch.setattr(amigable_tools, "_tenant_name", _fake_tenant_name)
    monkeypatch.setattr(
        "nexus_worker.streams.cobranza_reminder_cron.send_due_reminders_for_tenant",
        _fake_sweep,
    )

    with tenant_context(uuid.uuid4()):
        out = await amigable_tools.SendReminders().run(SendRemindersInput(confirm=True))

    assert out.status == "no_connector"
    assert out.queued == 0
    assert "conector" in out.message.lower()
