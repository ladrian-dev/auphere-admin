"""Spec 085 — the owner connects Instagram or Messenger from a link.

The WhatsApp link of spec 040, one per channel, and the console's own
Instagram / Messenger connection of spec 049 behind the public page. Meta is
the fake Graph of ``test_endpoint_console_meta_social`` behind the real
client; the link, the channel, the credential and the consumption run against
the database.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
import sqlalchemy as sa
from fastapi import HTTPException
from nexus_channels.meta_social import MetaSocialClient
from nexus_channels.meta_social.credentials import SocialCredentials
from nexus_channels.whatsapp_meta.exceptions import MetaAPIError
from sqlalchemy.exc import IntegrityError

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    Agent,
    AuditLog,
    Channel,
    ChannelSignupLink,
    ChannelStatus,
    ChannelType,
    ConsoleNotification,
    Partner,
)
from nexus_api.services import meta_social_service
from nexus_api.services.channel_signup_links import link_state, mint_link
from tests.conftest import console_headers
from tests.unit.test_endpoint_console_meta_social import IG_ID, PAGE_ID, FakeGraph

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

PUBLIC = "/console/channel-signup"
OTHER_IG = "17841400000000779"


@pytest.fixture
def graph(monkeypatch: pytest.MonkeyPatch) -> FakeGraph:
    """Meta: the fake Graph of spec 049's tests behind the real client."""
    fake = FakeGraph()
    client = MetaSocialClient("dev-meta-app-secret-change-me", transport=httpx.MockTransport(fake))
    monkeypatch.setattr(meta_social_service, "_client", client)
    return fake


def _svc() -> dict[str, str]:
    """The console server's service credential: a fresh one per call."""
    return console_headers(user_id="console-bff", partner_id=None, service=True)


def _token(url: str) -> str:
    return url.rsplit("/", 1)[-1]


async def _enable(db_session: Any, w: dict[str, Any], channels: list[str]) -> None:
    await db_session.execute(
        sa.update(Partner).where(Partner.id == w["partner_id"]).values(beta_channels=channels)
    )
    await db_session.commit()


async def _client_link(client: Any, w: dict[str, Any], kind: str = "instagram") -> str:
    made = await client.post(
        f"/console/clients/{w['ref']}/channels/{kind}/signup-link", headers=w["headers"]()
    )
    assert made.status_code == 201, made.text
    return _token(made.json()["url"])


async def _link_row(db_session: Any, token: str) -> ChannelSignupLink:
    from nexus_api.services.channel_signup_links import hash_token

    row = await db_session.scalar(
        sa.select(ChannelSignupLink)
        .where(ChannelSignupLink.token_hash == hash_token(token))
        .execution_options(populate_existing=True)
    )
    assert row is not None
    return row


async def _social_channels(db_session: Any, tenant_id: uuid.UUID) -> list[Channel]:
    db_session.expire_all()
    return list(
        (
            await db_session.scalars(
                sa.select(Channel).where(
                    Channel.tenant_id == tenant_id,
                    Channel.provider.in_(["meta_instagram", "meta_messenger"]),
                )
            )
        ).all()
    )


async def _mint(
    tenant_id: uuid.UUID,
    *,
    channel: str,
    mode: str | None = None,
    agent_id: uuid.UUID | None = None,
    replace: bool = False,
) -> ChannelSignupLink:
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
        minted = await mint_link(
            s,
            tenant_id=tenant_id,
            channel=channel,
            mode=mode,
            actor="console:test@example.com",
            agent_id=agent_id,
            replace=replace,
        )
        return minted.link


async def _state(link_id: uuid.UUID) -> str:
    async with get_sessionmaker()() as s:
        return link_state(await s.get(ChannelSignupLink, link_id))


async def _agent(db_session: Any, tenant_id: uuid.UUID, name: str) -> uuid.UUID:
    agent_id = uuid.uuid4()
    async with tenant_scoped_session(db_session, tenant_id):
        db_session.add(Agent(id=agent_id, tenant_id=tenant_id, name=name, lifecycle="published"))
    await db_session.commit()
    return agent_id


# ── La base: un enlace vivo por cliente y canal (requisitos 1.2 y 1.5) ─────────


