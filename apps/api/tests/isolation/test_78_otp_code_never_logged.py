"""Garantía 6 (logs) — un código de un solo uso no queda en ningún log ni en la
fila cuando el envío termina. Spec 077, requisito 4.6.

Recorre el camino entero: la API encola el código, el despachador lo manda y la
fila queda sin él; un envío que la membresía corta tampoco lo deja. La captura
comprueba además que vio eventos de verdad, para que el test no pase en vacío.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa
import structlog
from nexus_channels.base import SendResult, SendStatus
from nexus_worker.streams.outbound import _drain_tenant

from nexus_api.core.partner_keys import generate_api_key
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    ApiKeyScope,
    Channel,
    ChannelStatus,
    ChannelType,
    Message,
    Partner,
    PartnerApiKey,
    ServiceMembership,
    Tenant,
    TenantPlan,
)
from nexus_api.services.whatsapp_templates import TemplateOut

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]

_CODE = "K4Z9Q1"
_OTP = TemplateOut(
    id="otp",
    name="tecfin_codigo",
    language="es",
    category="AUTHENTICATION",
    status="APPROVED",
    components=[
        {"type": "BODY", "text": "*{{1}}* es tu código de verificación."},
        {"type": "BUTTONS", "buttons": [{"type": "URL", "text": "Copiar código"}]},
    ],
)


@pytest.fixture(autouse=True)
def _stub_templates(monkeypatch):
    async def _fake_fetch(_session):
        return [_OTP], "waba-1"

    monkeypatch.setattr("nexus_api.services.broadcasts.fetch_templates", _fake_fetch)


@dataclass
class _Adapter:
    provider: str = "meta"
    channel_type: str = "whatsapp"
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def send_template(self, **kwargs: Any) -> SendResult:
        self.calls.append(kwargs)
        return SendResult(provider_message_id=f"wamid.{uuid.uuid4().hex}", status=SendStatus.SENT)


@pytest_asyncio.fixture
async def world(db_session) -> dict[str, Any]:
    tid, pid = uuid.uuid4(), uuid.uuid4()
    generated = generate_api_key()
    db_session.add(Tenant(id=tid, name="Tecfin", slug=f"tf-{tid.hex[:6]}", plan=TenantPlan.PRO))
    await db_session.flush()
    db_session.add(
        Channel(
            tenant_id=tid,
            type=ChannelType.WHATSAPP,
            provider="meta",
            provider_identifier=f"+3466{tid.int % 10_000_000:07d}",
            status=ChannelStatus.ACTIVE,
        )
    )
    db_session.add(Partner(id=pid, name="D", slug=f"d-{pid.hex[:6]}"))
    db_session.add(
        PartnerApiKey(
            partner_id=pid,
            tenant_id=tid,
            prefix_snippet=generated.prefix_snippet,
            key_hash=generated.key_hash,
            scopes=[ApiKeyScope.MESSAGES_SEND.value],
        )
    )
    await db_session.commit()
    return {"tenant_id": tid, "headers": {"Authorization": f"Bearer {generated.plaintext}"}}


async def _rows(tenant_id: uuid.UUID) -> list[Message]:
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
        return list((await s.scalars(sa.select(Message))).all())


async def test_sent_code_leaves_no_trace(client, world) -> None:
    adapter = _Adapter()
    with structlog.testing.capture_logs() as logs:
        resp = await client.post(
            "/v1/messages/template",
            json={"to": "+56912345678", "template_name": "tecfin_codigo", "code": _CODE},
            headers=world["headers"],
        )
        assert resp.status_code == 202, resp.text
        await _drain_tenant(get_sessionmaker(), world["tenant_id"], {"meta": adapter}, batch_size=5)
    events = [entry["event"] for entry in logs]
    assert "direct_message.queued" in events
    assert "outbound.dispatcher.template_send" in events
    assert _CODE not in repr(logs)
    assert adapter.calls and adapter.calls[0]["params"]["body"] == [_CODE]
    assert all(_CODE not in str(m.template_payload) for m in await _rows(world["tenant_id"]))


async def test_code_cut_by_the_membership_leaves_no_trace(client, world) -> None:
    resp = await client.post(
        "/v1/messages/template",
        json={"to": "+56912345678", "template_name": "tecfin_codigo", "code": _CODE},
        headers=world["headers"],
    )
    assert resp.status_code == 202
    # The membership lapses before the dispatcher picks it up.
    async with get_sessionmaker()() as s, tenant_scoped_session(s, world["tenant_id"]):
        s.add(
            ServiceMembership(
                tenant_id=world["tenant_id"], payer="stripe", amount_cents=4000, status="past_due"
            )
        )
    adapter = _Adapter()
    with structlog.testing.capture_logs() as logs:
        await _drain_tenant(get_sessionmaker(), world["tenant_id"], {"meta": adapter}, batch_size=5)
    assert "outbound.dispatcher.blocked_membership" in [e["event"] for e in logs]
    assert _CODE not in repr(logs)
    assert adapter.calls == []
    [row] = await _rows(world["tenant_id"])
    assert row.failure_code == "membership_inactive"
    assert _CODE not in str(row.template_payload)
