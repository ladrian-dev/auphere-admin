"""Spec 024 (Requisitos 3.1, 3.3): the client list and the client record say
who the ACTIVE agent answers — never the draft, which is what the settings
screen edits — and the list reads it once per page.
"""

from __future__ import annotations

import pytest

from tests.unit.test_endpoint_console_agent_settings_audience import LIST
from tests.unit.test_endpoint_console_agent_tools import SETTINGS, _stage_and_publish

pytestmark = pytest.mark.asyncio


async def _limit(client, w, audience: dict) -> None:
    base = f"/console/clients/{w['ref']}/agent"
    saved = await client.put(
        f"{base}/settings",
        headers=w["headers"](),
        json={"settings": SETTINGS, "audience": audience},
    )
    assert saved.status_code == 200, saved.text
    pub = await client.post(
        f"{base}/versions/{saved.json()['version']}/publish", headers=w["headers"]()
    )
    assert pub.status_code == 200, pub.text


async def test_without_an_active_agent_there_is_nothing_to_say(client, console_world) -> None:
    a = console_world["a"]
    got = await client.get(f"/console/clients/{a['ref']}", headers=a["headers"]())
    assert got.status_code == 200, got.text
    assert got.json()["audience"] is None


async def test_the_record_and_the_list_read_the_active_version(client, console_world) -> None:
    a = console_world["a"]
    h = a["headers"]
    await _stage_and_publish(client, a)

    record = (await client.get(f"/console/clients/{a['ref']}", headers=h())).json()
    assert record["audience"] == {"mode": "everyone", "count": 0}

    await _limit(client, a, LIST)
    record = (await client.get(f"/console/clients/{a['ref']}", headers=h())).json()
    assert record["audience"] == {"mode": "list", "count": 2}

    page = (await client.get("/console/clients", headers=h())).json()
    rows = {c["external_client_ref"]: c for c in page["items"]}
    assert rows[a["ref"]]["audience"] == {"mode": "list", "count": 2}


async def test_a_draft_does_not_change_what_the_record_says(client, console_world) -> None:
    """The settings screen edits the draft; the header says what answers."""
    a = console_world["a"]
    h = a["headers"]
    await _stage_and_publish(client, a)
    saved = await client.put(
        f"/console/clients/{a['ref']}/agent/settings",
        headers=h(),
        json={"settings": SETTINGS, "audience": LIST},
    )
    assert saved.status_code == 200, saved.text
    record = (await client.get(f"/console/clients/{a['ref']}", headers=h())).json()
    assert record["audience"] == {"mode": "everyone", "count": 0}


async def test_the_other_partner_sees_its_own_clients_only(client, console_world) -> None:
    a, b = console_world["a"], console_world["b"]
    await _stage_and_publish(client, a)
    await _limit(client, a, LIST)
    page = (await client.get("/console/clients", headers=b["headers"]())).json()
    assert all(c["external_client_ref"] != a["ref"] for c in page["items"])
