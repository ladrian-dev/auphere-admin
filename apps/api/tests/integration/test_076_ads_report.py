"""Spec 076, requisito 3 — el informe de anuncios de un cliente.

``GET /console/clients/{ref}/ads/report?days=7|30|90``:

- **conversaciones** de un anuncio: las conversaciones distintas con un clic de
  ese anuncio en el periodo;
- **reservas**: las del agente (``origin='agent'``), no canceladas, creadas en
  el periodo y atribuidas al último clic de su contacto, en el número de su
  conversación, anterior a la reserva (aunque el clic sea de antes);
- el **importe** de esas reservas, por moneda; sin precio, cuentan sin importe.

La respuesta no lleva campos de cuerpo ni nombres o teléfonos de clientes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text

from nexus_api.db.models import (
    Channel,
    ChannelStatus,
    ChannelType,
    Conversation,
    ConversationStatus,
    Customer,
    CustomerAdReferral,
    Reservation,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

NOW = datetime.now(UTC)
FORBIDDEN = {"body", "text", "message", "content", "reason", "name", "phone", "identifier"}


async def _scoped(db_session: Any, tenant_id: uuid.UUID) -> None:
    await db_session.execute(
        text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
    )
    await db_session.execute(text("SET LOCAL ROLE nexus_app"))


class Shop:
    """Un número del cliente con contactos, clics y reservas."""

    def __init__(self, db_session: Any, tenant_id: uuid.UUID) -> None:
        self.db = db_session
        self.tenant_id = tenant_id
        self.channel_id = uuid.uuid4()

    async def setup(self) -> Shop:
        async with self.db.begin():
            await _scoped(self.db, self.tenant_id)
            self.db.add(
                Channel(
                    id=self.channel_id,
                    tenant_id=self.tenant_id,
                    type=ChannelType.WHATSAPP,
                    provider="meta",
                    provider_identifier=f"+5699{uuid.uuid4().int % 10**7:07d}",
                    status=ChannelStatus.ACTIVE,
                    config={"phone_number_id": "PN"},
                )
            )
        return self

    async def contact(self) -> tuple[uuid.UUID, uuid.UUID]:
        customer, conversation = uuid.uuid4(), uuid.uuid4()
        async with self.db.begin():
            await _scoped(self.db, self.tenant_id)
            self.db.add(
                Customer(
                    id=customer,
                    tenant_id=self.tenant_id,
                    identifier=f"+5691{uuid.uuid4().int % 10**7:07d}",
                    name="Ana Pérez",
                )
            )
            await self.db.flush()
            self.db.add(
                Conversation(
                    id=conversation,
                    tenant_id=self.tenant_id,
                    channel_id=self.channel_id,
                    customer_id=customer,
                    status=ConversationStatus.OPEN,
                )
            )
        return customer, conversation

    async def click(
        self, customer: uuid.UUID, conversation: uuid.UUID, ad: str | None, at: datetime
    ) -> None:
        async with self.db.begin():
            await _scoped(self.db, self.tenant_id)
            self.db.add(
                CustomerAdReferral(
                    tenant_id=self.tenant_id,
                    customer_id=customer,
                    conversation_id=conversation,
                    channel_id=self.channel_id,
                    provider_message_id=f"wamid.{uuid.uuid4().hex}",
                    source_type="ad",
                    source_id=ad,
                    source_url=f"https://fb.me/{ad}" if ad else None,
                    headline=f"Anuncio {ad}" if ad else None,
                    ctwa_clid="CLICK",
                    clicked_at=at,
                )
            )

    async def booking(
        self,
        customer: uuid.UUID,
        conversation: uuid.UUID,
        at: datetime,
        *,
        price: int | None = 15000,
        currency: str | None = "CLP",
        status: str = "confirmed",
        origin: str = "agent",
    ) -> None:
        async with self.db.begin():
            await _scoped(self.db, self.tenant_id)
            self.db.add(
                Reservation(
                    tenant_id=self.tenant_id,
                    mode="capacity",
                    status=status,
                    starts_at=at + timedelta(days=3),
                    ends_at=at + timedelta(days=3, hours=1),
                    origin=origin,
                    channel="whatsapp" if origin == "agent" else "phone",
                    created_by_kind="agent" if origin == "agent" else "person",
                    price_minor=price,
                    currency=currency,
                    customer_id=customer,
                    conversation_id=conversation,
                    contact_name="Ana Pérez",
                    created_at=at,
                )
            )


async def _report(client: Any, w: dict[str, Any], days: int = 30) -> Any:
    return await client.get(
        f"/console/clients/{w['ref']}/ads/report?days={days}", headers=w["headers"]()
    )


def _walk_keys(obj: Any) -> set[str]:
    if isinstance(obj, dict):
        return set(obj) | {k for v in obj.values() for k in _walk_keys(v)}
    if isinstance(obj, list):
        return {k for v in obj for k in _walk_keys(v)}
    return set()


async def test_rows_per_ad(client, db_session, console_world) -> None:
    w = console_world["a"]
    shop = await Shop(db_session, w["tenant_id"]).setup()
    c1, v1 = await shop.contact()
    c2, v2 = await shop.contact()
    c3, v3 = await shop.contact()
    await shop.click(c1, v1, "A", NOW - timedelta(days=2))
    await shop.click(c2, v2, "A", NOW - timedelta(days=1))
    await shop.click(c3, v3, "B", NOW - timedelta(days=1))
    await shop.booking(c1, v1, NOW - timedelta(days=2) + timedelta(minutes=5), price=15000)
    await shop.booking(c2, v2, NOW - timedelta(hours=20), price=None, currency=None)

    r = await _report(client, w)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["days"] == 30
    rows = {row["ad_id"]: row for row in body["rows"]}
    assert rows["A"]["conversations"] == 2
    assert rows["A"]["bookings"] == 2
    assert rows["A"]["amounts"] == [{"currency": "CLP", "amount_minor": 15000}]
    assert rows["A"]["ad_headline"] == "Anuncio A" and rows["A"]["ad_url"] == "https://fb.me/A"
    assert rows["A"]["ad_kind"] == "ad"
    assert rows["B"]["conversations"] == 1 and rows["B"]["bookings"] == 0
    assert rows["B"]["amounts"] == []
    # Orden: más reservas primero.
    assert [row["ad_id"] for row in body["rows"]] == ["A", "B"]
    # Sin campos de cuerpo ni datos de la persona.
    assert not _walk_keys(body) & FORBIDDEN
    assert "Ana" not in r.text


async def test_cancelled_and_console_bookings_do_not_count(
    client, db_session, console_world
) -> None:
    w = console_world["a"]
    shop = await Shop(db_session, w["tenant_id"]).setup()
    c1, v1 = await shop.contact()
    await shop.click(c1, v1, "A", NOW - timedelta(days=1))
    await shop.booking(c1, v1, NOW - timedelta(hours=20), status="cancelled")
    await shop.booking(c1, v1, NOW - timedelta(hours=19), origin="person")
    (row,) = (await _report(client, w)).json()["rows"]
    assert row["bookings"] == 0 and row["amounts"] == []


async def test_booking_counts_for_the_last_click_before_it(
    client, db_session, console_world
) -> None:
    w = console_world["a"]
    shop = await Shop(db_session, w["tenant_id"]).setup()
    c1, v1 = await shop.contact()
    # Clic de A hace 40 días (fuera del periodo), reserva hoy: cuenta para A.
    await shop.click(c1, v1, "A", NOW - timedelta(days=40))
    await shop.booking(c1, v1, NOW - timedelta(hours=5))
    # Un clic de B *después* de la reserva no se la lleva.
    await shop.click(c1, v1, "B", NOW - timedelta(hours=1))
    rows = {row["ad_id"]: row for row in (await _report(client, w)).json()["rows"]}
    assert rows["A"]["bookings"] == 1 and rows["A"]["conversations"] == 0
    assert rows["B"]["bookings"] == 0 and rows["B"]["conversations"] == 1


async def test_clicks_without_ad_id_group_together(client, db_session, console_world) -> None:
    w = console_world["a"]
    shop = await Shop(db_session, w["tenant_id"]).setup()
    c1, v1 = await shop.contact()
    await shop.click(c1, v1, None, NOW - timedelta(days=1))
    (row,) = (await _report(client, w)).json()["rows"]
    assert row["ad_id"] is None and row["conversations"] == 1


@pytest.mark.parametrize("days", [0, 1, 14, 365])
async def test_only_the_three_periods(client, console_world, days: int) -> None:
    r = await _report(client, console_world["a"], days=days)
    assert r.status_code == 422


async def test_empty_period(client, console_world) -> None:
    r = await _report(client, console_world["a"], days=7)
    assert r.status_code == 200 and r.json() == {"days": 7, "rows": []}