async def test_an_instagram_link_leaves_the_whatsapp_one_alive(console_world) -> None:
    tenant_id = console_world["a"]["tenant_id"]
    whatsapp = await _mint(tenant_id, channel="whatsapp", mode="coexistence")
    first = await _mint(tenant_id, channel="instagram")
    assert first.mode == "meta_login", "the owner chooses how to sign in, not the partner"
    assert await _state(whatsapp.id) == "valid", "another channel's link is not replaced"

    second = await _mint(tenant_id, channel="instagram")
    assert await _state(first.id) == "revoked", "the same channel's link is"
    assert await _state(second.id) == "valid"
    assert await _state(whatsapp.id) == "valid"


async def test_an_agent_holds_a_pending_link_per_channel(console_world, db_session) -> None:
    tenant_id = console_world["a"]["tenant_id"]
    agent_id = await _agent(db_session, tenant_id, "Recepción")
    whatsapp = await _mint(tenant_id, channel="whatsapp", mode="coexistence", agent_id=agent_id)
    instagram = await _mint(tenant_id, channel="instagram", agent_id=agent_id)
    messenger = await _mint(tenant_id, channel="messenger", agent_id=agent_id)
    for link in (whatsapp, instagram, messenger):
        assert await _state(link.id) == "valid"

    # The same agent and channel still offers to replace the pending one.
    with pytest.raises(HTTPException) as refused:
        await _mint(tenant_id, channel="instagram", agent_id=agent_id)
    assert refused.value.detail == {"code": "link_pending_exists", "link_id": str(instagram.id)}


