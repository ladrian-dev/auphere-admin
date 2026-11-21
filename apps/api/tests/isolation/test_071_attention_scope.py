"""Garantía 1 sobre «Lo que te necesita» — spec 071 (T004; encabezado de la spec).

La lista junta datos del partner (la cuenta, la partida, el cobro) y de cada uno de sus
clientes (bolsas, canales, agentes), siempre con el contexto del partner que pregunta:
el partner sale del principal y los clientes, de ``partner_tenants`` de ese partner. Se
prueba barriendo, no enumerando: dos partners con la consola nueva, los dos en todas las
condiciones a la vez, y en cada respuesta de uno se busca cualquier rastro del otro:

- ``GET /console/attention``, ``/console/home`` (``panel``) y la campana
  (``/console/notifications`` y su contador) de A no dicen ni un ``ref`` ni un nombre de
  cliente de B, ni una cifra de la cuenta de B;
- «Marcar todo como leído» de A no toca los avisos de B;
- ``resolve_cleared`` de A no resuelve ningún aviso de B, tampoco uno de B que lleve
  el mismo ``ref`` que un cliente de A (los ``ref`` son del partner, no únicos).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.db.models import PartnerTenant
from nexus_api.services.attention_live import resolve_cleared_detached
from tests.integration.attention._attention_world import (
    UNIT,
    MoneyWorld,
    assign,
    billing_state,
    build_spent,
    money_world,
    notice,
    notice_state,
    set_purchased,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]


async def _in_trouble(client: Any, db_session: Any, label: str, purchased: int) -> MoneyWorld:
    world = await money_world(db_session, roles=())
    async with db_session.begin():
        for c in (world.es, world.us):
            await db_session.execute(
                sa.update(PartnerTenant)
                .where(PartnerTenant.tenant_id == c.tenant_id)
                .values(client_name=f"Secreto {label} {c.country}")
            )
    await assign(client, world, world.us.ref, 10 * UNIT)
    await build_spent(db_session, world, 50 * UNIT)
    await set_purchased(db_session, world, purchased)
    await billing_state(db_session, world.partner_id, "payment_failed")
    return world


def _foreign_marks(world: MoneyWorld, label: str, purchased: int) -> list[str]:
    return [
        world.es.ref,
        world.us.ref,
        f"Secreto {label}",
        str(world.partner_id),
        str(world.es.tenant_id),
        str(world.us.tenant_id),
        f'"amount_micros":{purchased}',
    ]


async def test_neither_partner_sees_the_others_list_panel_or_bell(
    client: Any, db_session: Any
) -> None:
    a = await _in_trouble(client, db_session, "A", 111_111)
    b = await _in_trouble(client, db_session, "B", 222_222)
    for world, kind in ((a, "client.wallet.empty"), (b, "client.wallet.empty")):
        await notice(db_session, world.partner_id, kind, ref=world.es.ref, severity="critical")
        await notice(db_session, world.partner_id, "wallet.low")
        await notice(db_session, world.partner_id, "client.activated", ref=world.us.ref)

    pairs = ((a, b, "B", 222_222), (b, a, "A", 111_111))
    for me, other, other_label, other_purchased in pairs:
        listed = await client.get("/console/attention", headers=me.headers())
        assert listed.status_code == 200, listed.text
        items = listed.json()["items"]
        assert {i["code"] for i in items} >= {
            "billing_payment_failed",
            "build_cap_exhausted",
            "account_low",
            "no_balance",
        }, "las dos en todas las condiciones: el barrido no pasa en falso"
        refs = {i["external_client_ref"] for i in items if i["scope"] == "client"}
        assert refs <= {me.es.ref, me.us.ref}
        mine = (me.es.ref, me.us.ref)
        assert all(
            i["href"].startswith(("/clients/" + mine[0], "/clients/" + mine[1]))
            for i in items
            if i["scope"] == "client"
        )

        home = await client.get("/console/home", headers=me.headers())
        bell = await client.get("/console/notifications", headers=me.headers())
        count = await client.get("/console/notifications/unread-count", headers=me.headers())
        assert home.json()["panel"]["attention"] == items
        bell_refs = {n["external_client_ref"] for n in bell.json()["items"]} - {None}
        assert bell_refs <= {me.es.ref, me.us.ref}
        assert count.json() == {"unread": 1}, "solo su informativo"
        for resp in (listed, home, bell, count):
            text = resp.text.replace(" ", "")
            for mark in _foreign_marks(other, other_label, other_purchased):
                assert mark not in text, (resp.request.url.path, mark)


async def test_read_all_and_resolving_stay_inside_the_partner(client: Any, db_session: Any) -> None:
    a = await _in_trouble(client, db_session, "A", 100 * UNIT)
    b = await _in_trouble(client, db_session, "B", 100 * UNIT)
    # A tiene saldo en EE. UU.; B tiene ese mismo «ref» de A en un aviso suyo.
    a_cleared = await notice(
        db_session, a.partner_id, "client.wallet.empty", ref=a.us.ref, severity="critical"
    )
    b_same_ref = await notice(
        db_session, b.partner_id, "client.wallet.empty", ref=a.us.ref, severity="critical"
    )
    b_own = await notice(
        db_session, b.partner_id, "client.wallet.empty", ref=b.us.ref, severity="critical"
    )
    b_info = await notice(db_session, b.partner_id, "member.joined")

    assert (
        await client.post("/console/notifications/read-all", headers=a.headers())
    ).status_code == 200
    assert (
        await client.get("/console/notifications/unread-count", headers=b.headers())
    ).json() == {"unread": 1}, "el informativo de B sigue sin leer"

    await resolve_cleared_detached(a.partner_id)
    assert (await notice_state(db_session, a_cleared)).resolved
    for untouched in (b_same_ref, b_own, b_info):
        state = await notice_state(db_session, untouched)
        assert not state.resolved and state.dedupe_key is not None

    # Y un partner que no existe no resuelve nada de nadie.
    assert await resolve_cleared_detached(uuid.uuid4()) == 0
    assert not (await notice_state(db_session, b_own)).resolved
