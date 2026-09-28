"""D1: un cliente recién creado tiene **fila de cupo**, y con cero dentro.

El agujero que costó el corte del 31-ago: ``allow_channel_turn`` exige una
fila en ``partner_allocations`` y **nadie la escribía** — ni el wizard, ni
``provision_partner_client``, ni la migración 0094. El único escritor era
``PUT /console/clients/{ref}/allocation``, a mano. Un cliente nuevo nacía
mudo, sin error, sin aviso y con el checklist de Primeros pasos diciendo que
todo iba bien.

Lo que cura ese corte es **que la fila se escriba**, no lo que lleve dentro.
La spec 004 R6 (2026-09-12) sembraba además la cuota entera para que el
cliente contestara el día que nacía; la spec 019 lo revierte a cero (owner,
2026-09-28): 50 000 créditos comprados por alta los repartía el sistema, y
repartirlos es decisión del partner. El cliente nace sin contestar **y se ve
que es así** — que es lo contrario del silencio de agosto.
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


async def test_new_client_is_born_with_a_row_and_zero_credit(client, db_session) -> None:
    """La fila existe; el tope es cero (spec 019, R8.1 y R8.2)."""
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
    assert alloc is not None, (
        "el cliente nació sin fila de cupo: eso es el silencio del 31-ago, "
        "y es lo único que esta parte nunca puede perder"
    )
    assert int(alloc.cap) == 0
    assert int(alloc.remaining) == 0
    # Y el defecto es cero de verdad, no un número que alguien subió sin
    # tocar la spec: R8.1 se afirma contra el ajuste, no contra la fila.
    assert get_settings().partner_default_client_allocation_tokens == 0


async def test_new_client_stays_quiet_until_the_partner_assigns_credit(client, db_session) -> None:
    """El criterio de verdad, ahora en dos tiempos.

    Nace callado —es lo que el owner pidió— pero **se destraba asignando
    crédito y nada más**: sin migraciones, sin tocar otra fila y sin que
    nadie tenga que acordarse de crear la que faltaba. Esa es la diferencia
    con el corte del 31-ago, donde no había fila que subir.
    """
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

    assert await allow_channel_turn(mapping.tenant_id) is False

    alloc = await db_session.scalar(
        sa.select(PartnerAllocation).where(
            PartnerAllocation.partner_id == world["partner_id"],
            PartnerAllocation.tenant_id == mapping.tenant_id,
        )
    )
    assert alloc is not None
    alloc.cap = 50_000
    alloc.remaining = 50_000
    await db_session.commit()

    assert await allow_channel_turn(mapping.tenant_id) is True


async def test_provisioning_survives_an_exhausted_wallet(client, db_session) -> None:
    """Sin saldo, el alta **no falla**: el cliente nace con su fila en cero.

    Lo que aquí se cuida no es el número —desde la spec 019 el defecto es cero
    para todos— sino que un libro vacío no rompa el alta ni la deje a medias.
    El tope es un límite de gasto y no una reserva sobre el saldo: quien
    decide si un turno pasa es ``allow_channel_turn``, que mira el saldo real
    en cada turno.
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
    assert alloc is not None, "sin saldo el alta se quedó sin escribir la fila"
    assert int(alloc.cap) == 0
