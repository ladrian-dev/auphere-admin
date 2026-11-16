"""Catálogo, públicas y fotos de ``quedate.*`` (spec 061, enmienda del 2026-11-16;
requisitos 2.1-2.7, 5.6, 6.2 y CE-006).

El catálogo se prueba con la captura de Quédate dev (recortada). Las públicas usan la
API general; donde Quédate no documenta la respuesta, el cuerpo es mínimo y solo se
prueba que lo que no está en la salida no pasa.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
import pytest
from _quedate_support import EXAMPLES, LISTING_ID, installed, result, tool

from nexus_mcp.base import ToolError
from nexus_mcp.servers.quedate import tools

pytestmark = [pytest.mark.unit]

TENANT = uuid.UUID("00000000-0000-0000-0000-0000000000a2")
CUSTOMER = uuid.UUID("00000000-0000-0000-0000-0000000000c2")
CAP = 8_000  # _TOOL_RESULT_CHAR_CAP del worker
CATALOG = EXAMPLES["catalogs_200"]["data"]


@pytest.fixture
def env() -> Any:
    with installed(TENANT, None) as e:
        yield e


# ── catálogo ─────────────────────────────────────────────────────────────


async def test_locations_walk_states_cities_and_sectors_with_their_ids(env: Any) -> None:
    env.rec.on("GET", "/agent/catalogs", body=EXAMPLES["catalogs_200"])
    state = CATALOG["states"][0]
    city = state["cities"][0]

    states = result(await tool("quedate.list_locations").invoke({}))
    assert states["level"] == "states"
    assert states["items"][0] == {"id": state["id"], "name": state["name"]}

    cities = result(await tool("quedate.list_locations").invoke({"state": state["name"].upper()}))
    assert cities["level"] == "cities"
    assert [c["id"] for c in cities["items"]] == [c["id"] for c in state["cities"]]

    sectors = result(
        await tool("quedate.list_locations").invoke({"state": state["name"], "city": city["name"]})
    )
    assert sectors["level"] == "sectors"
    assert [s["id"] for s in sectors["items"]] == [s["id"] for s in city["sectors"]]


async def test_an_unknown_state_answers_with_the_valid_ones(env: Any) -> None:
    env.rec.on("GET", "/agent/catalogs", body=EXAMPLES["catalogs_200"])
    out = result(await tool("quedate.list_locations").invoke({"state": "Narnia"}))
    assert out["level"] == "states" and "Narnia" in out["message"]
    assert len(out["items"]) == len(CATALOG["states"])


async def test_locations_are_capped(env: Any) -> None:
    many = {
        "success": True,
        "data": {"states": [{"id": f"s-{i}", "name": f"Estado {i}"} for i in range(200)]},
    }
    env.rec.on("GET", "/agent/catalogs", body=many)
    out = result(await tool("quedate.list_locations").invoke({}))
    assert len(out["items"]) == tools.MAX_LOCATIONS and out["truncated"] is True
    assert len(json.dumps(out)) < CAP


async def test_listing_options_carry_the_ids_a_listing_needs(env: Any) -> None:
    env.rec.on("GET", "/agent/catalogs", body=EXAMPLES["catalogs_200"])
    out = result(await tool("quedate.listing_options").invoke({}))
    assert out["property_types"][0]["id"] == CATALOG["property_types"][0]["id"]
    assert out["amenities"][0]["name"] == CATALOG["amenities"][0]["name"]
    assert out["rental_types"] == CATALOG["rental_types"]
    assert out["document_types"] == ["CI", "PASAPORTE", "RIF"]
    assert out["bcv_rate"] == CATALOG["bcv_rate"]


# ── públicas ─────────────────────────────────────────────────────────────


def _host() -> dict[str, Any]:
    return {
        "id": "h-1",
        "name": "María Anfitriona",
        "email": "maria@example.com",
        "phone": "+584127654321",
        "document_number": "V12345678",
    }


async def test_get_listing_never_returns_the_hosts_contact_data(env: Any) -> None:
    env.rec.on(
        "GET",
        f"/listings/{LISTING_ID}",
        body={
            "success": True,
            "data": {
                "id": LISTING_ID,
                "title": "Apto",
                "description": "x" * 5_000,
                "host": _host(),
                "host_email": "maria@example.com",
                "unavailableDates": [f"2026-12-{d:02d}" for d in range(1, 29)] * 10,
                "amenities": [f"a{i}" for i in range(80)],
            },
        },
    )
    out = result(await tool("quedate.get_listing").invoke({"listing": LISTING_ID}))
    dumped = json.dumps(out)
    for secret in ("maria@example.com", "+584127654321", "V12345678"):
        assert secret not in dumped
    assert out["host_name"] == "María Anfitriona"
    assert len(out["description"]) == tools.MAX_DESCRIPTION
    assert len(out["unavailable_dates"]) == tools.MAX_UNAVAILABLE_DATES
    assert out["unavailable_dates_truncated"] is True
    assert len(out["amenities"]) == tools.MAX_AMENITIES
    assert len(dumped) < CAP


async def test_a_listing_ref_that_is_not_an_id_or_slug_never_reaches_the_path(env: Any) -> None:
    with pytest.raises(ToolError):
        await tool("quedate.get_listing").invoke({"listing": "../admin/users"})
    assert env.rec.sent == []


async def test_search_returns_at_most_ten_and_says_so(env: Any) -> None:
    rows = [
        {"id": f"l-{i}", "title": f"Apto {i}", "host": _host(), "price_per_night": 50}
        for i in range(40)
    ]
    env.rec.on(
        "GET", "/search/listings", body={"success": True, "data": {"data": rows, "total": 40}}
    )
    out = result(await tool("quedate.search_listings").invoke({"city": "Caracas"}))
    assert len(out["items"]) == tools.MAX_ITEMS
    assert out["total"] == 40 and out["truncated"] is True
    assert "maria@example.com" not in json.dumps(out)
    assert len(json.dumps(out)) < CAP


@pytest.mark.parametrize("status", [409, 422])
async def test_a_quote_on_taken_dates_is_an_answer_not_a_failure(env: Any, status: int) -> None:
    env.rec.on(
        "POST",
        "/checkout/quote",
        status,
        {"success": False, "error_code": "DATES_UNAVAILABLE", "message": "Fechas no disponibles."},
    )
    out = result(
        await tool("quedate.quote_stay").invoke(
            {
                "listing_id": LISTING_ID,
                "check_in": "2026-12-10",
                "check_out": "2026-12-12",
                "guests": 2,
            }
        )
    )
    assert out["available"] is False
    assert out["message"] == "Fechas no disponibles."


async def test_booking_settings_read_the_documented_switch(env: Any) -> None:
    env.rec.on("GET", "/settings/public", body=EXAMPLES["settings_public_200"])
    out = result(await tool("quedate.booking_settings").invoke({}))
    assert out == {"booking_mode": "immediate", "support_whatsapp": "+584141234567"}


# ── fallar cerrado ───────────────────────────────────────────────────────


@pytest.mark.parametrize("cls", tools.QUEDATE_TOOLS, ids=lambda c: c.name)
async def test_without_the_connection_no_tool_calls_quedate(cls: Any) -> None:
    """5.6 y spec 060: sin Quédate conectado y disponible, ninguna de las 27 sale."""
    from test_quedate_contract_unit import CASES

    with installed(TENANT, CUSTOMER) as e:
        e.store.connected = False
        args = {
            k: (["x"] if isinstance(v, list) else ("x" if v == "photo" else v))
            for k, v in CASES[cls.name].items()
        }
        with pytest.raises(ToolError, match="no está disponible"):
            await cls().invoke(args)
        assert e.rec.sent == []
        assert e.photos.reads == []


@pytest.mark.parametrize(
    "exc", [httpx.ConnectError("dns"), httpx.ReadTimeout("slow")], ids=["dns", "timeout"]
)
async def test_a_transport_failure_reads_as_quedate_not_answering(env: Any, exc: Exception) -> None:
    """Sin respuesta HTTP, el modelo lee «no responde», no el texto del transporte."""
    env.rec.fail("GET", "/agent/catalogs", exc)
    with pytest.raises(ToolError) as raised:
        await tool("quedate.list_locations").invoke({})
    assert str(raised.value) == tools._UNAVAILABLE


async def test_quedate_down_is_said_without_inventing(env: Any) -> None:
    env.rec.on("GET", "/settings/public", 503, {"success": False, "message": "boom"})
    with pytest.raises(ToolError, match="no responde"):
        await tool("quedate.booking_settings").invoke({})


async def test_a_rejected_key_is_not_passed_off_as_quedate_down(env: Any) -> None:
    env.rec.on("GET", "/agent/catalogs", 401, {"success": False, "message": "Unauthenticated."})
    with pytest.raises(ToolError) as raised:
        await tool("quedate.listing_options").invoke({})
    assert "no responde" not in str(raised.value)


# ── fotos de la conversación ─────────────────────────────────────────────


async def test_recent_photos_list_ids_and_times_never_where_they_live() -> None:
    with installed(TENANT, CUSTOMER) as e:
        ids = e.photos.give(CUSTOMER, 3)
        out = result(await tool("quedate.recent_photos").invoke({}))
    assert [p["photo_id"] for p in out["photos"]] == ids
    dumped = json.dumps(out)
    assert "media/" not in dumped and "tenant/" not in dumped
    assert e.photos.reads == []


async def test_recent_photos_say_so_when_there_are_none() -> None:
    with installed(TENANT, CUSTOMER):
        out = result(await tool("quedate.recent_photos").invoke({}))
    assert out["photos"] == [] and out["message"]


async def test_recent_photos_need_the_person_of_the_turn(env: Any) -> None:
    with pytest.raises(ToolError):
        await tool("quedate.recent_photos").invoke({})
