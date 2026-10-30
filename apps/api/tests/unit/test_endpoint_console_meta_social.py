"""Spec 049, requirement 5 — connecting Instagram and Messenger from the console.

Meta is a fake Graph (``httpx.MockTransport``) behind the real client, so the
whole connection runs: code exchange, portfolio, granted assets, subscribe,
channel row, encrypted credential, audit.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
import sqlalchemy as sa
from nexus_channels.meta_social import MetaSocialClient
from nexus_channels.meta_social.credentials import SocialCredentials

from nexus_api.db.models import AuditLog, Channel, ChannelStatus, ChannelType, Partner
from nexus_api.services import meta_social_service

pytestmark = pytest.mark.asyncio

IG_ID = "17841400000000555"
PAGE_ID = "105000000000555"


class FakeGraph:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, str]]] = []
        self.instagram_accounts: list[dict[str, Any]] = [{"id": IG_ID, "username": "demo.store"}]
        self.pages: list[dict[str, Any]] = [
            {
                "id": PAGE_ID,
                "name": "Demo Store",
                "access_token": "PAGE-TOKEN",
                "tasks": ["MESSAGING"],
            }
        ]
        self.business: str | None = "BIZ_1"
        self.subscribe_error: dict[str, Any] | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/v26.0")
        params = dict(request.url.params)
        self.calls.append((request.method, path, params))
        if path == "/oauth/access_token":
            return httpx.Response(200, json={"access_token": "SUAT-1", "token_type": "bearer"})
        if path == "/me" and params.get("fields") == "client_business_id":
            return httpx.Response(
                200,
                json={"id": "SU", "client_business_id": self.business}
                if self.business
                else {"id": "SU"},
            )
        if path == "/me/assigned_instagram_accounts":
            return httpx.Response(200, json={"data": self.instagram_accounts})
        if path == "/me/accounts":
            return httpx.Response(200, json={"data": self.pages})
        if path.endswith("/subscribed_apps"):
            if request.method == "POST" and self.subscribe_error:
                return httpx.Response(400, json={"error": self.subscribe_error})
            return httpx.Response(200, json={"success": True})
        if path == f"/{IG_ID}":
            return httpx.Response(
                200,
                json={
                    "id": IG_ID,
                    "username": "demo.store",
                    "name": "Demo Store",
                    "profile_picture_url": "https://x/p.jpg",
                },
            )
        return httpx.Response(404, json={"error": {"message": "unexpected", "code": 100}})


@pytest.fixture
def graph(monkeypatch) -> FakeGraph:
    fake = FakeGraph()
    client = MetaSocialClient("dev-meta-app-secret-change-me", transport=httpx.MockTransport(fake))
    monkeypatch.setattr(meta_social_service, "_client", client)
    return fake


async def _beta(db_session, partner_id: uuid.UUID, channels: list[str]) -> None:
    await db_session.execute(
        sa.update(Partner).where(Partner.id == partner_id).values(beta_channels=channels)
    )
    await db_session.commit()


def _url(a: dict[str, Any], tail: str) -> str:
    return f"/console/clients/{a['ref']}/channels/{tail}"


async def test_without_beta_the_channel_does_not_exist(client, console_world, graph) -> None:
    a = console_world["a"]
    r = await client.post(_url(a, "instagram/connect"), headers=a["headers"](), json={"code": "c"})
    assert r.status_code == 404
    ov = await client.get(_url(a, "overview"), headers=a["headers"]())
    assert ov.json()["meta_social"] is None
    assert graph.calls == []


async def test_overview_offers_the_enabled_channels(
    client, console_world, db_session, graph
) -> None:
    a = console_world["a"]
    await _beta(db_session, a["partner_id"], ["instagram"])
    body = (await client.get(_url(a, "overview"), headers=a["headers"]())).json()
    assert body["meta_social"]["channels"] == [
        {"kind": "instagram", "config_id": "1157578836735566"}
    ]
    assert body["meta_social"]["app_id"] == "957213733862330"


async def test_connect_instagram_end_to_end(client, console_world, db_session, graph) -> None:
    a = console_world["a"]
    await _beta(db_session, a["partner_id"], ["instagram"])

    r = await client.post(
        _url(a, "instagram/connect"), headers=a["headers"](), json={"code": "CODE"}
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "connected"
    assert body["channel"]["type"] == "instagram"
    assert body["channel"]["username"] == "demo.store"
    assert body["channel"]["status"] == "active"
    # Subscribed with the token, per account, with the messaging fields.
    [(method, path, params)] = [c for c in graph.calls if c[1].endswith("/subscribed_apps")]
    assert method == "POST" and path == f"/{IG_ID}/subscribed_apps"
    assert "messages" in params["subscribed_fields"] and "comments" in params["subscribed_fields"]

    row = (
        await db_session.execute(sa.select(Channel).where(Channel.provider_identifier == IG_ID))
    ).scalar_one()
    assert row.tenant_id == a["tenant_id"]
    assert row.provider == "meta_instagram"
    creds = SocialCredentials.from_payload(row.config_encrypted)
    assert creds.token == "SUAT-1" and creds.client_business_id == "BIZ_1"
    assert "SUAT" not in json.dumps(row.config)  # the token never lands in plain config
    audit = (
        await db_session.execute(
            sa.select(AuditLog).where(AuditLog.action == "channel.instagram.connect")
        )
    ).scalar_one()
    assert audit.after_json["display_name"] == "@demo.store"

    # It does not take the WhatsApp number's slot.
    ov = (await client.get(_url(a, "overview"), headers=a["headers"]())).json()
    assert ov["used_channels"] == 0


async def test_connect_messenger_uses_the_page_token(
    client, console_world, db_session, graph
) -> None:
    a = console_world["a"]
    await _beta(db_session, a["partner_id"], ["messenger"])

    r = await client.post(
        _url(a, "messenger/connect"), headers=a["headers"](), json={"code": "CODE"}
    )

    assert r.json()["status"] == "connected", r.text
    row = (
        await db_session.execute(sa.select(Channel).where(Channel.provider_identifier == PAGE_ID))
    ).scalar_one()
    assert row.type is ChannelType.MESSENGER
    assert SocialCredentials.from_payload(row.config_encrypted).send_token == "PAGE-TOKEN"


async def test_several_accounts_ask_to_choose_then_complete(
    client, console_world, db_session, graph
) -> None:
    a = console_world["a"]
    await _beta(db_session, a["partner_id"], ["instagram"])
    graph.instagram_accounts = [
        {"id": IG_ID, "username": "demo.store"},
        {"id": "17841400000000777", "username": "other"},
    ]

    first = (
        await client.post(
            _url(a, "instagram/connect"), headers=a["headers"](), json={"code": "CODE"}
        )
    ).json()
    assert first["status"] == "choose"
    assert {acc["id"] for acc in first["accounts"]} == {IG_ID, "17841400000000777"}
    assert await db_session.scalar(sa.select(sa.func.count()).select_from(Channel)) == 0

    done = await client.post(
        _url(a, "instagram/connect/complete"),
        headers=a["headers"](),
        json={"nonce": first["nonce"], "account_id": IG_ID},
    )
    assert done.json()["status"] == "connected", done.text
    again = await client.post(
        _url(a, "instagram/connect/complete"),
        headers=a["headers"](),
        json={"nonce": first["nonce"], "account_id": IG_ID},
    )
    assert again.status_code == 409 and again.json()["detail"]["code"] == "pending_expired"


async def test_no_portfolio_says_how_to_fix_and_creates_nothing(
    client, console_world, db_session, graph
) -> None:
    a = console_world["a"]
    await _beta(db_session, a["partner_id"], ["instagram"])
    graph.business = None

    r = await client.post(
        _url(a, "instagram/connect"), headers=a["headers"](), json={"code": "CODE"}
    )

    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "no_business_portfolio"
    assert "portfolio" in r.json()["detail"]["help"]
    assert await db_session.scalar(sa.select(sa.func.count()).select_from(Channel)) == 0


async def test_messages_disabled_is_explained(client, console_world, db_session, graph) -> None:
    a = console_world["a"]
    await _beta(db_session, a["partner_id"], ["instagram"])
    graph.subscribe_error = {"message": "(#200) messaging disabled", "code": 200}

    r = await client.post(
        _url(a, "instagram/connect"), headers=a["headers"](), json={"code": "CODE"}
    )

    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "messages_disabled"
    assert "Allow access to messages" in r.json()["detail"]["help"]


async def test_an_account_live_under_another_client_is_refused(
    client, console_world, db_session, graph
) -> None:
    a, b = console_world["a"], console_world["b"]
    await _beta(db_session, a["partner_id"], ["instagram"])
    db_session.add(
        Channel(
            tenant_id=b["tenant_id"],
            type=ChannelType.INSTAGRAM,
            provider="meta_instagram",
            provider_identifier=IG_ID,
            status=ChannelStatus.ACTIVE,
            config={},
        )
    )
    await db_session.commit()

    r = await client.post(
        _url(a, "instagram/connect"), headers=a["headers"](), json={"code": "CODE"}
    )

    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "already_connected_elsewhere"


async def test_disconnect_drops_the_token_now_and_starts_the_clock(
    client, console_world, db_session, graph
) -> None:
    a = console_world["a"]
    await _beta(db_session, a["partner_id"], ["instagram"])
    connected = (
        await client.post(
            _url(a, "instagram/connect"), headers=a["headers"](), json={"code": "CODE"}
        )
    ).json()
    channel_id = connected["channel"]["id"]

    r = await client.post(_url(a, f"{channel_id}/disconnect"), headers=a["headers"]())

    assert r.status_code == 200, r.text
    assert r.json()["status"] == "disconnected"
    assert ("DELETE", f"/{IG_ID}/subscribed_apps") in [(m, p) for m, p, _ in graph.calls]
    db_session.expire_all()
    row = await db_session.get(Channel, uuid.UUID(channel_id))
    assert row is not None
    assert row.config_encrypted is None
    disconnected_at = datetime.fromisoformat(row.config["disconnected_at"])
    assert datetime.now(UTC) - disconnected_at < timedelta(minutes=1)
    assert (
        await db_session.scalar(
            sa.select(sa.func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == "channel.meta_social.disconnect")
        )
        == 1
    )


async def test_admin_switches_the_beta_on_for_one_partner(
    client, console_world, db_session, admin_headers, graph
) -> None:
    from nexus_api.services import operator_identity

    a, b = console_world["a"], console_world["b"]
    async with db_session.begin():
        op = await operator_identity.create_account(
            db_session,
            email=f"ops-{uuid.uuid4().hex[:8]}@auphere.test",
            password="operator-password-1",
            display_name="Ops",
        )
    headers = {**admin_headers, "X-Operator-Id": str(op.id)}

    r = await client.put(
        f"/admin/partners/{a['partner_id']}/beta-channels",
        headers=headers,
        json={"channels": ["messenger", "instagram"]},
    )

    assert r.status_code == 200, r.text
    assert r.json()["channels"] == ["instagram", "messenger"]
    mine = (await client.get(_url(a, "overview"), headers=a["headers"]())).json()
    theirs = (
        await client.get(f"/console/clients/{b['ref']}/channels/overview", headers=b["headers"]())
    ).json()
    assert [c["kind"] for c in mine["meta_social"]["channels"]] == ["instagram", "messenger"]
    assert theirs["meta_social"] is None
    bad = await client.put(
        f"/admin/partners/{a['partner_id']}/beta-channels",
        headers=headers,
        json={"channels": ["telegram"]},
    )
    assert bad.status_code == 422


def test_the_new_console_names_the_account_not_the_meta_id() -> None:
    """Spec 049 in the v2 agent channels: @username / Page name, never the id."""
    from nexus_api.api.console.channel_config import _identifier

    ig = Channel(
        provider="meta_instagram", provider_identifier=IG_ID, config={"username": "demo.store"}
    )
    page = Channel(
        provider="meta_messenger", provider_identifier=PAGE_ID, config={"name": "Demo Store"}
    )
    wa = Channel(provider="meta", provider_identifier="+34600000001", config={"username": "x"})
    assert _identifier(ig) == "@demo.store"
    assert _identifier(page) == "Demo Store"
    assert _identifier(wa) == "+34600000001"


async def test_the_partner_sets_the_public_reply_to_comments(
    client, console_world, db_session, graph
) -> None:
    """QA 2026-10-30 (INC-07): nobody could write ``comment_public_reply``,
    so the public line under a comment never went out."""
    a = console_world["a"]
    await _beta(db_session, a["partner_id"], ["instagram"])
    r = await client.post(
        _url(a, "instagram/connect"), headers=a["headers"](), json={"code": "CODE"}
    )
    channel_id = r.json()["channel"]["id"]
    url = f"/console/clients/{a['ref']}/channels/{channel_id}"

    page = (await client.get(url, headers=a["headers"]())).json()
    assert page["instagram_comments"] == {"enabled": True, "public_reply": None}

    r = await client.put(
        f"{url}/comments",
        headers=a["headers"](),
        json={"enabled": True, "public_reply": "  We sent you a DM 📩  "},
    )
    assert r.status_code == 200, r.text
    assert r.json()["instagram_comments"] == {
        "enabled": True,
        "public_reply": "We sent you a DM 📩",
    }
    row = await db_session.get(Channel, uuid.UUID(channel_id), populate_existing=True)
    assert row.config["comment_public_reply"] == "We sent you a DM 📩"

    r = await client.put(
        f"{url}/comments", headers=a["headers"](), json={"enabled": False, "public_reply": ""}
    )
    assert r.json()["instagram_comments"] == {"enabled": False, "public_reply": None}
    row = await db_session.get(Channel, uuid.UUID(channel_id), populate_existing=True)
    assert row.config["comments_enabled"] is False
    assert "comment_public_reply" not in row.config
    audits = (
        (
            await db_session.execute(
                sa.select(AuditLog).where(AuditLog.action == "console.channel.comments")
            )
        )
        .scalars()
        .all()
    )
    assert len(audits) == 2


async def test_comment_settings_are_only_for_instagram(
    client, console_world, db_session, graph
) -> None:
    a = console_world["a"]
    await _beta(db_session, a["partner_id"], ["messenger"])
    r = await client.post(
        _url(a, "messenger/connect"), headers=a["headers"](), json={"code": "CODE"}
    )
    channel_id = r.json()["channel"]["id"]
    url = f"/console/clients/{a['ref']}/channels/{channel_id}"
    assert (await client.get(url, headers=a["headers"]())).json()["instagram_comments"] is None
    r = await client.put(
        f"{url}/comments", headers=a["headers"](), json={"enabled": True, "public_reply": "Hi"}
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "not_instagram"
