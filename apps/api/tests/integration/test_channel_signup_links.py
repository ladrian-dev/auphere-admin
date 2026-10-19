"""Spec 040 — the owner connects WhatsApp from a link on their own device.

Only Meta's client is faked; the link, the channel upsert, the connector row
and the consumption run against the database.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from nexus_api.db.models import Channel, ChannelSignupLink, TenantConnector
from nexus_api.services import meta_signup_service
from nexus_api.services.connectors.seed_loader import load_all_seeds
from nexus_api.services.connectors.seed_runner import apply_seeds
from tests.conftest import console_headers
from tests.unit.test_endpoint_console_whatsapp import _FakeMeta

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _operator(db_session) -> str:
    from nexus_api.services import operator_identity

    account = await operator_identity.create_account(
        db_session, email=f"op-{uuid.uuid4().hex[:6]}@auphere.test", password="x" * 16, role="admin"
    )
    await db_session.commit()
    return str(account.id)


def _svc() -> dict[str, str]:
    """The console server's service credential: a fresh one per call (replay rule)."""
    return console_headers(user_id="console-bff", partner_id=None, service=True)


def _token(url: str) -> str:
    return url.rsplit("/", 1)[-1]


async def test_operator_link_connects_on_the_owners_device(
    client, console_world, admin_headers, db_session, monkeypatch
) -> None:
    await apply_seeds(db_session, load_all_seeds())
    await db_session.commit()
    a = console_world["a"]
    op = await _operator(db_session)
    made = await client.post(
        f"/admin/tenants/{a['tenant_id']}/channels/whatsapp/signup-link",
        headers={**admin_headers, "X-Operator-Id": op},
        json={"mode": "coexistence"},
    )
    assert made.status_code == 201, made.text
    url = made.json()["url"]
    assert "/connect/whatsapp/" in url
    token = _token(url)

    # The token itself is never stored.
    stored = (await db_session.execute(sa.select(ChannelSignupLink.token_hash))).scalars().all()
    assert token not in stored

    info = await client.get(f"/console/channel-signup/{token}", headers=_svc())
    assert info.status_code == 200, info.text
    body = info.json()
    assert body["state"] == "valid"
    assert body["mode"] == "coexistence"
    assert body["business_name"]
    assert body["meta_config_id"]

    number = f"+5691{uuid.uuid4().int % 10**7:07d}"
    fake = _FakeMeta(number)
    monkeypatch.setattr(meta_signup_service, "build_meta_client", lambda: fake)
    done = await client.post(
        f"/console/channel-signup/{token}",
        headers=_svc(),
        json={"code": "abc", "waba_id": "W-link"},
    )
    assert done.status_code == 201, done.text
    channel_id = uuid.UUID(done.json()["channel_id"])

    db_session.expire_all()
    channel = await db_session.get(Channel, channel_id)
    assert channel is not None and channel.tenant_id == a["tenant_id"]
    installed = (
        (
            await db_session.execute(
                sa.select(TenantConnector).where(TenantConnector.tenant_id == a["tenant_id"])
            )
        )
        .scalars()
        .all()
    )
    assert installed, "the whatsapp_meta connector row is created too"

    # Single use.
    again = await client.post(
        f"/console/channel-signup/{token}",
        headers=_svc(),
        json={"code": "abc", "waba_id": "W-link"},
    )
    assert again.status_code == 410
    assert again.json()["detail"]["code"] == "link_used"
    assert (await client.get(f"/console/channel-signup/{token}", headers=_svc())).json() == {
        "state": "used",
        "business_name": None,
        "mode": None,
        "expires_at": None,
        "meta_app_id": None,
        "meta_config_id": None,
        "meta_graph_version": None,
    }


async def test_unknown_expired_and_revoked_links_do_nothing(
    client, console_world, admin_headers, db_session
) -> None:
    a = console_world["a"]
    assert (await client.get("/console/channel-signup/nope", headers=_svc())).json()[
        "state"
    ] == "unknown"
    r = await client.post(
        "/console/channel-signup/nope", headers=_svc(), json={"code": "x", "waba_id": "w"}
    )
    assert r.status_code == 404

    op = await _operator(db_session)
    headers = {**admin_headers, "X-Operator-Id": op}
    made = await client.post(
        f"/admin/tenants/{a['tenant_id']}/channels/whatsapp/signup-link", headers=headers, json={}
    )
    token = _token(made.json()["url"])
    link_id = made.json()["id"]

    await db_session.execute(
        sa.update(ChannelSignupLink)
        .where(ChannelSignupLink.id == uuid.UUID(link_id))
        .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    await db_session.commit()
    assert (await client.get(f"/console/channel-signup/{token}", headers=_svc())).json()[
        "state"
    ] == "expired"

    fresh = await client.post(
        f"/admin/tenants/{a['tenant_id']}/channels/whatsapp/signup-link", headers=headers, json={}
    )
    revoked = await client.delete(
        f"/admin/tenants/{a['tenant_id']}/channels/whatsapp/signup-links/{fresh.json()['id']}",
        headers=headers,
    )
    assert revoked.status_code == 204
    gone = await client.get(
        f"/console/channel-signup/{_token(fresh.json()['url'])}", headers=_svc()
    )
    assert gone.json()["state"] == "revoked"


async def test_a_partner_member_mints_a_link_for_their_client(client, console_world) -> None:
    a = console_world["a"]
    r = await client.post(
        f"/console/clients/{a['ref']}/channels/whatsapp/signup-link",
        headers=a["headers"](),
        json={"mode": "cloud_api"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["mode"] == "cloud_api"
    assert "/connect/whatsapp/" in r.json()["url"]


async def test_the_owner_route_needs_the_console_service_credential(client) -> None:
    assert (await client.get("/console/channel-signup/anything")).status_code in (401, 403)
