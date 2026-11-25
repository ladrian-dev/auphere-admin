"""Spec 076, requisitos 1.3 y 2.1 a 2.3 — la Bandeja lite dice de qué anuncio vino.

``GET /console/lite/inbox/conversations/{id}`` trae ``ad_origin`` con el último
clic del contacto de la conversación en su número: el tipo, el titular y el
enlace. Nunca el ``ctwa_clid``. Sin clic, ``null``. Sin titular, el tipo sigue.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from nexus_api.db.models import CustomerAdReferral
from tests.conftest import make_inbox

pytestmark = pytest.mark.asyncio

BASE = "/console/lite/inbox/conversations"


def _click(w, inbox, i: int, **kw) -> CustomerAdReferral:
    values = {
        "source_type": "ad",
        "source_id": "120200000000000",
        "source_url": "https://fb.me/ad",
        "headline": "Corte + barba",
        "ad_text": "20% esta semana",
        "ctwa_clid": "SECRET-CLICK-ID",
        "clicked_at": datetime.now(UTC) - timedelta(minutes=30),
        **kw,
    }
    return CustomerAdReferral(
        tenant_id=w["tenant_id"],
        customer_id=inbox["customers"][i],
        conversation_id=inbox["conversations"][i],
        channel_id=inbox["channel_id"],
        provider_message_id=f"wamid.{i}.{values['source_id']}.{values['clicked_at'].timestamp()}",
        **values,
    )


async def test_ad_origin_is_the_last_click(client, db_session, console_world) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    db_session.add_all(
        [
            _click(w, inbox, 0, headline="Viejo", clicked_at=datetime.now(UTC) - timedelta(days=9)),
            _click(w, inbox, 0, headline="Corte + barba"),
        ]
    )
    await db_session.commit()

    r = await client.get(f"{BASE}/{inbox['conversations'][0]}", headers=inbox["headers"]())
    assert r.status_code == 200, r.text
    origin = r.json()["ad_origin"]
    assert origin == {"kind": "ad", "headline": "Corte + barba", "url": "https://fb.me/ad"}
    assert "SECRET-CLICK-ID" not in r.text


async def test_no_click_is_null(client, db_session, console_world) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    r = await client.get(f"{BASE}/{inbox['conversations'][0]}", headers=inbox["headers"]())
    assert r.status_code == 200, r.text
    assert r.json()["ad_origin"] is None


async def test_without_headline_the_kind_stays(client, db_session, console_world) -> None:
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    db_session.add(_click(w, inbox, 0, source_type="post", headline=None, source_url=None))
    await db_session.commit()
    r = await client.get(f"{BASE}/{inbox['conversations'][0]}", headers=inbox["headers"]())
    assert r.json()["ad_origin"] == {"kind": "post", "headline": None, "url": None}


async def test_another_contacts_click_is_never_shown(client, db_session, console_world) -> None:
    """Garantía 8: el clic de la conversación 1 no aparece en la 0, aunque los dos
    contactos sean del mismo negocio y del mismo número."""
    w = console_world["a"]
    inbox = await make_inbox(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    db_session.add(_click(w, inbox, 1))
    await db_session.commit()
    r = await client.get(f"{BASE}/{inbox['conversations'][0]}", headers=inbox["headers"]())
    assert r.json()["ad_origin"] is None
