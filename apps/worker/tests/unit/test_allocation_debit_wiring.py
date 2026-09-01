"""D6: el consumo del canal debita los DOS libros, no solo el wallet.

``partner_wallets`` es el saldo del partner; ``partner_allocations.remaining``
es el techo por cliente que el partner fija en Consumo. Hasta el 2026-09-01
solo se debitaba el primero: ``debit_allocation`` existía, estaba probada y
**no la llamaba nadie salvo los tests**, así que ``remaining`` no bajaba nunca,
``usage_ledger`` estaba a 0 filas y el tope por cliente era un on/off.

Tras ADR-036 esto dejó de ser deuda y pasó a ser bloqueante: al renunciar al
proxy, el wallet es el único techo de gasto que queda.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock

import pytest

from nexus_worker.metering import consumer


def _event(meter: str, quantity: int, *, seq: int = 1) -> dict:
    return {
        "meter": meter,
        "quantity": quantity,
        "idempotency_key": f"t1:{seq}:{meter}",
        "occurred_at": "2026-09-01T10:00:00+00:00",
        "provider": "openai",
        "model": "openai/gpt-5.6-sol",
    }


def _rows(source: str = "channel") -> tuple[uuid.UUID, list[dict]]:
    return consumer.rows_from_entry(
        {
            "tenant_id": str(uuid.uuid4()),
            "turn_id": "t1",
            "source": source,
            "events": json.dumps(
                [
                    _event("llm.input_tokens", 10_000),
                    _event("llm.output_tokens", 100),
                    _event("llm.cache_read", 9_000),
                ]
            ),
        }
    )


@pytest.mark.asyncio
async def test_channel_turn_debits_wallet_and_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id, rows = _rows()
    partner_id = uuid.uuid4()
    monkeypatch.setattr(consumer, "_partner_for", AsyncMock(return_value=partner_id))
    wallet = AsyncMock()
    allocation = AsyncMock()
    monkeypatch.setattr("nexus_api.metering.wallet.debit_wallet", wallet)
    monkeypatch.setattr("nexus_api.metering.wallet.debit_allocation", allocation)

    await consumer._debit_channel_wallet(tenant_id, rows)

    assert wallet.await_count == 1, "el wallet del partner tiene que bajar"
    assert allocation.await_count == 1, "el remaining del cliente también"
    w = wallet.await_args.kwargs
    a = allocation.await_args.kwargs
    # Misma cantidad y misma clave: ``debit_allocation`` la sufija por dentro,
    # así que un reintento del stream no dobla ninguno de los dos libros.
    assert a["qty"] == w["qty"] > 0
    assert a["idempotency_key"] == w["idempotency_key"]
    assert a["partner_id"] == partner_id
    assert a["tenant_id"] == tenant_id


@pytest.mark.asyncio
async def test_allocation_failure_does_not_hide_a_good_wallet_debit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un fallo del segundo libro no puede tumbar ni enmascarar al primero."""
    tenant_id, rows = _rows()
    monkeypatch.setattr(consumer, "_partner_for", AsyncMock(return_value=uuid.uuid4()))
    wallet = AsyncMock()
    monkeypatch.setattr("nexus_api.metering.wallet.debit_wallet", wallet)
    monkeypatch.setattr(
        "nexus_api.metering.wallet.debit_allocation",
        AsyncMock(side_effect=RuntimeError("boom")),
    )

    await consumer._debit_channel_wallet(tenant_id, rows)  # no propaga

    assert wallet.await_count == 1


@pytest.mark.asyncio
async def test_qa_source_debits_neither_book(monkeypatch: pytest.MonkeyPatch) -> None:
    """El gasto del Playground no es coste del cliente y no come su tope."""
    tenant_id, rows = _rows(source="qa")
    wallet = AsyncMock()
    allocation = AsyncMock()
    monkeypatch.setattr("nexus_api.metering.wallet.debit_wallet", wallet)
    monkeypatch.setattr("nexus_api.metering.wallet.debit_allocation", allocation)

    await consumer._debit_channel_wallet(tenant_id, rows)

    assert wallet.await_count == 0
    assert allocation.await_count == 0
