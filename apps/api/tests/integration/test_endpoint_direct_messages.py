"""``POST /v1/messages/template`` + ``GET /v1/messages/{id}`` E2E.

The surface a client automates against (n8n, cron) with a tenant-scoped
API key. Template resolution is monkeypatched — Meta Graph is not
reachable in tests — everything else is real: key auth, RLS scoping from
the key's tenant_id, customer/conversation upserts, opt-out pre-flight,
the pending ``messages`` row, and idempotent replay.

The cross-tenant case lives in ``tests/isolation`` — this file covers
the contract, that one covers the boundary.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
import sqlalchemy as sa

from nexus_api.core.partner_keys import generate_api_key
from nexus_api.db.models import (
    ApiKeyScope,
    Channel,
    ChannelStatus,
    ChannelType,
    Customer,
    Message,
    Partner,
    PartnerApiKey,
    Tenant,
    TenantPlan,
    WhatsAppOptOut,
)
from nexus_api.services.whatsapp_templates import TemplateOut

pytestmark = pytest.mark.asyncio


async def _set_tenant(session, tenant_id: uuid.UUID) -> None:
    await session.execute(
        sa.text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
    )
    await session.execute(sa.text("SET LOCAL ROLE nexus_app"))


_TEMPLATE = TemplateOut(
    id="t1",
    name="newair_instalacion_recordatorio",
    language="es",
    category="MARKETING",
    status="APPROVED",
    components=[
        {
            "type": "BODY",
            "text": "Hola {{nombre}}, el día {{fecha}} instalamos tu equipo.",
        }
    ],
)

_PAUSED_TEMPLATE = TemplateOut(
    id="t2",
    name="pausada",
    language="es",
    category="MARKETING",
    status="PAUSED",
    components=[{"type": "BODY", "text": "Hola {{nombre}}"}],
)


@pytest.fixture(autouse=True)
def _stub_templates(monkeypatch):
    async def _fake_fetch(_session):
        return [_TEMPLATE, _PAUSED_TEMPLATE], "waba-1"

    monkeypatch.setattr("nexus_api.services.broadcasts.fetch_templates", _fake_fetch)


@pytest_asyncio.fixture
async def world(db_session):
    """A tenant with an active WhatsApp channel and a tenant-scoped key."""
    tenant_id, partner_id = uuid.uuid4(), uuid.uuid4()
    generated = generate_api_key()
    db_session.add(
        Tenant(id=tenant_id, name="NewAir", slug=f"na-{tenant_id.hex[:6]}", plan=TenantPlan.PRO)
    )
    await db_session.flush()
    channel = Channel(
        tenant_id=tenant_id,
        type=ChannelType.WHATSAPP,
        provider="meta",
        provider_identifier="+56222222222",
        status=ChannelStatus.ACTIVE,
    )
    db_session.add(channel)
    db_session.add(Partner(id=partner_id, name="P", slug=f"pp-{partner_id.hex[:6]}"))
    db_session.add(
        PartnerApiKey(
            partner_id=partner_id,
            tenant_id=tenant_id,
            prefix_snippet=generated.prefix_snippet,
            key_hash=generated.key_hash,
            scopes=[ApiKeyScope.MESSAGES_SEND.value],
        )
    )
    await db_session.commit()
    await db_session.refresh(channel)
    return {
        "tenant_id": tenant_id,
        "partner_id": partner_id,
        "channel_id": channel.id,
        "headers": {"Authorization": f"Bearer {generated.plaintext}"},
    }


def _payload(**overrides):
    payload = {
        "to": "+56912345678",
        "template_name": "newair_instalacion_recordatorio",
        "language": "es",
        "variables": {"nombre": "Juan Pérez", "fecha": "15/01/2026"},
    }
    payload.update(overrides)
    return payload


async def test_send_queues_pending_template_message(client, world, db_session) -> None:
    resp = await client.post("/v1/messages/template", json=_payload(), headers=world["headers"])
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert body["duplicate"] is False
    assert body["to"] == "+56912345678"

    await db_session.rollback()
    async with db_session.begin():
        await _set_tenant(db_session, world["tenant_id"])
        message = (
            await db_session.execute(
                sa.select(Message).where(Message.id == uuid.UUID(body["message_id"]))
            )
        ).scalar_one()
        assert message.status.value == "pending"
        assert message.actor_kind == "system"
        assert message.template_payload["name"] == "newair_instalacion_recordatorio"
        assert message.template_payload["params"]["body"] == {
            "nombre": "Juan Pérez",
            "fecha": "15/01/2026",
        }
        # Meta's from-format: digits WITHOUT '+', so inbound webhooks
        # resolve the same customer instead of forking history.
        identifier = (await db_session.execute(sa.select(Customer.identifier))).scalar_one()
        assert identifier == "56912345678"


async def test_phone_is_normalised_to_e164(client, world) -> None:
    resp = await client.post(
        "/v1/messages/template",
        json=_payload(to="+56 9 1234-5678"),
        headers=world["headers"],
    )
    assert resp.status_code == 202, resp.text
    assert resp.json()["to"] == "+56912345678"


async def test_invalid_phone_is_422(client, world) -> None:
    resp = await client.post(
        "/v1/messages/template", json=_payload(to="no-soy-un-telefono"), headers=world["headers"]
    )
    assert resp.status_code == 422
    assert "invalid_phone" in resp.text


async def test_missing_variable_is_422_and_names_it(client, world) -> None:
    resp = await client.post(
        "/v1/messages/template",
        json=_payload(variables={"nombre": "Juan"}),
        headers=world["headers"],
    )
    assert resp.status_code == 422
    # The caller must be able to fix this without reading our source.
    assert "missing_variables" in resp.text
    assert "fecha" in resp.text


async def test_unexpected_variable_is_422(client, world) -> None:
    """A typo'd key would otherwise send with an unfilled placeholder."""
    resp = await client.post(
        "/v1/messages/template",
        json=_payload(variables={"nombre": "Juan", "fecha": "15/01/2026", "nomre": "x"}),
        headers=world["headers"],
    )
    assert resp.status_code == 422
    assert "unexpected_variables" in resp.text
    assert "nomre" in resp.text