async def test_an_expired_agent_link_does_not_block_the_next_one(console_world, db_session) -> None:
    """It used to: the index ignores expiry and the mint only revoked live
    links, so the INSERT failed with a 500."""
    tenant_id = console_world["a"]["tenant_id"]
    agent_id = await _agent(db_session, tenant_id, "Recepción")
    old = await _mint(tenant_id, channel="whatsapp", mode="coexistence", agent_id=agent_id)
    await db_session.execute(
        sa.update(ChannelSignupLink)
        .where(ChannelSignupLink.id == old.id)
        .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    await db_session.commit()

    fresh = await _mint(tenant_id, channel="whatsapp", mode="coexistence", agent_id=agent_id)
    assert await _state(fresh.id) == "valid"
    assert await _state(old.id) == "revoked", "the expired one is put away, with its audit row"


async def test_the_table_ties_each_channel_to_its_modes(console_world, db_session) -> None:
    tenant_id = console_world["a"]["tenant_id"]

    def row(channel: str, mode: str) -> ChannelSignupLink:
        return ChannelSignupLink(
            tenant_id=tenant_id,
            token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
            channel=channel,
            mode=mode,
            created_by="test",
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )

    db_session.add(row("instagram", "meta_login"))
    db_session.add(row("messenger", "meta_login"))
    await db_session.commit()

    for channel, mode in (
        ("instagram", "coexistence"),
        ("whatsapp", "meta_login"),
        ("tiktok", "meta_login"),
    ):
        db_session.add(row(channel, mode))
        with pytest.raises(IntegrityError):
            await db_session.commit()
        await db_session.rollback()


# ── H1: el cliente conecta su Instagram desde un enlace ─────────────────────────


async def test_the_partner_mints_an_instagram_link_without_choosing_a_mode(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    base = f"/console/clients/{a['ref']}/channels"
    absent = await client.post(f"{base}/instagram/signup-link", headers=a["headers"]())
    assert absent.status_code == 404, "without the channel, the route does not exist (§V)"

    await _enable(db_session, a, ["instagram"])
    made = await client.post(f"{base}/instagram/signup-link", headers=a["headers"]())
    assert made.status_code == 201, made.text
    body = made.json()
    assert body["channel"] == "instagram"
    assert "/connect/instagram/" in body["url"]
    assert body["expires_at"]
    assert set(body) == {"url", "channel", "expires_at"}

    unknown = await client.post(f"{base}/tiktok/signup-link", headers=a["headers"]())
    assert unknown.status_code == 422

    # The client's list shows it next to WhatsApp's, with its channel (1.5).
    whatsapp = await client.post(
        f"{base}/whatsapp/signup-link", headers=a["headers"](), json={"mode": "coexistence"}
    )
    assert whatsapp.status_code == 201, whatsapp.text
    listed = (await client.get(f"{base}/whatsapp/signup-links", headers=a["headers"]())).json()
    assert [(r["channel"], r["state"]) for r in listed] == [
        ("whatsapp", "valid"),
        ("instagram", "valid"),
    ]


async def test_the_owner_page_learns_how_to_open_meta(client, console_world, db_session) -> None:
    a = console_world["a"]
    await _enable(db_session, a, ["instagram"])
    token = await _client_link(client, a)

    info = (await client.get(f"{PUBLIC}/{token}", headers=_svc())).json()
    assert info["state"] == "valid"
    assert info["channel"] == "instagram"
    assert info["mode"] == "meta_login"
    assert info["business_name"]
    assert info["meta_app_id"]
    # The console's own offer (spec 049, R8; spec 081, 1.1).
    assert info["meta_config_id"] == meta_social_service.config_id("instagram")
    assert info["meta_page_config_id"] == meta_social_service.page_config_id("instagram")
    assert info["meta_signup_version"] is None

    # Without the channel for the partner, the link is as if it did not exist.
    await _enable(db_session, a, [])
    gone = (await client.get(f"{PUBLIC}/{token}", headers=_svc())).json()
    assert gone["state"] == "unknown" and gone["channel"] is None
    refused = await client.post(
        f"{PUBLIC}/{token}/meta-social", headers=_svc(), json={"code": "CODE"}
    )
    assert refused.status_code == 404
    assert refused.json()["detail"]["code"] == "link_unknown"


async def test_the_owner_connects_instagram_and_the_link_is_used(
    client, console_world, db_session, graph
) -> None:
    a = console_world["a"]
    await _enable(db_session, a, ["instagram"])
    # A full number quota does not stop Instagram (spec 049; requirement 6.1).
    await db_session.execute(
        sa.update(Partner).where(Partner.id == a["partner_id"]).values(max_channels_per_client=1)
    )
    async with get_sessionmaker()() as s, tenant_scoped_session(s, a["tenant_id"]):
        s.add(
            Channel(
                tenant_id=a["tenant_id"],
                type=ChannelType.WHATSAPP,
                provider="meta",
                provider_identifier="+56999990077",
                status=ChannelStatus.ACTIVE,
                config={"phone_number_id": "PN77", "waba_id": "W77"},
            )
        )
    await db_session.commit()
    token = await _client_link(client, a)

    done = await client.post(f"{PUBLIC}/{token}/meta-social", headers=_svc(), json={"code": "CODE"})
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["status"] == "connected"
    assert body["display_name"] == "@demo.store"
    assert body["business_name"]
    assert "channel" not in body and "tenant_id" not in body

    [channel] = await _social_channels(db_session, a["tenant_id"])
    assert channel.provider_identifier == IG_ID and channel.status == ChannelStatus.ACTIVE
    link = await _link_row(db_session, token)
    assert link.consumed_at is not None and link.channel_id == channel.id
    audit = await db_session.scalar(
        sa.select(AuditLog).where(AuditLog.action == "channel.instagram.connect")
    )
    assert audit is not None and audit.actor == f"link:{link.id}"
    assert audit.after_json["display_name"] == "@demo.store"

    # Single use, with the WhatsApp page's states.
    again = await client.post(
        f"{PUBLIC}/{token}/meta-social", headers=_svc(), json={"code": "CODE"}
    )
    assert again.status_code == 410 and again.json()["detail"]["code"] == "link_used"


async def test_an_agents_link_puts_the_account_on_that_agent_and_tells_the_partner(
    client, console_world, db_session, graph
) -> None:
    a = console_world["a"]
    await _enable(db_session, a, ["instagram"])
    agent_id = await _agent(db_session, a["tenant_id"], "Ventas")
    links = f"/console/clients/{a['ref']}/agents/{agent_id}/channels/owner-links"
    whatsapp = await client.post(links, headers=a["headers"](), json={"mode": "coexistence"})
    assert whatsapp.status_code == 201, whatsapp.text
    made = await client.post(links, headers=a["headers"](), json={"channel": "instagram"})
    assert made.status_code == 201, made.text
    assert made.json()["channel"] == "instagram" and made.json()["mode"] == "meta_login"
    assert "/connect/instagram/" in made.json()["url"]
    clash = await client.post(links, headers=a["headers"](), json={"channel": "instagram"})
    assert clash.status_code == 409 and clash.json()["detail"]["code"] == "link_pending_exists"
    bad = await client.post(
        links, headers=a["headers"](), json={"channel": "instagram", "mode": "coexistence"}
    )
    assert bad.status_code == 422

    tab = (
        await client.get(
            f"/console/clients/{a['ref']}/agents/{agent_id}/channels", headers=a["headers"]()
        )
    ).json()
    assert tab["pending_link"]["id"] == whatsapp.json()["id"], "pending_link stays WhatsApp's"
    assert sorted((p["channel"], p["id"]) for p in tab["pending_links"]) == sorted(
        [("whatsapp", whatsapp.json()["id"]), ("instagram", made.json()["id"])]
    )

    token = _token(made.json()["url"])
    done = await client.post(f"{PUBLIC}/{token}/meta-social", headers=_svc(), json={"code": "C"})
    assert done.status_code == 200, done.text

    [channel] = await _social_channels(db_session, a["tenant_id"])
    assert channel.agent_id == agent_id, "the account is on the link's agent"
    moved = await db_session.scalar(
        sa.select(AuditLog).where(
            AuditLog.action == "channel.moved", AuditLog.target == f"channel:{channel.id}"
        )
    )
    assert moved is not None and moved.actor.startswith("link:")
    notices = (
        await db_session.scalars(
            sa.select(ConsoleNotification).where(
                ConsoleNotification.partner_id == a["partner_id"],
                ConsoleNotification.kind == "channel.connected",
            )
        )
    ).all()
    assert len(notices) == 1
    assert notices[0].payload["via"] == "owner_link"
    assert notices[0].payload["agent_id"] == str(agent_id)
    assert notices[0].payload["channel_id"] == str(channel.id)


async def test_meta_refusing_or_failing_leaves_the_link_valid(
    client, console_world, db_session, graph, monkeypatch
) -> None:
    a = console_world["a"]
    await _enable(db_session, a, ["instagram"])
    token = await _client_link(client, a)

    graph.subscribe_error = {"message": "nope", "code": 1}
    refused = await client.post(f"{PUBLIC}/{token}/meta-social", headers=_svc(), json={"code": "C"})
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["code"] == "subscribe_failed"
    assert refused.json()["detail"]["help"] == meta_social_service.REASON_HELP["subscribe_failed"]
    graph.subscribe_error = None

    async def silent(**_: Any) -> Any:
        raise MetaAPIError("down", status_code=500, code=2)

    monkeypatch.setattr(meta_social_service._client, "assigned_instagram_accounts", silent)
    down = await client.post(f"{PUBLIC}/{token}/meta-social", headers=_svc(), json={"code": "C"})
    assert down.status_code == 502, down.text

    link = await _link_row(db_session, token)
    assert link.consumed_at is None and link.revoked_at is None, "the link still works"
    assert await _social_channels(db_session, a["tenant_id"]) == []


async def test_dead_links_answer_like_whatsapps(client, console_world, db_session, graph) -> None:
    a = console_world["a"]
    await _enable(db_session, a, ["instagram"])
    unknown = await client.post(
        f"{PUBLIC}/no-such-token-000000/meta-social", headers=_svc(), json={"code": "C"}
    )
    assert unknown.status_code == 404 and unknown.json()["detail"]["code"] == "link_unknown"

    expired = await _client_link(client, a)
    await db_session.execute(
        sa.update(ChannelSignupLink)
        .where(ChannelSignupLink.id == (await _link_row(db_session, expired)).id)
        .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    await db_session.commit()
    r = await client.post(f"{PUBLIC}/{expired}/meta-social", headers=_svc(), json={"code": "C"})
    assert r.status_code == 410 and r.json()["detail"]["code"] == "link_expired"

    first = await _client_link(client, a)
    await _client_link(client, a)  # replaces the first
    r = await client.post(f"{PUBLIC}/{first}/meta-social", headers=_svc(), json={"code": "C"})
    assert r.status_code == 410 and r.json()["detail"]["code"] == "link_revoked"
    r = await client.post(
        f"{PUBLIC}/{first}/meta-social/complete",
        headers=_svc(),
        json={"nonce": "n" * 16, "account_id": IG_ID},
    )
    assert r.status_code == 410 and r.json()["detail"]["code"] == "link_revoked"


async def test_the_whatsapp_route_refuses_an_instagram_link(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    await _enable(db_session, a, ["instagram"])
    token = await _client_link(client, a)
    r = await client.post(f"{PUBLIC}/{token}", headers=_svc(), json={"code": "c", "waba_id": "W-x"})
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "link_channel_mismatch"
    link = await _link_row(db_session, token)
    assert link.consumed_at is None and link.revoked_at is None


async def test_reconnecting_an_account_of_this_client_updates_its_channel(
    client, console_world, db_session, graph
) -> None:
    a = console_world["a"]
    await _enable(db_session, a, ["instagram"])
    first = await _client_link(client, a)
    assert (
        await client.post(f"{PUBLIC}/{first}/meta-social", headers=_svc(), json={"code": "C"})
    ).status_code == 200
    [before] = await _social_channels(db_session, a["tenant_id"])

    graph.token = "SUAT-2"
    second = await _client_link(client, a)
    again = await client.post(f"{PUBLIC}/{second}/meta-social", headers=_svc(), json={"code": "C"})
    assert again.status_code == 200, again.text

    [after] = await _social_channels(db_session, a["tenant_id"])
    assert after.id == before.id, "the same channel, not another"
    assert SocialCredentials.from_payload(after.config_encrypted).token == "SUAT-2"


# ── H2: el cliente conecta su Messenger desde un enlace ─────────────────────────


async def test_the_owner_connects_a_page_to_messenger(
    client, console_world, db_session, graph
) -> None:
    a = console_world["a"]
    await _enable(db_session, a, ["messenger"])
    token = await _client_link(client, a, "messenger")

    info = (await client.get(f"{PUBLIC}/{token}", headers=_svc())).json()
    assert info["channel"] == "messenger" and info["mode"] == "meta_login"
    assert info["meta_config_id"] == meta_social_service.config_id("messenger")
    assert info["meta_page_config_id"] is None, "Messenger asks nothing: Facebook and the Page"

    done = await client.post(f"{PUBLIC}/{token}/meta-social", headers=_svc(), json={"code": "C"})
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "connected"
    assert done.json()["display_name"] == "Demo Store"

    [channel] = await _social_channels(db_session, a["tenant_id"])
    assert channel.type == ChannelType.MESSENGER and channel.provider_identifier == PAGE_ID
    assert SocialCredentials.from_payload(channel.config_encrypted).page_token == "PAGE-TOKEN"
    assert (await _link_row(db_session, token)).channel_id == channel.id


# ── H3: elegir entre varias cuentas o Páginas ──────────────────────────────────


async def test_the_owner_picks_one_of_several_accounts_with_the_same_link(
    client, console_world, db_session, graph
) -> None:
    a = console_world["a"]
    await _enable(db_session, a, ["instagram"])
    graph.instagram_accounts = [
        {"id": IG_ID, "username": "demo.store"},
        {"id": OTHER_IG, "username": "other"},
    ]
    token = await _client_link(client, a)

    first = await client.post(f"{PUBLIC}/{token}/meta-social", headers=_svc(), json={"code": "C"})
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["status"] == "choose" and body["nonce"]
    assert {acc["id"] for acc in body["accounts"]} == {IG_ID, OTHER_IG}
    assert (await _link_row(db_session, token)).consumed_at is None, "asking does not use it"
    assert await _social_channels(db_session, a["tenant_id"]) == []

    expired = await client.post(
        f"{PUBLIC}/{token}/meta-social/complete",
        headers=_svc(),
        json={"nonce": "not-the-nonce-1234", "account_id": OTHER_IG},
    )
    assert expired.status_code == 409, expired.text
    assert expired.json()["detail"]["code"] == "pending_expired"
    assert (await _link_row(db_session, token)).consumed_at is None, "an expired choice keeps it"

    done = await client.post(
        f"{PUBLIC}/{token}/meta-social/complete",
        headers=_svc(),
        json={"nonce": body["nonce"], "account_id": OTHER_IG},
    )
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "connected" and done.json()["display_name"] == "@other"
    [channel] = await _social_channels(db_session, a["tenant_id"])
    assert channel.provider_identifier == OTHER_IG, "the one picked, not the other"
    link = await _link_row(db_session, token)
    assert link.consumed_at is not None and link.channel_id == channel.id
