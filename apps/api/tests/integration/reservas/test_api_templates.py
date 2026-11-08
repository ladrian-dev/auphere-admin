"""Spec 043, requisito 15.7 — los Ajustes de Reservas dicen cómo van sus plantillas.

``GET /console/lite/reservas/templates`` lee el espejo que alimenta el webhook
de Meta (y la pasada que las crea), nunca llama a Meta: las seis, cada una
aprobada, en revisión, rechazada (con el motivo de Meta en un código que la
pantalla traduce), en pausa o sin crear (y por qué).
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.conftest import make_reservas
from tests.integration.reservas._meta_templates import SIX, seed_creds, seed_mirror

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

URL = "/console/lite/reservas/templates"
WABA = "WABA_A"


@pytest.fixture
async def shop(db_session, console_world) -> dict[str, Any]:
    w = console_world["a"]
    return await make_reservas(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])


def _by_name(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {i["name"]: i for i in body["items"]}


async def test_without_a_whatsapp_number_none_can_be_created(client, shop) -> None:
    r = await client.get(URL, headers=shop["headers"]())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["whatsapp"] is False
    assert body["approved"] == 0
    assert [i["name"] for i in body["items"]] == list(SIX)
    assert {(i["state"], i["why_not_created"]) for i in body["items"]} == {
        ("not_created", "no_whatsapp")
    }


async def test_with_a_number_and_nothing_yet_they_are_on_their_way(
    client, shop, db_session
) -> None:
    await seed_creds(db_session, shop["tenant_id"], waba_id=WABA)
    r = await client.get(URL, headers=shop["headers"]())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["whatsapp"] is True
    assert {(i["state"], i["why_not_created"]) for i in body["items"]} == {
        ("not_created", "on_its_way")
    }


async def test_each_template_says_its_state_and_the_rejection_reason(
    client, shop, db_session
) -> None:
    tid = shop["tenant_id"]
    await seed_creds(db_session, tid, waba_id=WABA)
    rows = {
        "reserva_confirmada": ("APPROVED", "es", None),
        "reserva_pide_confirmacion": ("APPROVED", "es_MX", None),
        "reserva_recordatorio": ("PENDING", "es", None),
        "reserva_cambiada": ("REJECTED", "es", "INVALID_FORMAT"),
        "reserva_cancelada": ("PAUSED", "es", None),
    }
    for name, (status, language, reason) in rows.items():
        await seed_mirror(
            db_session,
            waba_id=WABA,
            tenant_id=tid,
            name=name,
            status=status,
            language=language,
            reason=reason,
        )
    # Una que solo existe en inglés no cuenta: el outbox solo usa las ``es*``.
    await seed_mirror(
        db_session,
        waba_id=WABA,
        tenant_id=tid,
        name="reserva_hueco_libre",
        status="APPROVED",
        language="en_US",
    )

    r = await client.get(URL, headers=shop["headers"]())
    assert r.status_code == 200, r.text
    body = r.json()
    items = _by_name(body)
    assert body["approved"] == 2
    assert items["reserva_confirmada"]["state"] == "approved"
    assert items["reserva_pide_confirmacion"]["state"] == "approved"
    assert items["reserva_recordatorio"]["state"] == "in_review"
    assert items["reserva_cambiada"]["state"] == "rejected"
    assert items["reserva_cambiada"]["rejection"] == "invalid_format"
    assert items["reserva_cancelada"]["state"] == "paused"
    assert items["reserva_hueco_libre"]["state"] == "not_created"
    assert items["reserva_hueco_libre"]["why_not_created"] == "on_its_way"
    assert all(i["rejection"] is None for n, i in items.items() if n != "reserva_cambiada")


async def test_a_reason_in_meta_words_travels_as_a_code(client, shop, db_session) -> None:
    """El texto libre de Meta no llega a la persona del cliente: llega su código."""
    tid = shop["tenant_id"]
    await seed_creds(db_session, tid, waba_id=WABA)
    await seed_mirror(
        db_session,
        waba_id=WABA,
        tenant_id=tid,
        name="reserva_cancelada",
        status="REJECTED",
        reason="The template contains content that violates our policies about +56911112222",
    )
    r = await client.get(URL, headers=shop["headers"]())
    item = _by_name(r.json())["reserva_cancelada"]
    assert item["rejection"] == "other"
    assert "violates" not in r.text


async def test_a_template_deleted_in_meta_is_not_created_and_says_why(
    client, shop, db_session
) -> None:
    tid = shop["tenant_id"]
    await seed_creds(db_session, tid, waba_id=WABA)
    await seed_mirror(
        db_session, waba_id=WABA, tenant_id=tid, name="reserva_recordatorio", status="DELETED"
    )
    item = _by_name((await client.get(URL, headers=shop["headers"]())).json())[
        "reserva_recordatorio"
    ]
    assert (item["state"], item["why_not_created"]) == ("not_created", "deleted")