async def test_unknown_template_is_422(client, world) -> None:
    resp = await client.post(
        "/v1/messages/template",
        json=_payload(template_name="no_existe"),
        headers=world["headers"],
    )
    assert resp.status_code == 422
    assert "does not exist" in resp.text


async def test_unapproved_template_is_422(client, world) -> None:
    resp = await client.post(
        "/v1/messages/template",
        json=_payload(template_name="pausada", variables={"nombre": "Juan"}),
        headers=world["headers"],
    )
    assert resp.status_code == 422
    assert "PAUSED" in resp.text


async def test_opted_out_recipient_is_409(client, world, db_session) -> None:
    await db_session.rollback()
    async with db_session.begin():
        await _set_tenant(db_session, world["tenant_id"])
        db_session.add(
            WhatsAppOptOut(
                tenant_id=world["tenant_id"],
                channel_id=world["channel_id"],
                recipient_phone="56912345678",
                reason="keyword_stop",
                opted_out_at=datetime.now(UTC),
            )
        )

    resp = await client.post("/v1/messages/template", json=_payload(), headers=world["headers"])
    assert resp.status_code == 409
    assert "opted_out" in resp.text


async def test_idempotency_key_replays_instead_of_resending(client, world, db_session) -> None:
    payload = _payload(idempotency_key="fila-15-2026-07-20")

    first = await client.post("/v1/messages/template", json=payload, headers=world["headers"])
    assert first.status_code == 202, first.text
    assert first.json()["duplicate"] is False

    second = await client.post("/v1/messages/template", json=payload, headers=world["headers"])
    assert second.status_code == 202, second.text
    assert second.json()["duplicate"] is True
    assert second.json()["message_id"] == first.json()["message_id"]

    # The point of the whole mechanism: one WhatsApp, not two.
    await db_session.rollback()
    async with db_session.begin():
        await _set_tenant(db_session, world["tenant_id"])
        count = await db_session.scalar(
            sa.select(sa.func.count())
            .select_from(Message)
            .where(Message.template_payload.is_not(None))
        )
        assert count == 1


async def test_replay_of_a_failed_send_requeues_instead_of_answering_duplicate(
    client, world, db_session
) -> None:
    """The New Air symptom: ``duplicate=true`` on a message nobody received.

    The first send is queued and then fails at the dispatcher (Meta
    rejects the number, the template is paused, the token is dead — the
    reason does not matter, the row ends ``failed``). The automation runs
    again the next day with the same key. Answering ``duplicate`` there
    tells the caller the message is handled and queues nothing, so the
    recipient never hears from us and the spreadsheet row gets marked as
    sent. The retry has to re-drive the same row instead.
    """
    payload = _payload(idempotency_key="newair-instalacion-fila-15")

    first = await client.post("/v1/messages/template", json=payload, headers=world["headers"])
    assert first.status_code == 202, first.text
    message_id = uuid.UUID(first.json()["message_id"])

    # The dispatcher's terminal state for a rejected recipient.
    await db_session.rollback()
    async with db_session.begin():
        await _set_tenant(db_session, world["tenant_id"])
        await db_session.execute(
            sa.update(Message)
            .where(Message.id == message_id)
            .values(
                status="failed",
                attempts=3,
                failed_at=datetime.now(UTC),
                failure_code="131026",
                last_error="MetaAPIError: recipient unable to receive message",
            )
        )

    second = await client.post("/v1/messages/template", json=payload, headers=world["headers"])
    assert second.status_code == 202, second.text
    body = second.json()
    assert body["duplicate"] is False, "a failed send must not be reported as a duplicate"
    assert body["status"] == "pending"
    assert uuid.UUID(body["message_id"]) == message_id, "same row, re-driven"

    await db_session.rollback()
    async with db_session.begin():
        await _set_tenant(db_session, world["tenant_id"])
        message = (
            await db_session.execute(sa.select(Message).where(Message.id == message_id))
        ).scalar_one()
        assert message.status.value == "pending"
        # A fresh retry budget: inheriting attempts=3 would make the
        # dispatcher park the row on its very first failure.
        assert message.attempts == 0
        assert message.failure_code is None
        assert message.failed_at is None
        assert message.last_error is None

        # Still exactly one row — the unique index on (tenant_id,
        # idempotency_key) is intact, we re-drove rather than duplicated.
        count = await db_session.scalar(
            sa.select(sa.func.count())
            .select_from(Message)
            .where(Message.idempotency_key == "newair-instalacion-fila-15")
        )
        assert count == 1


