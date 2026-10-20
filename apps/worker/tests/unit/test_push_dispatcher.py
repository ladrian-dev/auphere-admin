"""Spec 031 · R8.2 — la tarea ``push-dispatcher`` (T087).

La lógica de a quién y qué vive en ``nexus_api.services.push_fanout`` y la
barren las suites de la API. Aquí, el envío: cada aviso va al proveedor de su
teléfono con el payload del contrato, y el resultado vuelve tal cual para que
``settle`` lo anote.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from nexus_api.services import push_fanout
from nexus_api.services.push_payloads import Notice

from nexus_worker.push import dispatcher
from nexus_worker.push._result import SendResult

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


def _outgoing(provider: str) -> push_fanout.Outgoing:
    return push_fanout.Outgoing(
        delivery_id=uuid.uuid4(),
        event_id=uuid.uuid4(),
        phone_id=uuid.uuid4(),
        provider=provider,
        token="t" * 64,
        apns_environment="sandbox" if provider == "apns" else None,
        notice=Notice(
            kind="inbox.waiting",
            title="Martín Ruiz espera a una persona",
            body="Pide un reembolso.",
            url="auphere-customers://inbox/abc",
            thread="abc",
            badge=2,
        ),
    )


class _FakeApns:
    topic = "com.auphere.customers"

    def __init__(self, result: SendResult) -> None:
        self.calls: list[dict[str, Any]] = []
        self.result = result

    async def send(self, **kw: Any) -> SendResult:
        self.calls.append(kw)
        return self.result


class _FakeFcm:
    def __init__(self, result: SendResult) -> None:
        self.calls: list[dict[str, Any]] = []
        self.result = result

    async def send(self, message: dict[str, Any]) -> SendResult:
        self.calls.append(message)
        return self.result


async def test_an_iphone_notice_goes_to_apns_with_the_contract_payload() -> None:
    apns = _FakeApns(SendResult(outcome="sent", provider_message_id="apns-1"))
    fcm = _FakeFcm(SendResult(outcome="sent"))
    o = _outgoing("apns")

    r = await dispatcher.deliver(o, apns=apns, fcm=fcm)  # type: ignore[arg-type]

    assert (r.outcome, r.provider_message_id, r.delivery_id) == ("sent", "apns-1", o.delivery_id)
    (call,) = apns.calls
    assert call["environment"] == "sandbox"
    assert call["headers"]["apns-push-type"] == "alert"
    assert call["payload"]["aps"]["interruption-level"] == "time-sensitive"
    assert call["payload"]["body"] == {
        "url": "auphere-customers://inbox/abc",
        "kind": "inbox.waiting",
    }
    assert fcm.calls == []


async def test_an_android_notice_goes_to_fcm_as_data() -> None:
    apns = _FakeApns(SendResult(outcome="sent"))
    fcm = _FakeFcm(SendResult(outcome="unregistered", error_code="UNREGISTERED"))

    r = await dispatcher.deliver(_outgoing("fcm"), apns=apns, fcm=fcm)  # type: ignore[arg-type]

    assert (r.outcome, r.error_code) == ("unregistered", "UNREGISTERED")
    (message,) = fcm.calls
    assert message["message"]["data"]["channelId"] == "waiting_v1"
    assert message["message"]["android"]["priority"] == "high"
    assert apns.calls == []


async def test_the_work_set_parses_notifications() -> None:
    work = dispatcher.PushWorkSet()
    tid = uuid.uuid4()
    work.add_raw(str(tid))
    work.add_raw("no-es-un-uuid")
    assert work.pop_all() == {tid}
    assert work.pop_all() == set()
