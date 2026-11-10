"""Spec 055: las correcciones de QA de la consola, en lo que toca a la API.

- **Moneda** (requisitos 2 y 3): una sola moneda de precios por negocio, sin
  inventar ninguna, y los servicios la siguen con el mismo número, con confirmación.
- **«Señal»** (requisito 6): lo que lee el agente usa la misma etiqueta.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import AuditLog, Reservation, ReservationService
from nexus_api.services.business import compilation, services_catalog

from ._business_world import Biz, if_match, new_business

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def biz(client: Any, db_session: AsyncSession, console_world: dict[str, Any]) -> Biz:
    """Barbería Cultor, en Madrid y en euros."""
    return await new_business(client, db_session, console_world, name="Barbería Cultor")


def service_body(name: str = "Corte", amount: int | None = 1550, **over: Any) -> dict[str, Any]:
    price = {"kind": "amount", "amount_minor": amount} if amount is not None else {"kind": "none"}
    return {"name": name, "bookable": True, "duration_min": 30, "price": price, **over}


async def get_section(client: Any, biz: Biz, section: str) -> dict[str, Any]:
    resp = await client.get(f"{biz.url}/{section}", headers=biz.headers())
    assert resp.status_code == 200, resp.text
    out: dict[str, Any] = resp.json()
    return out


async def add_service(client: Any, biz: Biz, **kw: Any) -> dict[str, Any]:
    now = await get_section(client, biz, "services")
    resp = await client.post(
        f"{biz.url}/services",
        json=service_body(**kw),
        headers={**biz.headers(), **if_match(now["revision"])},
    )
    assert resp.status_code == 201, resp.text
    out: dict[str, Any] = resp.json()
    return out


async def put_currency(client: Any, biz: Biz, currency: str, *, confirm: bool = False) -> Any:
    basics = await get_section(client, biz, "basics")
    body: dict[str, Any] = {"price_currency": currency}
    if confirm:
        body["confirm_price_change"] = True
    return await client.put(
        f"{biz.url}/basics", json=body, headers={**biz.headers(), **if_match(basics["revision"])}
    )


async def without_currency(db_session: AsyncSession, biz: Biz) -> None:
    from nexus_api.db.models import BusinessProfile, Tenant

    async with tenant_scoped_session(db_session, biz.tenant_id):
        profile = await db_session.get(BusinessProfile, biz.tenant_id)
        tenant = await db_session.get(Tenant, biz.tenant_id)
        assert profile is not None and tenant is not None
        profile.price_currency = None
        tenant.market = None


class TestOneCurrencyPerBusiness:
    async def test_a_new_service_takes_the_business_currency(self, client: Any, biz: Biz) -> None:
        out = await add_service(client, biz)
        assert out["currency"] == "EUR" and out["exponent"] == 2
        assert out["items"][0]["currency"] == "EUR" and out["items"][0]["exponent"] == 2

    async def test_without_a_currency_none_is_invented(
        self, client: Any, biz: Biz, db_session: AsyncSession
    ) -> None:
        await without_currency(db_session, biz)
        now = await get_section(client, biz, "services")
        assert now["currency"] == "XXX" and now["currency_set"] is False
        resp = await client.post(
            f"{biz.url}/services",
            json=service_body(),
            headers={**biz.headers(), **if_match(now["revision"])},
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["detail"]["code"] == "price_currency_required"

    async def test_a_service_without_a_price_needs_no_currency(
        self, client: Any, biz: Biz, db_session: AsyncSession
    ) -> None:
        await without_currency(db_session, biz)
        out = await add_service(client, biz, amount=None)
        assert out["currency_set"] is False and out["items"][0]["price"] == {"kind": "none"}

    async def test_the_currency_chosen_in_the_modal_stays_for_the_whole_business(
        self, client: Any, biz: Biz, db_session: AsyncSession
    ) -> None:
        await without_currency(db_session, biz)
        out = await add_service(client, biz, price_currency="USD")
        assert out["currency"] == "USD" and out["items"][0]["currency"] == "USD"
        assert (await get_section(client, biz, "basics"))["price_currency"] == "USD"

    async def test_editing_an_amount_moves_a_stray_row_to_the_business_currency(
        self, client: Any, biz: Biz, db_session: AsyncSession
    ) -> None:
        out = await add_service(client, biz)
        service_id = uuid.UUID(out["items"][0]["id"])
        async with tenant_scoped_session(db_session, biz.tenant_id):
            svc = await db_session.get(ReservationService, service_id)
            assert svc is not None
            svc.currency = "CLP"
        now = await get_section(client, biz, "services")
        assert now["items"][0]["currency"] == "CLP" and now["items"][0]["exponent"] == 0
        resp = await client.patch(
            f"{biz.url}/services/{service_id}",
            json={"price": {"kind": "amount", "amount_minor": 2000}},
            headers={**biz.headers(), **if_match(now["revision"])},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["items"][0]["currency"] == "EUR"


class TestChangingTheCurrency:
    async def test_it_asks_how_many_change_and_writes_nothing(self, client: Any, biz: Biz) -> None:
        await add_service(client, biz, name="Corte")
        await add_service(client, biz, name="Barba")
        await add_service(client, biz, name="Consulta", amount=None)
        resp = await put_currency(client, biz, "USD")
        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"] == {"code": "prices_would_change", "count": 2, "rounds": False}
        assert (await get_section(client, biz, "basics"))["price_currency"] == "EUR"
        items = (await get_section(client, biz, "services"))["items"]
        assert {i["currency"] for i in items} == {"EUR"}

    async def test_without_priced_services_it_does_not_ask(self, client: Any, biz: Biz) -> None:
        await add_service(client, biz, amount=None)
        assert (await put_currency(client, biz, "USD")).status_code == 200

    async def test_confirming_keeps_the_same_number(self, client: Any, biz: Biz) -> None:
        await add_service(client, biz)
        revision = (await get_section(client, biz, "services"))["revision"]
        resp = await put_currency(client, biz, "USD", confirm=True)
        assert resp.status_code == 200, resp.text
        assert resp.json()["price_currency"] == "USD"
        out = await get_section(client, biz, "services")
        assert out["items"][0]["currency"] == "USD"
        assert out["items"][0]["price"]["amount_minor"] == 1550
        # Un modal abierto con la revisión de antes choca con su conflicto.
        assert out["revision"] > revision

    async def test_more_decimals_keep_the_visible_number(self, client: Any, biz: Biz) -> None:
        resp = await put_currency(client, biz, "CLP", confirm=True)
        assert resp.status_code == 200, resp.text
        await add_service(client, biz, amount=15000)
        assert (await put_currency(client, biz, "USD", confirm=True)).status_code == 200
        item = (await get_section(client, biz, "services"))["items"][0]
        assert item["price"]["amount_minor"] == 1500000 and item["exponent"] == 2

    async def test_fewer_decimals_round_and_say_so(self, client: Any, biz: Biz) -> None:
        await add_service(client, biz, amount=1550)
        resp = await put_currency(client, biz, "CLP")
        assert resp.json()["detail"] == {"code": "prices_would_change", "count": 1, "rounds": True}
        assert (await put_currency(client, biz, "CLP", confirm=True)).status_code == 200
        item = (await get_section(client, biz, "services"))["items"][0]
        assert item["price"]["amount_minor"] == 16 and item["exponent"] == 0

    async def test_it_leaves_an_audit_entry_with_how_many(
        self, client: Any, biz: Biz, db_session: AsyncSession
    ) -> None:
        await add_service(client, biz)
        assert (await put_currency(client, biz, "USD", confirm=True)).status_code == 200
        async with tenant_scoped_session(db_session, biz.tenant_id):
            row = await db_session.scalar(
                sa.select(AuditLog).where(
                    AuditLog.tenant_id == biz.tenant_id,
                    AuditLog.action == "business.price_currency_changed",
                )
            )
        assert row is not None
        assert row.before_json == {"currency": "EUR"}
        assert row.after_json == {"currency": "USD", "services": 1}

    async def test_a_reservation_already_made_keeps_its_money(
        self, client: Any, biz: Biz, db_session: AsyncSession
    ) -> None:
        await add_service(client, biz)
        starts = datetime.now(UTC) + timedelta(days=1)
        async with tenant_scoped_session(db_session, biz.tenant_id):
            booking = Reservation(
                tenant_id=biz.tenant_id,
                mode="capacity",
                party_size=2,
                status="confirmed",
                starts_at=starts,
                ends_at=starts + timedelta(minutes=30),
                origin="person",
                channel="phone",
                created_by_kind="person",
                contact_name="Ana",
                contact_phone="+34600000000",
                price_minor=1550,
                currency="EUR",
            )
            db_session.add(booking)
            await db_session.flush()
            booking_id = booking.id
        assert (await put_currency(client, biz, "CLP", confirm=True)).status_code == 200
        async with tenant_scoped_session(db_session, biz.tenant_id):
            row = await db_session.get(Reservation, booking_id, populate_existing=True)
        assert row is not None and row.currency == "EUR" and row.price_minor == 1550


class TestRescale:
    @pytest.mark.parametrize(
        ("amount", "source", "target", "expected"),
        [
            (1550, "EUR", "USD", 1550),
            (15000, "CLP", "USD", 1500000),
            (1550, "USD", "CLP", 16),
            (1549, "USD", "CLP", 15),
            (1000, "KWD", "USD", 100),
        ],
    )
    async def test_rescale(self, amount: int, source: str, target: str, expected: int) -> None:
        assert services_catalog.rescale(amount, source, target) == expected


class TestDepositLabel:
    async def test_the_agent_reads_the_same_label_and_the_value_stays(self) -> None:
        facts = compilation.Facts(name="Cultor", policies=(("Señal o anticipo", "10 EUR"),))
        block = compilation.render_facts(facts)
        assert "Señal o anticipo" in block and "10 EUR" in block


class TestCategories:
    async def test_a_category_is_trimmed_and_shared_whatever_its_case(
        self, client: Any, biz: Biz
    ) -> None:
        await add_service(client, biz, name="Básico", category="  Corte ")
        out = await add_service(client, biz, name="Heavy", category="corte")
        assert {i["name"]: i["category"] for i in out["items"]} == {
            "Básico": "Corte",
            "Heavy": "Corte",
        }

    async def test_empty_is_no_category_and_too_long_is_refused(
        self, client: Any, biz: Biz
    ) -> None:
        out = await add_service(client, biz, name="Consulta", category="   ")
        assert out["items"][0]["category"] is None
        now = await get_section(client, biz, "services")
        resp = await client.post(
            f"{biz.url}/services",
            json=service_body(name="Larga", category="x" * 41),
            headers={**biz.headers(), **if_match(now["revision"])},
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["detail"]["code"] == "category_too_long"

    async def test_editing_and_duplicating_keep_it(self, client: Any, biz: Biz) -> None:
        out = await add_service(client, biz, name="Básico", category="Corte")
        service_id = out["items"][0]["id"]
        resp = await client.patch(
            f"{biz.url}/services/{service_id}",
            json={"description": "Con lavado"},
            headers={**biz.headers(), **if_match(out["revision"])},
        )
        assert resp.status_code == 200 and resp.json()["items"][0]["category"] == "Corte"
        copy = await client.post(
            f"{biz.url}/services/{service_id}/duplicate",
            headers={**biz.headers(), **if_match(resp.json()["revision"])},
        )
        assert copy.status_code == 201, copy.text
        assert {i["category"] for i in copy.json()["items"]} == {"Corte"}

    async def test_the_exported_ficha_keeps_it(self, client: Any, biz: Biz) -> None:
        await add_service(client, biz, name="Básico", category="Corte")
        await add_service(client, biz, name="Consulta")
        resp = await client.get(f"/console/clients/{biz.ref}/business", headers=biz.headers())
        assert resp.status_code == 200, resp.text
        services = {s["name"]: s for s in resp.json()["spec"]["services"]}
        assert services["Básico"]["category"] == "Corte"
        assert "category" not in services["Consulta"]

    async def test_the_agent_reads_it_first_and_lines_without_it_stay_the_same(
        self, client: Any, biz: Biz, db_session: AsyncSession
    ) -> None:
        from ._business_world import seed_agent

        await add_service(client, biz, name="Básico", category="Corte")
        await add_service(client, biz, name="Consulta", amount=None)
        agent, _config = await seed_agent(
            db_session, biz.tenant_id, name="Recepción", prompt="Hola"
        )
        async with tenant_scoped_session(db_session, biz.tenant_id):
            from nexus_api.db.models import Agent

            row = await db_session.get(Agent, agent)
            assert row is not None
            facts = await compilation.load_facts(db_session, row)
        assert "Corte · Básico · 30 min · 15,50 EUR · se reserva" in facts.services
        assert any(line.startswith("Consulta · ") for line in facts.services)
