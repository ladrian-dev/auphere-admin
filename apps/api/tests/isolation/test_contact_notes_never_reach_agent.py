"""Spec 030 T019 — la nota interna de un contacto nunca llega al agente (R13.5, D18).

La Bandeja deja que el equipo del cliente escriba una nota sobre un contacto
(``contact_notes``). Es del equipo: no la recibe el contacto y **no la lee el
agente**. Dos pruebas, una estructural y una de comportamiento:

1. **Barrido**: ni ``ContactNote`` ni ``contact_notes`` aparecen en el código
   del worker ni de los servidores MCP — quien arma el turno del agente y las
   herramientas que el agente llama. Si alguien la necesitara allí, este test
   le obliga a decidirlo a la vista.
2. **El turno real**: con una nota sembrada, el estado que el despachador
   entrega al pipeline —incluido el resumen de una devolución, que es donde
   más fácil sería colarla— no contiene su texto.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from nexus_worker.runtime.dispatcher import InboundEvent, process_inbound

from nexus_api.db.models import (
    AgentConfig,
    AgentConfigStatus,
    ContactNote,
    Conversation,
    Customer,
)
from tests.conftest import make_inbox

pytestmark = [pytest.mark.isolation]

_ROOT = Path(__file__).resolve().parents[4]
_AGENT_SIDE = [_ROOT / "apps" / "worker" / "src", _ROOT / "apps" / "mcp" / "src"]
_NEEDLE = re.compile(r"ContactNote|contact_notes")
NOTE = "NOTA-INTERNA-7f3a: no ofrecerle descuentos, debe dos facturas"


def test_the_agent_side_never_names_the_notes() -> None:
    files = [f for root in _AGENT_SIDE for f in root.rglob("*.py")]
    assert len(files) > 50, "the sweep is looking at the wrong place"
    offenders = [str(f.relative_to(_ROOT)) for f in files if _NEEDLE.search(f.read_text())]
    assert not offenders, f"the agent side reads internal notes: {offenders}"


class _RecordingPipeline:
    def __init__(self) -> None:
        self.states: list[dict[str, Any]] = []

    async def ainvoke(
        self, state: dict[str, Any], config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self.states.append(state)
        return {"intent": "info", "response": "ok", "tool_calls": []}


@pytest.mark.asyncio
async def test_a_turn_never_carries_the_note(db_session, console_world) -> None:
    w = console_world["a"]
    inbox = await make_inbox(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"], conversations=1
    )
    conv_id, customer_id = inbox["conversations"][0], inbox["customers"][0]
    customer = await db_session.get(Customer, customer_id)
    db_session.add_all(
        [
            AgentConfig(
                tenant_id=w["tenant_id"],
                version=1,
                status=AgentConfigStatus.ACTIVE,
                system_prompt_rendered="Eres un asistente de prueba.",
                channels=[],
                tools=[],
                policies={},
                created_by="test",
            ),
            ContactNote(
                tenant_id=w["tenant_id"], customer_id=customer_id, body=NOTE, updated_by="t"
            ),
        ]
    )
    # Una devolución pendiente: el turno siguiente arma el resumen para el agente.
    conv = await db_session.get(Conversation, conv_id)
    conv.takeover_context = {
        "reason": "inbox",
        "notes": None,
        "started_at": "2026-01-01T00:00:00+00:00",
        "operator_id": "Valeria",
    }
    await db_session.commit()

    pipeline = _RecordingPipeline()
    await process_inbound(
        InboundEvent(
            tenant_id=w["tenant_id"],
            channel_id=inbox["channel_id"],
            user_id=customer.identifier,
            content="hola de nuevo",
        ),
        pipeline=pipeline,
    )

    assert len(pipeline.states) == 1, "the turn must reach the pipeline"
    dumped = json.dumps(pipeline.states[0], default=str)
    assert "Contexto interno" in dumped, "the briefing was built (control)"
    assert "NOTA-INTERNA-7f3a" not in dumped
