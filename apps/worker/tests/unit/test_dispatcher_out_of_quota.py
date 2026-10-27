"""Spec 016 (R2.2, R2.6) y 047 (requisitos 2.1 y 2.4): sin cupo, la puerta cierra.

El silencio del 31-ago era ``allow_channel_turn`` cerrando la puerta sin que
nadie se enterase; y hasta la 047, además, sin guardar el mensaje. Ahora la
puerta de la bolsa va **después** de guardar (``accept_inbound``), dentro del
turno, y su motivo es ``no_balance``: la conversación espera a una persona y el
partner y el cliente reciben el aviso (eso lo prueban, contra la base,
``apps/api/tests/integration/test_dispatcher_persist_first.py`` y
``test_dispatcher_reason_notices.py``). Aquí, la puerta sola, sin base.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from nexus_worker.runtime import dispatcher

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


async def test_an_empty_bag_closes_with_its_reason(monkeypatch) -> None:
    from nexus_api.metering import wallet

    monkeypatch.setattr(wallet, "allow_channel_turn", AsyncMock(return_value=False))
    proxy = AsyncMock(side_effect=AssertionError("the proxy is not even asked"))
    monkeypatch.setattr("nexus_api.core.llm_proxy.partner_id_for_tenant_standalone", proxy)

    gate, partner = await dispatcher.money_and_model_gate(uuid.uuid4())

    assert gate == dispatcher.Gate("wallet_empty", "no_balance")
    assert partner is None


async def test_a_bag_with_quota_goes_on_to_the_model(monkeypatch) -> None:
    from nexus_api.metering import wallet

    monkeypatch.setattr(wallet, "allow_channel_turn", AsyncMock(return_value=True))
    monkeypatch.setattr(
        "nexus_api.core.llm_proxy.partner_id_for_tenant_standalone", AsyncMock(return_value=None)
    )

    gate, partner = await dispatcher.money_and_model_gate(uuid.uuid4())

    assert gate is None and partner is None


def test_the_bag_is_checked_only_after_the_base_gates() -> None:
    """Un cliente en pausa sin saldo espera por la pausa, no por el saldo: las
    puertas de la base deciden antes y la bolsa no llega a mirarse."""
    paused = dispatcher.TurnFacts(
        tenant_status=dispatcher.TenantStatus.PAUSED,
        channel_status=None,
        send_only_channel=False,
        has_active_agent=True,
        ever_had_agent=True,
        agent_active=True,
        out_of_audience=False,
    )
    assert dispatcher.gate_for(paused) == dispatcher.Gate("tenant_inactive", "paused_client")
