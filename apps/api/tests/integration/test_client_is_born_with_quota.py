"""D1: un cliente recién creado puede atender sin pasar por Consumo.

El agujero que costó el corte del 31-ago: ``allow_channel_turn`` exige una
fila en ``partner_allocations`` y **nadie la escribía** — ni el wizard, ni
``provision_partner_client``, ni la migración 0094. El único escritor era
``PUT /console/clients/{ref}/allocation``, a mano. Un cliente nuevo nacía
mudo, sin error, sin aviso y con el checklist de Primeros pasos diciendo que
todo iba bien.

El criterio de «hecho» de D1 no es que exista la fila: es que el canal abra.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from nexus_api.config import get_settings
from nexus_api.core.partner_keys import generate_api_key
from nexus_api.db.models import Partner, PartnerAllocation, PartnerApiKey, PartnerTenant

pytestmark = pytest.mark.asyncio


async def _bare_partner(db_session) -> dict:
    """Partner sin blueprint: el camino más corto a un cliente nuevo."""
    partner_id = uuid.uuid4()
    generated = generate_api_key()
    db_session.add(
        Partner(
            id=partner_id,
            name="Cuota Test",
            slug=f"cuota-{partner_id.hex[:6]}",
            auto_activate=True,
        )
    )
    db_session.add(
        PartnerApiKey(
            id=uuid.uuid4(),
            partner_id=partner_id,
            prefix_snippet=generated.prefix_snippet,
            key_hash=generated.key_hash,
            scopes=["provision"],
            allowed_origins=["https://partner.example"],
        )
    )
    await db_session.commit()
    return {"partner_id": partner_id, "key": generated.plaintext}


def _body(ref: str) -> dict:
    return {
        "external_client_ref": ref,
        "name": "Panadería La Espiga",
        "timezone": "Europe/Madrid",
    }


async def test_new_client_gets_the_default_quota(client, db_session) -> None:
    world = await _bare_partner(db_session)
    ref = f"cliente-{uuid.uuid4().hex[:8]}"

    resp = await client.post(
        "/v1/partners/clients",
        json=_body(ref),
        headers={"Authorization": f"Bearer {world['key']}"},
    )
    assert resp.status_code in (200, 201), resp.text

    mapping = await db_session.get(PartnerTenant, (world["partner_id"], ref))
    assert mapping is not None
    alloc = await db_session.scalar(
        sa.select(PartnerAllocation).where(
            PartnerAllocation.partner_id == world["partner_id"],
            PartnerAllocation.tenant_id == mapping.tenant_id,
        )
    )
    assert alloc is not None, "el cliente nació sin cuota: vuelve a nacer mudo"
    expected = get_settings().partner_default_client_allocation_tokens
    assert int(alloc.cap) == expected
    assert int(alloc.remaining) == expected


async def test_new_client_can_actually_answer(client, db_session) -> None:
    """El criterio de verdad: la puerta del canal abre sin tocar Consumo."""
    from nexus_api.metering.wallet import allow_channel_turn

    world = await _bare_partner(db_session)
    ref = f"cliente-{uuid.uuid4().hex[:8]}"
    resp = await client.post(
        "/v1/partners/clients",
        json=_body(ref),
        headers={"Authorization": f"Bearer {world['key']}"},
    )
    assert resp.status_code in (200, 201), resp.text
    mapping = await db_session.get(PartnerTenant, (world["partner_id"], ref))
    assert mapping is not None

    assert await allow_channel_turn(mapping.tenant_id) is True


async def test_provisioning_survives_an_exhausted_wallet(client, db_session) -> None:
    """Sin disponible se siembra lo que quede (puede ser 0) y el alta NO falla.

    Una fila con cap 0 es visible en Consumo y explicable; la ausencia de
    fila es el silencio.
    """
    from nexus_api.db.models import PartnerWallet

    world = await _bare_partner(db_session)
    wallet = await db_session.get(PartnerWallet, world["partner_id"])
    if wallet is None:
        wallet = PartnerWallet(
            partner_id=world["partner_id"], included_remaining=0, purchased_remaining=0
        )
        db_session.add(wallet)
    else:
        wallet.included_remaining = 0
        wallet.purchased_remaining = 0
    await db_session.commit()

    ref = f"cliente-{uuid.uuid4().hex[:8]}"
    resp = await client.post(
        "/v1/partners/clients",
        json=_body(ref),
        headers={"Authorization": f"Bearer {world['key']}"},
    )
    assert resp.status_code in (200, 201), resp.text
    mapping = await db_session.get(PartnerTenant, (world["partner_id"], ref))
    assert mapping is not None
    alloc = await db_session.scalar(
        sa.select(PartnerAllocation).where(
            PartnerAllocation.partner_id == world["partner_id"],
            PartnerAllocation.tenant_id == mapping.tenant_id,
        )
    )
    assert alloc is not None
    assert int(alloc.cap) == 0
