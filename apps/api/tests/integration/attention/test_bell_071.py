"""Spec 071, T005 — la campana con «Ahora» y «Anteriores» (requisitos 3.1 y 3.3;
``contracts/api.md`` §Avisos guardados).

Los avisos de condición (tabla de spec §2.1) los cuenta «Ahora», la lista viva: el
contador de la campana deja de contarlos y «Marcar todo como leído» no los toca, porque
se arreglan, no se leen. Cada aviso dice si es de condición (``condition``). La consola
de antes, sin «Ahora», sigue como hoy (research.md §R6).
"""

from __future__ import annotations

from typing import Any

import pytest

from ._attention_world import money_world, notice

pytestmark = [pytest.mark.integration]

BELL = "/console/notifications"


async def test_the_bell_counts_only_what_is_read_not_what_is_fixed(
    client: Any, db_session: Any
) -> None:
    world = await money_world(db_session, roles=())
    await notice(db_session, world.partner_id, "channel.problem", ref=world.es.ref)
    await notice(db_session, world.partner_id, "wallet.low")
    await notice(db_session, world.partner_id, "client.activated", ref=world.es.ref)
    await notice(db_session, world.partner_id, "client.wallet.not_enough", ref=world.us.ref)
    headers = world.headers  # una ficha por llamada

    count = await client.get(f"{BELL}/unread-count", headers=headers())
    assert count.status_code == 200, count.text
    assert count.json() == {"unread": 2}, "los dos informativos"

    listed = await client.get(BELL, headers=headers())
    assert listed.status_code == 200, listed.text
    page = listed.json()
    assert page["unread"] == 2, "el mismo número en la página"
    flags = {n["kind"]: n["condition"] for n in page["items"]}
    assert flags == {
        "channel.problem": True,
        "wallet.low": True,
        "client.activated": False,
        "client.wallet.not_enough": False,
    }

    marked = await client.post(f"{BELL}/read-all", headers=headers())
    assert marked.json() == {"marked": 2}, "solo los informativos"
    assert (await client.get(f"{BELL}/unread-count", headers=headers())).json() == {"unread": 0}
    items = (await client.get(BELL, headers=headers())).json()["items"]
    still = {n["kind"]: n["read"] for n in items if n["condition"]}
    assert still == {"channel.problem": False, "wallet.low": False}, "se arreglan, no se leen"


async def test_the_old_console_bell_is_unchanged(
    client: Any, db_session: Any, console_world: dict[str, Any]
) -> None:
    a = console_world["a"]
    await notice(db_session, a["partner_id"], "channel.problem", ref=a["ref"])
    await notice(db_session, a["partner_id"], "member.joined")
    headers = a["headers"]
    assert (await client.get(f"{BELL}/unread-count", headers=headers())).json() == {"unread": 2}
    page = (await client.get(BELL, headers=headers())).json()
    assert {n["condition"] for n in page["items"]} == {False}
    assert (await client.post(f"{BELL}/read-all", headers=headers())).json() == {"marked": 2}
