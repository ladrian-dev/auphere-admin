"""Spec 050 (3.2): the operator rotates a number's two-step PIN.

The new PIN goes to Meta, is stored encrypted on the channel (and on the
tenant row when it is the same number), is audited, and is never in the
response. A coexistence number and another tenant's channel are refused.
"""

from __future__ import annotations

import json

import pytest
import respx
from nexus_channels.whatsapp_meta.credentials import MetaCredentials
from nexus_channels.whatsapp_meta.meta_client import META_GRAPH_BASE_URL
from sqlalchemy import select

from nexus_api.db.models import AuditLog, Channel, TenantCredentials

pytestmark = pytest.mark.asyncio


async def _connect(client, admin_headers, tenant_id) -> str:
    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        mock.post("/PN_PIN/register").respond(200, json={"success": True})
        mock.post("/WABA_PIN/subscribed_apps").respond(200, json={"success": True})
        mock.get("/PN_PIN").respond(200, json={"display_phone_number": "56977778888"})
        r = await client.post(
            f"/admin/tenants/{tenant_id}/integrations/meta/connect-owned",
            json={
                "system_user_token": "EAA-system-user-token-for-pin-tests",
                "waba_id": "WABA_PIN",
                "phone_number_id": "PN_PIN",
            },
            headers=admin_headers,
        )
    assert r.status_code == 201, r.text
    return r.json()["channel_id"]


async def test_rotating_sends_stores_and_audits_the_new_pin(
    client, admin_headers, seed_tenants, db_session
):
    tenant_id = seed_tenants["a"]
    channel_id = await _connect(client, admin_headers, tenant_id)

    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        route = mock.post("/PN_PIN").respond(200, json={"success": True})
        r = await client.post(
            f"/admin/tenants/{tenant_id}/channels/{channel_id}/two-step-pin",
            headers=admin_headers,
        )
    assert r.status_code == 200, r.text
    pin = json.loads(route.calls.last.request.content)["pin"]
    assert len(pin) == 6 and pin.isdigit()
    assert set(r.json()) == {"status", "channel_id"}  # the PIN never leaves

    chan = await db_session.scalar(select(Channel).where(Channel.tenant_id == tenant_id))
    assert chan is not None and chan.config_encrypted is not None
    assert MetaCredentials.from_payload(chan.config_encrypted).two_step_pin == pin
    cred = await db_session.scalar(
        select(TenantCredentials).where(TenantCredentials.tenant_id == tenant_id)
    )
    assert cred is not None
    assert MetaCredentials.from_payload(cred.encrypted_payload).two_step_pin == pin

    audit = await db_session.scalar(
        select(AuditLog).where(
            AuditLog.tenant_id == tenant_id, AuditLog.action == "channel.whatsapp.pin_rotated"
        )
    )
    assert audit is not None and pin not in json.dumps(audit.after_json)


async def test_meta_refusing_keeps_the_old_pin(client, admin_headers, seed_tenants, db_session):
    tenant_id = seed_tenants["a"]
    channel_id = await _connect(client, admin_headers, tenant_id)
    chan = await db_session.scalar(select(Channel).where(Channel.tenant_id == tenant_id))
    assert chan is not None and chan.config_encrypted is not None
    before = MetaCredentials.from_payload(chan.config_encrypted).two_step_pin

    async with respx.mock(base_url=META_GRAPH_BASE_URL) as mock:
        mock.post("/PN_PIN").respond(400, json={"error": {"message": "bad", "code": 100}})
        r = await client.post(
            f"/admin/tenants/{tenant_id}/channels/{channel_id}/two-step-pin",
            headers=admin_headers,
        )
    assert r.status_code == 502
    await db_session.refresh(chan)
    assert chan.config_encrypted is not None
    assert MetaCredentials.from_payload(chan.config_encrypted).two_step_pin == before


async def test_a_coexistence_number_is_refused(client, admin_headers, seed_tenants, db_session):
    tenant_id = seed_tenants["a"]
    channel_id = await _connect(client, admin_headers, tenant_id)
    chan = await db_session.scalar(select(Channel).where(Channel.tenant_id == tenant_id))
    assert chan is not None
    chan.config = {**chan.config, "mode": "coexistence"}
    await db_session.commit()

    r = await client.post(
        f"/admin/tenants/{tenant_id}/channels/{channel_id}/two-step-pin", headers=admin_headers
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "coexistence_number"


async def test_another_tenants_channel_is_not_found(client, admin_headers, seed_tenants):
    channel_id = await _connect(client, admin_headers, seed_tenants["a"])
    r = await client.post(
        f"/admin/tenants/{seed_tenants['b']}/channels/{channel_id}/two-step-pin",
        headers=admin_headers,
    )
    assert r.status_code == 404


async def test_rotating_requires_the_admin_token(client, seed_tenants):
    import uuid

    r = await client.post(
        f"/admin/tenants/{seed_tenants['a']}/channels/{uuid.uuid4()}/two-step-pin"
    )
    assert r.status_code == 401