async def test_delivered_send_still_replays_as_duplicate(client, world, db_session) -> None:
    """The guard the test above must not break: a send that actually
    reached the customer stays a duplicate on retry, forever."""
    payload = _payload(idempotency_key="newair-mantencion-fila-8")

    first = await client.post("/v1/messages/template", json=payload, headers=world["headers"])
    message_id = uuid.UUID(first.json()["message_id"])

    await db_session.rollback()
    async with db_session.begin():
        await _set_tenant(db_session, world["tenant_id"])
        await db_session.execute(
            sa.update(Message)
            .where(Message.id == message_id)
            .values(status="delivered", delivered_at=datetime.now(UTC))
        )

    second = await client.post("/v1/messages/template", json=payload, headers=world["headers"])
    assert second.status_code == 202
    assert second.json()["duplicate"] is True
    assert second.json()["status"] == "delivered"


async def test_key_collision_between_two_different_rows_is_logged(client, world) -> None:
    """Two different messages under one key: the second is swallowed.

    This is the caller's bug, not ours — a key built from
    ``tipo-telefono-fecha`` collides whenever two spreadsheet rows share
    those fields. We cannot deliver both under one key, but we must not
    lose it silently, so the drop is a WARNING with both payloads.
    """
    first = await client.post(
        "/v1/messages/template",
        json=_payload(
            idempotency_key="newair-2026-08-07",
            variables={
                "nombre": "Juan Pérez",
                "fecha": "15/01/2026",
            },
        ),
        headers=world["headers"],
    )
    assert first.status_code == 202

    second = await client.post(
        "/v1/messages/template",
        json=_payload(
            idempotency_key="newair-2026-08-07",
            variables={
                "nombre": "Marta Silva",
                "fecha": "20/01/2026",
            },
        ),
        headers=world["headers"],
    )
    assert second.status_code == 202
    # Same key, different customer entirely — reported as a duplicate and
    # never sent. The response cannot express this; the log must.
    assert second.json()["duplicate"] is True
    assert second.json()["message_id"] == first.json()["message_id"]


async def test_status_endpoint_returns_delivery_state(client, world) -> None:
    sent = await client.post("/v1/messages/template", json=_payload(), headers=world["headers"])
    message_id = sent.json()["message_id"]

    resp = await client.get(f"/v1/messages/{message_id}", headers=world["headers"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["message_id"] == message_id
    assert body["status"] == "pending"
    assert body["delivered_at"] is None
    assert body["failure_code"] is None


async def test_unknown_message_id_is_404(client, world) -> None:
    resp = await client.get(f"/v1/messages/{uuid.uuid4()}", headers=world["headers"])
    assert resp.status_code == 404


async def test_partner_key_without_tenant_is_403(client, world, db_session) -> None:
    """A valid key on the wrong surface: 403, not 401 — retrying with the
    same credential can never succeed."""
    generated = generate_api_key()
    await db_session.rollback()
    async with db_session.begin():
        db_session.add(
            PartnerApiKey(
                partner_id=world["partner_id"],
                prefix_snippet=generated.prefix_snippet,
                key_hash=generated.key_hash,
                scopes=[ApiKeyScope.MESSAGES_SEND.value],
            )
        )

    resp = await client.post(
        "/v1/messages/template",
        json=_payload(),
        headers={"Authorization": f"Bearer {generated.plaintext}"},
    )
    assert resp.status_code == 403
    assert "tenant-scoped" in resp.text


async def test_key_without_messages_send_scope_is_403(client, world, db_session) -> None:
    generated = generate_api_key()
    await db_session.rollback()
    async with db_session.begin():
        db_session.add(
            PartnerApiKey(
                partner_id=world["partner_id"],
                tenant_id=world["tenant_id"],
                prefix_snippet=generated.prefix_snippet,
                key_hash=generated.key_hash,
                scopes=[ApiKeyScope.WIDGET_SESSIONS.value],
            )
        )

    resp = await client.post(
        "/v1/messages/template",
        json=_payload(),
        headers={"Authorization": f"Bearer {generated.plaintext}"},
    )
    assert resp.status_code == 403
    assert "scope" in resp.text


async def test_missing_bearer_is_401(client) -> None:
    resp = await client.post("/v1/messages/template", json=_payload())
    assert resp.status_code == 401
