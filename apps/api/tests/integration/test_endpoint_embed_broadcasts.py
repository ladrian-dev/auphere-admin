"""``POST /v1/embed/broadcasts`` fan-out E2E (ADR-028, Fase 1).

Template resolution is monkeypatched (Meta Graph is not reachable in
tests); everything else is real: RLS scoping from the JWT, customer /
conversation upserts, opt-out pre-flight, pending ``messages`` rows with
``template_payload``, idempotent replay, and the status aggregation
endpoint.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
import sqlalchemy as sa

from nexus_api.core.embed_jwt import mint_widget_token
from nexus_api.core.partner_keys import generate_api_key
from nexus_api.db.models import (
    Broadcast,
    BroadcastRecipient,
    Channel,
    ChannelStatus,
    ChannelType,
    Customer,
    Message,
    MessageStatus,
    Partner,
    PartnerApiKey,
    PartnerTenant,
    Tenant,
    TenantPlan,
    WhatsAppOptOut,
)
from nexus_api.services.whatsapp_templates import TemplateOut

pytestmark = pytest.mark.asyncio


async def _set_tenant(session, tenant_id: uuid.UUID) -> None:
    """RLS scope for direct DB assertions — same recipe as the isolation
    suite's helper."""
    await session.execute(
        sa.text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
    )
    await session.execute(sa.text("SET LOCAL ROLE nexus_app"))

_TEMPLATE = TemplateOut(
    id="t1",
    name="cobro_pendiente",
    language="es",
    category="UTILITY",
    status="APPROVED",
    components=[
        {
            "type": "BODY",
            "text": "Hola {{cliente}}, tienes un saldo de {{saldo_pendiente}}.",
        }
    ],
)

_PAUSED_TEMPLATE = TemplateOut(
    id="t2",
    name="promo_pausada",
    language="es",
    category="MARKETING",
    status="PAUSED",
    components=[{"type": "BODY", "text": "Hola {{cliente}}"}],
)

_POSITIONAL_TEMPLATE = TemplateOut(
    id="t3",
    name="legacy_posicional",
    language="es",
    category="UTILITY",
    status="APPROVED",
    components=[{"type": "BODY", "text": "Hola {{1}}, saldo {{2}}"}],
)


@pytest.fixture(autouse=True)
def _stub_templates(monkeypatch):
    async def _fake_fetch(_session):
        return [_TEMPLATE, _PAUSED_TEMPLATE, _POSITIONAL_TEMPLATE], "waba-1"

    # Both the fan-out validator and GET /templates funnel through this.
    monkeypatch.setattr("nexus_api.services.broadcasts.fetch_templates", _fake_fetch)
    monkeypatch.setattr("nexus_api.api.embed.fetch_templates", _fake_fetch)


@pytest_asyncio.fixture
async def world(db_session):
    tenant_id, partner_id, key_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    generated = generate_api_key()
    db_session.add(
        Tenant(id=tenant_id, name="B", slug=f"bt-{tenant_id.hex[:6]}", plan=TenantPlan.PRO)
    )
    await db_session.flush()
    channel = Channel(
        tenant_id=tenant_id,
        type=ChannelType.WHATSAPP,
        provider="meta",
        provider_identifier="+34632719028",
        status=ChannelStatus.ACTIVE,
    )
    db_session.add(channel)
    db_session.add(Partner(id=partner_id, name="P", slug=f"pp-{partner_id.hex[:6]}"))
    db_session.add(
        PartnerApiKey(
            id=key_id,
            partner_id=partner_id,
            prefix_snippet=generated.prefix_snippet,
            key_hash=generated.key_hash,
        )
    )
    db_session.add(
        PartnerTenant(
            partner_id=partner_id, external_client_ref="c1", tenant_id=tenant_id
        )
    )
    await db_session.commit()
    await db_session.refresh(channel)

    token, _jti, _exp = mint_widget_token(
        tenant_id=tenant_id,
        partner_id=partner_id,
        key_id=key_id,
        scope=["widget:send"],
        allowed_origins=[],
    )
    return {
        "tenant_id": tenant_id,
        "partner_id": partner_id,
        "channel_id": channel.id,
        "headers": {"Authorization": f"Bearer {token}"},
    }


