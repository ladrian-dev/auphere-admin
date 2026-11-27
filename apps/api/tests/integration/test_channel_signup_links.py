"""Spec 040 — the owner connects WhatsApp from a link on their own device.

Only Meta's client is faked; the link, the channel upsert, the connector row
and the consumption run against the database.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import HTTPException

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AuditLog,
    Channel,
    ChannelSignupLink,
    ChannelStatus,
    ChannelType,
    Partner,
    TenantConnector,
)
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
    assert body["channel"] == "whatsapp"
    assert body["mode"] == "coexistence"
    assert body["business_name"]
    assert body["meta_config_id"]
    assert body["meta_signup_version"] == "v4"  # spec 050: v5 waits for staging

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
        "channel": None,  # spec 085: a dead link does not say which channel it was
        "mode": None,
        "expires_at": None,
        "meta_app_id": None,
        "meta_config_id": None,
        "meta_graph_version": None,
        "meta_signup_version": None,
        "meta_page_config_id": None,
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


async def test_one_live_link_per_client_and_the_partner_revokes_it(
    client, console_world, db_session
) -> None:
    """Owner, 2026-10-20: every «Enviar enlace» left another valid link, and
    the console could neither see nor revoke them."""
    a, b = console_world["a"], console_world["b"]
    base = f"/console/clients/{a['ref']}/channels/whatsapp"
    first = await client.post(f"{base}/signup-link", headers=a["headers"](), json={})
    second = await client.post(f"{base}/signup-link", headers=a["headers"](), json={})
    assert first.status_code == second.status_code == 201

    # The first no longer works: the new one replaced it.
    old = await client.get(f"/console/channel-signup/{_token(first.json()['url'])}", headers=_svc())
    assert old.json()["state"] == "revoked"
    new = await client.get(
        f"/console/channel-signup/{_token(second.json()['url'])}", headers=_svc()
    )
    assert new.json()["state"] == "valid"

    listed = await client.get(f"{base}/signup-links", headers=a["headers"]())
    assert listed.status_code == 200, listed.text
    states = [r["state"] for r in listed.json()]
    assert states == ["valid", "revoked"]
    assert "url" not in listed.json()[0]  # the token is never shown again
    live_id = listed.json()[0]["id"]

    # Another partner cannot revoke it, nor see that it exists.
    other = await client.delete(
        f"/console/clients/{b['ref']}/channels/whatsapp/signup-links/{live_id}",
        headers=b["headers"](),
    )
    assert other.status_code == 404

    gone = await client.delete(f"{base}/signup-links/{live_id}", headers=a["headers"]())
    assert gone.status_code == 204
    again = await client.get(
        f"/console/channel-signup/{_token(second.json()['url'])}", headers=_svc()
    )
    assert again.json()["state"] == "revoked"
    # Revoking twice is harmless.
    twice = await client.delete(f"{base}/signup-links/{live_id}", headers=a["headers"]())
    assert twice.status_code == 204

    rows = (
        (
            await db_session.execute(
                sa.select(AuditLog).where(AuditLog.action == "channel.signup_link.revoked")
            )
        )
        .scalars()
        .all()
    )
    assert sorted(r.after_json["reason"] for r in rows) == ["replaced", "revoked"]


# --- La cuota del enlace es la de la consola ------------------------------------
# Bug `el-enlace-cuenta-instagram-como-numero`: el enlace contaba Instagram y
# Messenger como números (la consola no, spec 049) y no dejaba volver a
# autorizar un número del cliente (la consola sí, spec 076, 4.3). El alta se
# sustituye por una que responde 418: llegar a ella es haber pasado la cuota.


@pytest.fixture
def link_reaches_meta(monkeypatch: pytest.MonkeyPatch) -> None:
    async def reached(**_: Any) -> Any:
        raise HTTPException(status_code=418, detail="reached the signup")

    monkeypatch.setattr("nexus_api.services.channel_signup_links.complete_meta_signup", reached)


async def _one_number_allowed_and(db_session: Any, w: dict[str, Any], channel: Channel) -> None:
    await db_session.execute(
        sa.update(Partner).where(Partner.id == w["partner_id"]).values(max_channels_per_client=1)
    )
    await db_session.commit()
    async with get_sessionmaker()() as s, tenant_scoped_session(s, w["tenant_id"]):
        s.add(channel)
        await s.commit()


async def _link_signup(client: Any, w: dict[str, Any], phone_number_id: str) -> Any:
    made = await client.post(
        f"/console/clients/{w['ref']}/channels/whatsapp/signup-link",
        headers=w["headers"](),
        json={"mode": "coexistence"},
    )
    assert made.status_code == 201, made.text
    return await client.post(
        f"/console/channel-signup/{_token(made.json()['url'])}",
        headers=_svc(),
        json={"code": "c", "waba_id": "WABA1", "phone_number_id": phone_number_id},
    )


def _number(w: dict[str, Any], phone_number_id: str) -> Channel:
    return Channel(
        id=uuid.uuid4(),
        tenant_id=w["tenant_id"],
        type=ChannelType.WHATSAPP,
        provider="meta",
        provider_identifier="+56999990001",
        status=ChannelStatus.ACTIVE,
        config={"phone_number_id": phone_number_id, "waba_id": "WABA1"},
    )


async def test_an_instagram_account_does_not_take_a_number_slot(
    client, db_session, console_world, link_reaches_meta
) -> None:
    w = console_world["a"]
    await _one_number_allowed_and(
        db_session,
        w,
        Channel(
            id=uuid.uuid4(),
            tenant_id=w["tenant_id"],
            type=ChannelType.INSTAGRAM,
            provider="meta_instagram",
            provider_identifier=f"ig-{uuid.uuid4().hex[:8]}",
            status=ChannelStatus.ACTIVE,
            config={},
        ),
    )
    r = await _link_signup(client, w, "PN-new")
    assert r.status_code == 418, r.text


async def test_reauthorising_the_same_number_by_link_passes_the_quota(
    client, db_session, console_world, link_reaches_meta
) -> None:
    w = console_world["a"]
    await _one_number_allowed_and(db_session, w, _number(w, "PN1"))
    r = await _link_signup(client, w, "PN1")
    assert r.status_code == 418, r.text


async def test_a_new_number_by_link_still_hits_the_quota(
    client, db_session, console_world, link_reaches_meta
) -> None:
    w = console_world["a"]
    await _one_number_allowed_and(db_session, w, _number(w, "PN1"))
    r = await _link_signup(client, w, "PN2")
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "channel_quota_full"
