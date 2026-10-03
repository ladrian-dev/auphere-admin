"""Spec 016 (R2.2, R2.6): el turno saltado por falta de cupo avisa al partner.

El silencio del 31-ago era esto: ``allow_channel_turn`` cerraba la puerta y
nadie se enteraba. Ahora el despachador llama al aviso por cliente con el
``tenant_id`` y sigue devolviendo exactamente lo que devolvía; el cliente
final no recibe nada distinto, y un aviso roto nunca tumba el turno.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from nexus_worker.runtime.dispatcher import InboundEvent, _process_inbound

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


def _event() -> InboundEvent:
    return InboundEvent(
        tenant_id=uuid.uuid4(),
        channel_id=uuid.uuid4(),
        user_id="+34600000000",
        content="hola",
        mark_read=False,
    )


async def test_skipped_turn_notifies_the_partner_and_answers_nothing(monkeypatch) -> None:
    from nexus_api.metering import wallet
    from nexus_api.services import wallet_alerts

    monkeypatch.setattr(wallet, "allow_channel_turn", AsyncMock(return_value=False))
    notify = AsyncMock(return_value=None)
    monkeypatch.setattr(wallet_alerts, "notify_client_out_of_quota_detached", notify)
    pipeline = AsyncMock()

    event = _event()
    out = await _process_inbound(event, pipeline=pipeline)

    assert out == {"skipped": "wallet_empty"}
    notify.assert_awaited_once_with(event.tenant_id)
    pipeline.assert_not_called()


async def test_a_broken_notice_never_costs_the_turns_answer(monkeypatch) -> None:
    from nexus_api.metering import wallet
    from nexus_api.services import wallet_alerts

    monkeypatch.setattr(wallet, "allow_channel_turn", AsyncMock(return_value=False))
    monkeypatch.setattr(
        wallet_alerts,
        "notify_client_out_of_quota_detached",
        AsyncMock(side_effect=RuntimeError("bd caída")),
    )
    assert await _process_inbound(_event(), pipeline=AsyncMock()) == {"skipped": "wallet_empty"}


async def test_a_turn_with_quota_does_not_notify(monkeypatch) -> None:
    from nexus_api.metering import wallet
    from nexus_api.services import wallet_alerts

    monkeypatch.setattr(wallet, "allow_channel_turn", AsyncMock(return_value=True))
    notify = AsyncMock()
    monkeypatch.setattr(wallet_alerts, "notify_client_out_of_quota_detached", notify)
    # Lo primero tras la puerta es el proxy del partner: se corta ahí a
    # propósito, con un fallo que el test reconoce.
    monkeypatch.setattr(
        "nexus_api.core.llm_proxy.partner_id_for_tenant_standalone",
        AsyncMock(side_effect=RuntimeError("stop here")),
    )
    with pytest.raises(RuntimeError, match="stop here"):
        await _process_inbound(_event(), pipeline=AsyncMock())
    notify.assert_not_called()
