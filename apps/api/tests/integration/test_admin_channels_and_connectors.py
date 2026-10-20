"""Spec 035 — the channel catalog and the views across every client.

The global views read ``channels`` and ``tenant_connectors`` client by client
under each client's GUC: every row comes back labelled with the client it
belongs to, and the Playground's internal channels never show.
"""

from __future__ import annotations

import uuid

import pytest

from nexus_api.config import get_settings
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Channel, ChannelStatus, ChannelType

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _channel(
    tenant_id: uuid.UUID, *, identifier: str, provider: str = "meta", **config
) -> None:
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
        s.add(
            Channel(
                tenant_id=tenant_id,
                type=ChannelType.WHATSAPP if provider != "qa_playground" else ChannelType.WEB,
                provider=provider,
                provider_identifier=identifier,
                config=config,
                status=ChannelStatus.ACTIVE,
            )
        )


async def test_the_catalog_names_six_channels_with_their_state(
    client, admin_headers, monkeypatch
) -> None:
    monkeypatch.setattr(get_settings(), "tiktok_enabled", False, raising=False)
    res = await client.get("/admin/channel-catalog", headers=admin_headers)
    assert res.status_code == 200, res.text
    by_key = {c["key"]: c for c in res.json()}
    assert list(by_key) == ["whatsapp", "tiktok", "instagram", "telegram", "x", "threads"]
    assert by_key["whatsapp"]["availability"] == "available"
    assert by_key["tiktok"]["availability"] == "pending"
    assert {by_key[k]["availability"] for k in ("instagram", "telegram", "x", "threads")} == {
        "coming_soon"
    }

    monkeypatch.setattr(get_settings(), "tiktok_enabled", True, raising=False)
    on = {
        c["key"]: c
        for c in (await client.get("/admin/channel-catalog", headers=admin_headers)).json()
    }
    assert on["tiktok"]["availability"] == "beta"


async def test_every_channel_of_every_client_is_labelled_with_its_client(
    client, console_world, admin_headers
) -> None:
    a, b = console_world["a"], console_world["b"]
    await _channel(
        a["tenant_id"], identifier="+56900000001", role="agent", verified_name="Tienda A"
    )
    await _channel(b["tenant_id"], identifier="+56900000002", agent_enabled=False)
    await _channel(
        a["tenant_id"], identifier=f"qa_playground:{a['tenant_id']}", provider="qa_playground"
    )

    res = await client.get("/admin/channels", headers=admin_headers)
    assert res.status_code == 200, res.text
    rows = {r["provider_identifier"]: r for r in res.json()["channels"]}
    assert rows["+56900000001"]["tenant_id"] == str(a["tenant_id"])
    assert rows["+56900000001"]["partner_id"] == str(a["partner_id"])
    assert rows["+56900000001"]["role"] == "agent"
    assert rows["+56900000001"]["name"] == "Tienda A"
    assert rows["+56900000002"]["tenant_id"] == str(b["tenant_id"])
    assert rows["+56900000002"]["agent_enabled"] is False
    # The Playground's internal channel is not a channel of the client.
    assert not any(k.startswith("qa_playground:") for k in rows)
    assert res.json()["unreadable"] == []


async def test_the_global_views_require_the_admin_token(client) -> None:
    for path in ("/admin/channel-catalog", "/admin/channels", "/admin/connectors-installs"):
        assert (await client.get(path)).status_code in (401, 403)


async def test_connector_installs_name_their_clients(client, console_world, admin_headers) -> None:
    res = await client.get("/admin/connectors-installs", headers=admin_headers)
    assert res.status_code == 200, res.text
    for installs in res.json().values():
        for row in installs:
            assert set(row) == {"tenant_id", "tenant_name", "status"}
