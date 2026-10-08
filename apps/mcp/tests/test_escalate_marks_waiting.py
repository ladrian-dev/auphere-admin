"""Spec 030 T068 — ``escalate.escalate_to_human`` pasa por ``mark_waiting``.

El escalado vive en un solo sitio (``inbox_lifecycle``): la herramienta ya no
escribe ``ESCALATED`` a mano. Lo que fija este archivo:

- la herramienta llama a ``mark_waiting`` con el motivo y el resumen del
  agente, dentro de su transacción;
- avisa (``announce_waiting``) **después** de cerrar la transacción, nunca
  antes;
- conserva lo de hoy: la auditoría ``conversation.escalated`` con el motivo, y
  la consulta al dueño por el backchannel cuando está activo (sin cambios).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any

import pytest
from nexus_api.db.models import Conversation, ConversationStatus, Tenant
from nexus_api.services.inbox_lifecycle import WaitingMark

from nexus_mcp.servers.escalate import tools as escalate_tools
from nexus_mcp.servers.escalate.schemas import EscalateToHumanInput

pytestmark = [pytest.mark.unit]


async def test_escalation_marks_waiting_then_announces(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id, conv_id = uuid.uuid4(), uuid.uuid4()
    conv = SimpleNamespace(id=conv_id, tenant_id=tenant_id, status=ConversationStatus.OPEN)
    tenant = SimpleNamespace(id=tenant_id, backchannel_enabled=False)
    calls: list[tuple[str, Any]] = []
    open_tx = {"value": False}

    class _Session:
        async def get(self, model: type, key: uuid.UUID) -> Any:
            return (
                {Conversation: conv, Tenant: tenant}[model] if key in (conv_id, tenant_id) else None
            )

        async def flush(self) -> None:
            return None

    @asynccontextmanager
    async def _tool_session() -> AsyncIterator[_Session]:
        open_tx["value"] = True
        yield _Session()
        open_tx["value"] = False
        calls.append(("commit", None))

    class _Audit:
        def __init__(self, session: Any) -> None:
            pass

        async def record(self, **kw: Any) -> Any:
            calls.append(("audit", kw))
            return SimpleNamespace(id=uuid.uuid4())

    async def _mark(
        session: Any, c: Any, *, reason: str | None, summary: str | None
    ) -> WaitingMark:
        assert open_tx["value"], "mark_waiting corre dentro de la transacción"
        c.status = ConversationStatus.ESCALATED
        calls.append(("mark", {"reason": reason, "summary": summary}))
        return WaitingMark(
            tenant_id=tenant_id,
            conversation_id=conv_id,
            event_id=uuid.uuid4(),
            inbox=True,
            contact="Ana",
        )

    async def _announce(mark: WaitingMark, **kw: Any) -> None:
        assert not open_tx["value"], "el aviso sale después del commit"
        calls.append(("announce", mark.conversation_id))

    monkeypatch.setattr(escalate_tools, "tool_session", _tool_session)
    monkeypatch.setattr(escalate_tools, "AuditRepository", _Audit)
    monkeypatch.setattr(escalate_tools.inbox_lifecycle, "mark_waiting", _mark)
    monkeypatch.setattr(escalate_tools.inbox_lifecycle, "announce_waiting", _announce)

    out = await escalate_tools.EscalateToHuman().run(
        EscalateToHumanInput(
            conversation_id=conv_id, reason="Pide un reembolso", customer_summary="Habitual"
        )
    )

    assert out.status == "operator_notified"
    assert [c[0] for c in calls] == ["mark", "audit", "commit", "announce"]
    assert calls[0][1] == {"reason": "Pide un reembolso", "summary": "Habitual"}
    audit = calls[1][1]
    assert audit["action"] == "conversation.escalated"
    assert audit["before"] == {"status": "open"}
    assert audit["after"] == {"status": "escalated", "reason": "Pide un reembolso"}