def _payload(**overrides):
    payload = {
        "template_name": "cobro_pendiente",
        "language": "es",
        "recipients": [
            {"phone": "+56 9 1111 2223", "variables": {"cliente": "Ana", "saldo_pendiente": "$12.000"}},
            {"phone": "+56911112224", "variables": {"cliente": "Luis", "saldo_pendiente": "$8.000"}},
        ],
    }
    payload.update(overrides)
    return payload


async def test_fanout_creates_pending_template_messages(client, world, db_session) -> None:
    resp = await client.post("/v1/embed/broadcasts", json=_payload(), headers=world["headers"])
    assert resp.status_code == 202
    body = resp.json()
    assert body["accepted"] == 2
    assert body["rejected"] == []

    await db_session.rollback()  # clear any autobegin state from fixtures
    async with db_session.begin():
        await _set_tenant(db_session, world["tenant_id"])
        messages = (
            (await db_session.execute(sa.select(Message).where(Message.template_payload.is_not(None))))
            .scalars()
            .all()
        )
        assert len(messages) == 2
        assert all(m.status.value == "pending" for m in messages)
        assert all(m.actor_kind == "system" for m in messages)
        params = {m.template_payload["params"]["body"]["cliente"] for m in messages}
        assert params == {"Ana", "Luis"}
        # Customer identifiers use Meta's from-format: digits WITHOUT '+',
        # spaces stripped — exactly what the inbound webhook writes.
        customers = (
            (await db_session.execute(sa.select(Customer.identifier))).scalars().all()
        )
        assert sorted(customers) == ["56911112223", "56911112224"]


async def test_recipients_are_validated_and_reported(client, world, db_session) -> None:
    await db_session.rollback()  # clear any autobegin state from fixtures
    async with db_session.begin():
        db_session.add(
            WhatsAppOptOut(
                tenant_id=world["tenant_id"],
                channel_id=world["channel_id"],
                recipient_phone="56922223333",
                reason="keyword_stop",
                opted_out_at=datetime.now(UTC),
            )
        )
    payload = _payload(
        recipients=[
            {"phone": "+56911112223", "variables": {"cliente": "Ana", "saldo_pendiente": "$1"}},
            {"phone": "+56911112223", "variables": {"cliente": "Ana", "saldo_pendiente": "$1"}},
            {"phone": "no-es-numero", "variables": {"cliente": "X", "saldo_pendiente": "$1"}},
            {"phone": "+56922223333", "variables": {"cliente": "Opt", "saldo_pendiente": "$1"}},
            {"phone": "+56933334444", "variables": {"cliente": "Sin"}},
        ]
    )
    resp = await client.post("/v1/embed/broadcasts", json=payload, headers=world["headers"])
    assert resp.status_code == 202
    body = resp.json()
    assert body["accepted"] == 1
    reasons = {r["phone"]: r["reason"] for r in body["rejected"]}
    assert reasons["+56911112223"] == "duplicate"
    assert reasons["no-es-numero"] == "invalid_phone"
    assert reasons["+56922223333"] == "opted_out"
    assert reasons["+56933334444"].startswith("missing_variables:saldo_pendiente")


async def test_cap_is_enforced(client, world, db_session) -> None:
    await db_session.execute(
        sa.update(Partner)
        .where(Partner.id == world["partner_id"])
        .values(broadcast_recipient_cap=1)
    )
    await db_session.commit()
    resp = await client.post("/v1/embed/broadcasts", json=_payload(), headers=world["headers"])
    assert resp.status_code == 413


async def test_unknown_template_is_422(client, world) -> None:
    resp = await client.post(
        "/v1/embed/broadcasts",
        json=_payload(template_name="no_existe"),
        headers=world["headers"],
    )
    assert resp.status_code == 422


async def test_paused_template_is_422(client, world) -> None:
    resp = await client.post(
        "/v1/embed/broadcasts",
        json=_payload(template_name="promo_pausada"),
        headers=world["headers"],
    )
    assert resp.status_code == 422
    assert "PAUSED" in resp.json()["detail"]


async def test_positional_template_is_422(client, world) -> None:
    resp = await client.post(
        "/v1/embed/broadcasts",
        json=_payload(template_name="legacy_posicional"),
        headers=world["headers"],
    )
    assert resp.status_code == 422
    assert "named" in resp.json()["detail"]


