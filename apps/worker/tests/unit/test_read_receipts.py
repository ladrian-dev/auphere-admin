"""El runner envía el acuse de lectura que el webhook decidió.

El envío vivía dentro del handler del webhook y era una llamada HTTPS a
Meta esperada antes del 200 (~40 % del ack medido en staging el
2026-08-09). Aquí se fija el contrato del lado que lo recibe:

- el flag del stream se traduce a ``InboundEvent.mark_read``;
- con el flag, se envía UNA vez y con el wamid del mensaje;
- sin flag (canal send-only, remitente no admin, o entradas anteriores al
  cambio), no se envía nada;
- **un fallo del acuse no puede costar un turno** — es cosmético.
"""

from __future__ import annotations

import uuid

import pytest

from nexus_worker.runtime import read_receipts
from nexus_worker.streams.consumer import _to_event

pytestmark = pytest.mark.asyncio


def _fields(**extra: str) -> dict[str, str]:
    base = {
        "tenant_id": str(uuid.uuid4()),
        "channel_id": str(uuid.uuid4()),
        "user_id": "56911112222",
        "content": "hola",
        "provider_message_id": "wamid.abc",
    }
    base.update(extra)
    return base


@pytest.fixture(autouse=True)
def _clean_senders():
    read_receipts.reset_read_receipt_senders()
    yield
    read_receipts.reset_read_receipt_senders()


@pytest.mark.filterwarnings("ignore")
async def test_stream_flag_becomes_event_flag() -> None:
    assert _to_event(_fields(mark_read="1")).mark_read is True
    # Ausente o cualquier otro valor = no marcar. Fail-closed: una entrada
    # de antes de este cambio no dispara acuses retroactivos.
    assert _to_event(_fields()).mark_read is False
    assert _to_event(_fields(mark_read="0")).mark_read is False


async def test_send_uses_the_registered_sender_once() -> None:
    calls: list[dict] = []

    async def _sender(**kwargs) -> None:
        calls.append(kwargs)

    read_receipts.set_read_receipt_sender("meta", _sender)

    tenant_id, channel_id = uuid.uuid4(), uuid.uuid4()
    sent = await read_receipts.send_read_receipt(
        provider="meta", tenant_id=tenant_id, channel_id=channel_id, wamid="wamid.abc"
    )

    assert sent is True
    assert len(calls) == 1
    assert calls[0]["wamid"] == "wamid.abc"
    assert calls[0]["tenant_id"] == tenant_id
    assert calls[0]["channel_id"] == channel_id


async def test_no_sender_or_no_wamid_is_a_silent_noop() -> None:
    # Sin emisor registrado (p. ej. proveedor sin acuses) no es un error.
    assert (
        await read_receipts.send_read_receipt(
            provider="tiktok", tenant_id=uuid.uuid4(), channel_id=uuid.uuid4(), wamid="x"
        )
        is False
    )

    async def _sender(**kwargs) -> None:  # pragma: no cover - no debe llamarse
        raise AssertionError("sin wamid no hay nada que marcar")

    read_receipts.set_read_receipt_sender("meta", _sender)
    assert (
        await read_receipts.send_read_receipt(
            provider="meta", tenant_id=uuid.uuid4(), channel_id=uuid.uuid4(), wamid=None
        )
        is False
    )


async def test_a_failing_receipt_never_propagates() -> None:
    """La garantía que hace seguro llamarlo al principio del turno."""

    async def _boom(**kwargs) -> None:
        raise RuntimeError("Meta devolvió 500")

    read_receipts.set_read_receipt_sender("meta", _boom)

    assert (
        await read_receipts.send_read_receipt(
            provider="meta",
            tenant_id=uuid.uuid4(),
            channel_id=uuid.uuid4(),
            wamid="wamid.abc",
        )
        is False
    )
