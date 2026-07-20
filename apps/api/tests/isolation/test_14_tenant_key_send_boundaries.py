"""Isolation guarantee — tenant-scoped send keys (direct message API).

A tenant-scoped key (``api_keys.tenant_id`` set, scope ``messages_send``)
is the credential a direct client automates against. The frontier here is
simpler than the partner one — the tenant is baked into the key, not
resolved from request input — but it must hold under adversarial input:

- Client A's key cannot queue a message that lands in tenant B, no matter
  what it puts in the body (there is no tenant field to attack).
- Client A's key cannot read tenant B's message status by id.
- A key confined to a tenant cannot carry ``provision`` (DB CHECK), so it
  can never widen itself into the partner-provisioning surface.
"""

from __future__ import annotations

import uuid

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
)
from nexus_api.services.whatsapp_templates import TemplateOut

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]


_TEMPLATE = TemplateOut(
    id="t1",
    name="newair_instalacion_recordatorio",
    language="es",
    category="MARKETING",
    status="APPROVED",
    components=[{"type": "BODY", "text": "Hola {{nombre}}, el {{fecha}}."}],
)


@pytest.fixture(autouse=True)
def _stub_templates(monkeypatch):
    async def _fake_fetch(_session):
        return [_TEMPLATE], "waba-1"

    monkeypatch.setattr("nexus_api.services.broadcasts.fetch_templates", _fake_fetch)


async def _seed_tenant_with_send_key(db_session, *, label: str) -> dict:
    """Tenant + active WhatsApp channel + tenant-scoped send key."""
    tenant_id, partner_id = uuid.uuid4(), uuid.uuid4()
    generated = generate_api_key()
    db_session.add(
        Tenant(
            id=tenant_id,
            name=f"T{label}",
            slug=f"t{label}-{tenant_id.hex[:6]}",
            plan=TenantPlan.PRO,
        )
    )
    await db_session.flush()
    channel = Channel(
        tenant_id=tenant_id,
        type=ChannelType.WHATSAPP,
        provider="meta",
        provider_identifier=f"+5622222{label}000"[:15],
        status=ChannelStatus.ACTIVE,
    )
    db_session.add(channel)
    db_session.add(Partner(id=partner_id, name=f"P{label}", slug=f"p{label}-{partner_id.hex[:6]}"))
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
        "channel_id": channel.id,
        "key": generated.plaintext,
    }


@pytest_asyncio.fixture
async def two_clients(db_session):
    a = await _seed_tenant_with_send_key(db_session, label="a")
    b = await _seed_tenant_with_send_key(db_session, label="b")
    return {"a": a, "b": b}


def _auth(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def _payload(**overrides):
    payload = {
        "to": "+56912345678",
        "template_name": "newair_instalacion_recordatorio",
        "language": "es",
        "variables": {"nombre": "Ana", "fecha": "15/01/2026"},
    }
    payload.update(overrides)
    return payload


async def _set_tenant(session, tenant_id: uuid.UUID) -> None:
    await session.execute(
        sa.text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
    )
    await session.execute(sa.text("SET LOCAL ROLE nexus_app"))


async def test_send_lands_in_own_tenant_only(client, two_clients, db_session) -> None:
    """A's key queues into A. The message and its customer exist under A
    and are invisible under B — there is no request field that could have
    aimed it elsewhere."""
    resp = await client.post(
        "/v1/messages/template", json=_payload(), headers=_auth(two_clients["a"]["key"])
    )
    assert resp.status_code == 202, resp.text
    message_id = uuid.UUID(resp.json()["message_id"])

    await db_session.rollback()
    async with db_session.begin():
        await _set_tenant(db_session, two_clients["a"]["tenant_id"])
        assert (
            await db_session.scalar(sa.select(Message.id).where(Message.id == message_id))
        ) == message_id

    async with db_session.begin():
        await _set_tenant(db_session, two_clients["b"]["tenant_id"])
        assert (
            await db_session.scalar(sa.select(Message.id).where(Message.id == message_id))
        ) is None
        # The customer row is A's too — B sees an empty table.
        assert (await db_session.scalar(sa.select(sa.func.count()).select_from(Customer))) == 0


async def test_client_cannot_read_other_clients_message(client, two_clients) -> None:
    """B queues a message; A asks for it by id → 404, not 200. RLS filters
    the row out before the handler runs, so 'not found' and 'not yours'
    are indistinguishable — as they must be, or the id itself leaks."""
    sent = await client.post(
        "/v1/messages/template", json=_payload(), headers=_auth(two_clients["b"]["key"])
    )
    assert sent.status_code == 202, sent.text
    b_message_id = sent.json()["message_id"]

    resp = await client.get(f"/v1/messages/{b_message_id}", headers=_auth(two_clients["a"]["key"]))
    assert resp.status_code == 404

    # Sanity: B can read its own.
    own = await client.get(f"/v1/messages/{b_message_id}", headers=_auth(two_clients["b"]["key"]))
    assert own.status_code == 200


async def test_shared_idempotency_key_does_not_collide_across_tenants(client, two_clients) -> None:
    """The same key string from two clients must both send — the unique
    index is (tenant_id, idempotency_key), not global. Otherwise client B
    could suppress client A's message by guessing its key."""
    payload = _payload(idempotency_key="fila-15")

    a = await client.post(
        "/v1/messages/template", json=payload, headers=_auth(two_clients["a"]["key"])
    )
    b = await client.post(
        "/v1/messages/template", json=payload, headers=_auth(two_clients["b"]["key"])
    )
    assert a.status_code == 202 and b.status_code == 202
    assert a.json()["duplicate"] is False
    assert b.json()["duplicate"] is False
    assert a.json()["message_id"] != b.json()["message_id"]


async def test_tenant_key_with_provision_is_rejected_by_db(db_session, two_clients) -> None:
    """The CHECK constraint, not application code, forbids a tenant-scoped
    key from holding ``provision``. Belt-and-suspenders against a future
    refactor that trusts the request to set scopes."""
    generated = generate_api_key()
    await db_session.rollback()
    with pytest.raises(sa.exc.IntegrityError):
        async with db_session.begin():
            db_session.add(
                PartnerApiKey(
                    partner_id=uuid.uuid4(),  # FK will not even be reached
                    tenant_id=two_clients["a"]["tenant_id"],
                    prefix_snippet=generated.prefix_snippet,
                    key_hash=generated.key_hash,
                    scopes=[ApiKeyScope.PROVISION.value, ApiKeyScope.MESSAGES_SEND.value],
                )
            )
