"""El consumo del canal baja el tope del cliente UNA vez, dentro de
``debit_wallet``.

``partner_wallets`` es el saldo del partner; ``partner_allocations.remaining``
es el techo por cliente que el partner fija en Consumo. ``debit_wallet`` con
``tenant_id`` baja los dos, por lo que de verdad cobra y en una transacción.

Historia, para que no se repita: el 2026-09-02 este fichero fijó que el
consumidor llamara a ``debit_wallet`` **y** a ``debit_allocation``, creyendo que
el tope no bajaba nunca. Lo bajaba ya el primero, así que desde entonces bajó
dos veces — el cliente se quedaba mudo a mitad de su tope —. Con dobles
independientes eso no se ve; lo fija contra la base real
``apps/api/tests/integration/test_channel_debit_once.py``. Bug
``doble-cobro-del-tope``.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock

import pytest

from nexus_worker.metering import consumer


@pytest.fixture(autouse=True)
def _catalog(monkeypatch):
    """El débito necesita los tres pesos por carril (spec 007, R1.2).

    Se inyecta en vez de dejar que ``get_catalog()`` vaya a la base: este es un
    test unit sin Postgres, y pedirlo de verdad cachea un motor que después
    rompe otro test del dispatcher. Los pesos son 1 —el neutro— porque lo que
    este fichero prueba es el CABLEADO de los dos libros, no la ponderación.

    ``quota_weight`` sigue en el doble aunque esté deprecada: mientras la
    columna exista, un doble que no la tenga se parece menos a la fila real.
    """
    from decimal import Decimal

    class _Row:
        quota_weight = Decimal(1)
        quota_weight_input = Decimal(1)
        quota_weight_cache_read = Decimal(1)
        quota_weight_output = Decimal(1)

    async def _fake_catalog():
        return {"openai/gpt-5.6-sol": _Row()}

    monkeypatch.setattr(consumer, "get_catalog", _fake_catalog)


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
async def test_channel_turn_debits_the_wallet_once_with_its_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id, rows = _rows()
    partner_id = uuid.uuid4()
    monkeypatch.setattr(consumer, "_partner_for", AsyncMock(return_value=partner_id))
    wallet = AsyncMock()
    monkeypatch.setattr("nexus_api.metering.wallet.debit_wallet", wallet)

    await consumer._debit_channel_wallet(tenant_id, rows)

    assert wallet.await_count == 1
    w = wallet.await_args.kwargs
    assert w["partner_id"] == partner_id
    # With the client: that is what lowers its cap, inside the same debit.
    assert w["tenant_id"] == tenant_id
    assert w["qty"] > 0
    assert w["allow_included"] is False


def test_there_is_no_second_cap_debit_to_wire_by_mistake() -> None:
    from nexus_api.metering import wallet

    assert not hasattr(wallet, "debit_allocation")


@pytest.mark.asyncio
async def test_qa_source_debits_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """El gasto del Playground no es coste del cliente y no come su tope."""
    tenant_id, rows = _rows(source="qa")
    wallet = AsyncMock()
    monkeypatch.setattr("nexus_api.metering.wallet.debit_wallet", wallet)

    await consumer._debit_channel_wallet(tenant_id, rows)

    assert wallet.await_count == 0


def test_wallet_renewal_cron_is_registered_in_the_scheduler() -> None:
    """D3 solo sirve si el scheduler lo arranca.

    Guardián barato: el cron existía, estaba probado y no corría nadie es
    exactamente lo que pasó con ``debit_allocation``.
    """
    from nexus_worker.bootstrap import SCHEDULER_TASK_NAMES

    assert "wallet-renewal-cron" in SCHEDULER_TASK_NAMES
