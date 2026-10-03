"""Spec 028: ``GET /console/usage/spend`` — what the partner spent, in money."""

from __future__ import annotations

import pytest

from nexus_api.metering.wallet import debit_wallet

pytestmark = pytest.mark.asyncio


async def _spend(a) -> None:
    await debit_wallet(
        partner_id=a["partner_id"], tenant_id=a["tenant_id"], qty=120_000, idempotency_key="sp:a"
    )
    await debit_wallet(partner_id=a["partner_id"], qty=30_000, idempotency_key="sp:companion")


async def test_spend_is_money_per_day_and_per_client(client, console_world) -> None:
    a = console_world["a"]
    await _spend(a)
    r = await client.get("/console/usage/spend?days=7", headers=a["headers"]())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["currency"] == "USD" and len(body["days"]) == 7
    assert body["series_cents"][-1] == 150  # 1,20 US$ of the client + 0,30 of the Companion
    by = {c["external_client_ref"]: c["series_cents"][-1] for c in body["by_client"]}
    assert by == {a["ref"]: 120, None: 30}
    assert body["month_cents"] == 150 and body["projected_cents"] >= 150
    month = {c["external_client_ref"]: c["cents"] for c in body["month_by_client"]}
    assert month[a["ref"]] == 120
    assert "credit" not in r.text and "tenant_id" not in r.text


async def test_one_client_leaves_the_companion_out(client, console_world) -> None:
    a = console_world["a"]
    await _spend(a)
    body = (
        await client.get(f"/console/usage/spend?days=7&client={a['ref']}", headers=a["headers"]())
    ).json()
    assert body["series_cents"][-1] == 120
    assert [c["external_client_ref"] for c in body["by_client"]] == [a["ref"]]
    assert body["month_cents"] == 120


async def test_another_partners_client_is_the_same_404_and_sees_nothing(
    client, console_world
) -> None:
    a, b = console_world["a"], console_world["b"]
    await _spend(a)
    foreign = await client.get(f"/console/usage/spend?client={a['ref']}", headers=b["headers"]())
    missing = await client.get("/console/usage/spend?client=nope", headers=b["headers"]())
    assert foreign.status_code == missing.status_code == 404
    mine = (await client.get("/console/usage/spend?days=7", headers=b["headers"]())).json()
    assert sum(mine["series_cents"]) == 0 and mine["month_cents"] == 0
