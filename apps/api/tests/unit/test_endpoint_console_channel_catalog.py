"""``GET /console/channel-catalog`` (spec 046, T002).

Constitution §V, amendment 1.2.0: the console shows what is coming, marked
with its state, and only what the console can connect is startable. The
copy is the partner's: no ADRs, no provider plumbing, never a date.
"""

from __future__ import annotations

import re

import pytest

from nexus_api.api.console.channel_catalog import console_entry
from nexus_api.config import get_settings
from nexus_api.services.channel_catalog import ChannelEntry

pytestmark = pytest.mark.asyncio

URL = "/console/channel-catalog"


async def test_the_partner_sees_every_channel_with_its_state(client, console_world, monkeypatch):
    monkeypatch.setattr(get_settings(), "tiktok_enabled", False, raising=False)
    a = console_world["a"]
    r = await client.get(URL, headers=a["headers"]())
    assert r.status_code == 200, r.text
    by_key = {c["key"]: c for c in r.json()}
    assert list(by_key) == ["whatsapp", "tiktok", "instagram", "telegram", "x", "threads"]
    assert by_key["whatsapp"]["availability"] == "available"
    assert by_key["whatsapp"]["note"] is None
    assert by_key["tiktok"]["availability"] == "pending"
    for key in ("instagram", "telegram", "x", "threads"):
        assert by_key[key]["availability"] == "coming_soon"
        assert by_key[key]["note"]


async def test_tiktok_in_beta_is_still_not_startable_from_the_console(
    client, console_world, monkeypatch
):
    # The panel connects TikTok in beta; the console has no step for it yet.
    monkeypatch.setattr(get_settings(), "tiktok_enabled", True, raising=False)
    r = await client.get(URL, headers=console_world["a"]["headers"]())
    tiktok = next(c for c in r.json() if c["key"] == "tiktok")
    assert tiktok["availability"] == "coming_soon"


async def test_the_copy_never_leaks_internals_or_promises_a_date(client, console_world):
    r = await client.get(URL, headers=console_world["a"]["headers"]())
    text = " ".join(f"{c['description']} {c['note'] or ''}" for c in r.json())
    assert "ADR" not in text
    assert "API de Meta" not in text
    assert "spec" not in text.lower()
    assert not re.search(r"\b20\d\d\b", text)
    assert ";" not in text


async def test_it_needs_a_console_session(client):
    assert (await client.get(URL)).status_code in (401, 403)


async def test_only_whatsapp_is_startable():
    beta = ChannelEntry(key="tiktok", name="TikTok", description="d", availability="beta")
    assert console_entry(beta).availability == "coming_soon"
    wa = ChannelEntry(key="whatsapp", name="WhatsApp", description="d", availability="available")
    assert console_entry(wa).availability == "available"