async def test_idempotency_key_replays_without_double_send(client, world, db_session) -> None:
    payload = _payload(idempotency_key="op-123")
    first = await client.post("/v1/embed/broadcasts", json=payload, headers=world["headers"])
    assert first.status_code == 202
    second = await client.post("/v1/embed/broadcasts", json=payload, headers=world["headers"])
    assert second.status_code == 200
    assert second.json()["broadcast_id"] == first.json()["broadcast_id"]

    await db_session.rollback()  # clear any autobegin state from fixtures
    async with db_session.begin():
        await _set_tenant(db_session, world["tenant_id"])
        count = await db_session.scalar(sa.select(sa.func.count(Broadcast.id)))
        assert count == 1
        msg_count = await db_session.scalar(
            sa.select(sa.func.count(Message.id)).where(Message.template_payload.is_not(None))
        )
        assert msg_count == 2


async def test_customer_reused_across_broadcasts(client, world, db_session) -> None:
    for _ in range(2):
        resp = await client.post(
            "/v1/embed/broadcasts", json=_payload(), headers=world["headers"]
        )
        assert resp.status_code == 202

    await db_session.rollback()  # clear any autobegin state from fixtures
    async with db_session.begin():
        await _set_tenant(db_session, world["tenant_id"])
        customers = (await db_session.execute(sa.select(Customer.id))).scalars().all()
        assert len(customers) == 2  # one per phone, NOT one per broadcast


async def test_broadcast_status_aggregates_message_state(client, world, db_session) -> None:
    resp = await client.post("/v1/embed/broadcasts", json=_payload(), headers=world["headers"])
    broadcast_id = resp.json()["broadcast_id"]

    status_resp = await client.get(
        f"/v1/embed/broadcasts/{broadcast_id}", headers=world["headers"]
    )
    assert status_resp.status_code == 200
    body = status_resp.json()
    assert body["counts"] == {"pending": 2}
    assert {r["status"] for r in body["recipients"]} == {"pending"}

    # Simulate the dispatcher sending one and Meta failing the other.
    await db_session.rollback()  # clear any autobegin state from fixtures
    async with db_session.begin():
        await _set_tenant(db_session, world["tenant_id"])
        rows = (
            (
                await db_session.execute(
                    sa.select(BroadcastRecipient).where(
                        BroadcastRecipient.broadcast_id == uuid.UUID(broadcast_id)
                    )
                )
            )
            .scalars()
            .all()
        )
        await db_session.execute(
            sa.update(Message).where(Message.id == rows[0].message_id).values(status=MessageStatus.SENT)
        )
        await db_session.execute(
            sa.update(Message)
            .where(Message.id == rows[1].message_id)
            .values(status=MessageStatus.FAILED, failure_code="opted_out")
        )

    body = (
        await client.get(f"/v1/embed/broadcasts/{broadcast_id}", headers=world["headers"])
    ).json()
    assert body["counts"] == {"sent": 1, "failed": 1}
    failed = next(r for r in body["recipients"] if r["status"] == "failed")
    assert failed["reason"] == "opted_out"


async def test_broadcast_of_other_tenant_is_404(client, world, db_session) -> None:
    resp = await client.post("/v1/embed/broadcasts", json=_payload(), headers=world["headers"])
    broadcast_id = resp.json()["broadcast_id"]

    # Second tenant + partner with its own token tries to read it.
    other_tenant, other_partner, other_key = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    generated = generate_api_key()
    db_session.add(
        Tenant(id=other_tenant, name="O", slug=f"ot-{other_tenant.hex[:6]}", plan=TenantPlan.PRO)
    )
    db_session.add(Partner(id=other_partner, name="OP", slug=f"op-{other_partner.hex[:6]}"))
    # No ORM relationships → flush so the FK targets exist before the
    # mapping/key rows insert.
    await db_session.flush()
    db_session.add(
        PartnerApiKey(
            id=other_key,
            partner_id=other_partner,
            prefix_snippet=generated.prefix_snippet,
            key_hash=generated.key_hash,
        )
    )
    db_session.add(
        PartnerTenant(
            partner_id=other_partner, external_client_ref="oc", tenant_id=other_tenant
        )
    )
    await db_session.commit()
    token, _, _ = mint_widget_token(
        tenant_id=other_tenant,
        partner_id=other_partner,
        key_id=other_key,
        scope=["widget:send"],
        allowed_origins=[],
    )
    resp = await client.get(
        f"/v1/embed/broadcasts/{broadcast_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
