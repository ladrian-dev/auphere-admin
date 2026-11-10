"""Canal: wallet/asignación 0 o libro ilegible no abre el pipeline.

Spec 047: la puerta se mira dentro del turno, después de guardar el mensaje
(``dispatcher.money_and_model_gate``); el despachador entero, contra la base, lo
prueba ``apps/api/tests/integration/test_dispatcher_persist_first.py``.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from nexus_worker.runtime.dispatcher import Gate, InboundEvent, money_and_model_gate


@pytest.mark.asyncio
async def test_a_closed_wallet_closes_the_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "nexus_api.metering.wallet.allow_channel_turn",
        AsyncMock(return_value=False),
    )
    gate, _partner = await money_and_model_gate(uuid.uuid4())
    assert gate == Gate("wallet_empty", "no_balance")


@pytest.mark.asyncio
async def test_inbound_event_shape_still_builds() -> None:
    event = InboundEvent(
        tenant_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        user_id="u1",
        content="hola",
        provider="whatsapp",
    )
    assert event.content == "hola"
