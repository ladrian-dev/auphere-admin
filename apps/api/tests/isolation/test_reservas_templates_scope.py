"""Spec 043, requisito 15.9 — garantía 1: un cliente nunca crea ni lee plantillas
en la WABA de otro.

La pasada que crea las plantillas de Reservas recorre clientes con la base de la
plataforma y entra en cada uno bajo su RLS (``tenant_scoped_session``): lee sus
credenciales (``tenant_credentials`` lleva RLS FORCE) y habla con Meta con ese
token y esa WABA, nada más.

El espejo ``whatsapp_template_status`` **no** lleva RLS (Auphere guarda ahí
también las de su propia WABA): toda lectura tiene que filtrar por la WABA del
cliente de la sesión. B es el cebo: tiene sus seis en el espejo, aprobadas. Si A
leyera el espejo sin filtrar, se daría por completo y no crearía nada; si su
pantalla lo leyera, mostraría aprobadas las de B.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from nexus_worker.streams.reservation_templates_cron import cron_pass

from nexus_api.db.models import AuditLog, WhatsAppTemplateStatus
from tests.conftest import make_reservas
from tests.integration.reservas._meta_templates import (
    SIX,
    FakeMeta,
    seed_creds,
    seed_mirror,
    token_of,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]

WABA_A, WABA_B = "WABA_ISO_A", "WABA_ISO_B"


async def _world(db_session, console_world):
    a, b = console_world["a"], console_world["b"]
    shop_a = await make_reservas(db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"])
    await make_reservas(db_session, partner_id=b["partner_id"], tenant_id=b["tenant_id"])
    await seed_creds(db_session, a["tenant_id"], waba_id=WABA_A)
    await seed_creds(db_session, b["tenant_id"], waba_id=WABA_B)
    for name in SIX:
        await seed_mirror(
            db_session, waba_id=WABA_B, tenant_id=b["tenant_id"], name=name, status="APPROVED"
        )
    return a, b, shop_a


async def test_each_client_talks_to_meta_with_its_own_waba_and_token(
    db_session, console_world
) -> None:
    a, b, _shop = await _world(db_session, console_world)
    meta = FakeMeta()
    # Meta tiene en la WABA de B una del contrato que A no tiene: A no la ve.
    meta.has(WABA_B, "reserva_hueco_libre", status="REJECTED")

    await cron_pass(client=meta)

    # A: las seis, en su WABA y con su token. B (completa en el espejo): nada.
    assert {(w, t) for _o, w, t, _n in meta.calls} == {(WABA_A, token_of(WABA_A))}
    assert sorted(meta.ops("create", WABA_A)) == sorted(SIX)

    rows = (
        await db_session.execute(
            sa.select(WhatsAppTemplateStatus.waba_id, WhatsAppTemplateStatus.tenant_id)
        )
    ).all()
    await db_session.commit()
    by_waba: dict[str, set] = {}
    for waba_id, tenant_id in rows:
        by_waba.setdefault(waba_id, set()).add(tenant_id)
    assert by_waba == {WABA_A: {a["tenant_id"]}, WABA_B: {b["tenant_id"]}}

    audits = (
        await db_session.execute(
            sa.select(AuditLog.tenant_id).where(
                AuditLog.action == "reservations.template_requested"
            )
        )
    ).all()
    await db_session.commit()
    assert {t for (t,) in audits} == {a["tenant_id"]}


async def test_the_screen_never_shows_another_clients_waba(
    client, db_session, console_world
) -> None:
    _a, _b, shop_a = await _world(db_session, console_world)

    r = await client.get("/console/lite/reservas/templates", headers=shop_a["headers"]())

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["approved"] == 0
    assert {i["state"] for i in body["items"]} == {"not_created"}
