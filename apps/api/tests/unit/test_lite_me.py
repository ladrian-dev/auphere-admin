"""Spec 030 — ``GET /console/lite/me`` (R2.1, R4.6).

Lo que la consola lite necesita saber de quién entra para pintar su
armazón: la persona, su negocio, sus módulos, sus canales y a quién pedir más
saldo. Nada del partner salvo su nombre, y solo para eso.
"""

from __future__ import annotations

import pytest

from nexus_api.config import get_settings
from nexus_api.db.models import Partner
from tests.conftest import add_client_member, make_client_access

pytestmark = pytest.mark.asyncio

ME = "/console/lite/me"


async def test_me_describes_the_client_console(client, db_session, console_world) -> None:
    w = console_world["a"]
    await make_client_access(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"], modules=("panel", "usage")
    )
    member = await add_client_member(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"]
    )
    resp = await client.get(ME, headers=member["headers"]())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["user"]["name"] == "Valeria Ríos"
    assert body["client"] == {"name": "Client A One", "modules": ["panel", "usage"]}
    assert body["balance_contact"] == {"kind": "partner", "name": "Console Partner A"}
    assert body["channels"] == []
    # Nada que identifique al tenant ni al partner por id.
    flat = resp.text
    assert str(w["tenant_id"]) not in flat
    assert str(w["partner_id"]) not in flat


async def test_direct_client_asks_auphere(
    client, db_session, console_world, monkeypatch: pytest.MonkeyPatch
) -> None:
    w = console_world["a"]
    partner = await db_session.get(Partner, w["partner_id"])
    assert partner is not None
    monkeypatch.setattr(get_settings(), "auphere_partner_slugs", f"otro, {partner.slug}")
    await make_client_access(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    member = await add_client_member(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"]
    )
    resp = await client.get(ME, headers=member["headers"]())
    assert resp.json()["balance_contact"] == {"kind": "auphere", "name": "Auphere"}


async def test_partner_member_gets_403(client, db_session, console_world) -> None:
    w = console_world["a"]
    await make_client_access(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    assert (await client.get(ME, headers=w["headers"]())).status_code == 403


async def test_me_brings_the_business_hours(client, db_session, console_world) -> None:
    """Spec 045 R5.1: la zona, el horario canónico y su frase ya escrita."""
    from nexus_api.db.models import Tenant

    w = console_world["a"]
    tenant = await db_session.get(Tenant, w["tenant_id"])
    tenant.timezone = "America/Santiago"
    tenant.business_hours = {
        **{
            d: [{"from": "09:00", "to": "19:00"}]
            for d in ("monday", "tuesday", "wednesday", "thursday", "friday")
        },
        "saturday": [{"from": "09:00", "to": "14:00"}],
        "sunday": [],
    }
    await db_session.commit()
    await make_client_access(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    member = await add_client_member(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"]
    )

    body = (await client.get(ME, headers=member["headers"]())).json()

    assert body["business"]["timezone"] == "America/Santiago"
    assert body["business"]["hours"]["saturday"] == [{"from": "09:00", "to": "14:00"}]
    assert body["business"]["hours"]["sunday"] == []
    assert body["business"]["hours_label"].startswith("Lunes a viernes 09:00")

    en = (await client.get(ME, headers={**member["headers"](), "Accept-Language": "en-GB"})).json()
    assert en["business"]["hours_label"].startswith("Monday to Friday 09:00")


async def test_me_without_hours_says_so(client, db_session, console_world) -> None:
    w = console_world["a"]
    await make_client_access(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    member = await add_client_member(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"]
    )
    business = (await client.get(ME, headers=member["headers"]())).json()["business"]
    assert business["hours"] is None
    assert business["hours_label"] is None
