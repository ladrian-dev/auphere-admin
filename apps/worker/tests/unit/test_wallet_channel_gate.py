"""Canal: wallet/asignación 0 o libro ilegible no abre el pipeline."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest

from nexus_worker.runtime.dispatcher import InboundEvent, process_inbound


class _Pipeline:
    def __init__(self) -> None:
        self.called = False

    async def ainvoke(
        self, state: dict[str, Any], config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self.called = True
        return {"intent": "info", "response": "ok", "tool_calls": []}


@pytest.mark.asyncio
async def test_process_inbound_skips_pipeline_when_wallet_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "nexus_api.metering.wallet.allow_channel_turn",
        AsyncMock(return_value=False),
    )
    pipeline = _Pipeline()
    event = InboundEvent(
        tenant_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        user_id="u1",
        content="hola",
        provider="whatsapp",
    )
    result = await process_inbound(event, pipeline=pipeline)
    assert result["skipped"] == "wallet_empty"
    assert pipeline.called is False


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
    assert process_inbound is not None
