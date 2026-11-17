"""Las herramientas de equipo de ``quedate.*`` (spec 061, enmienda del 2026-11-16;
requisitos 4.4-4.7 y Historia 5).

Actúan sobre cualquier anfitrión o anuncio de la clave del negocio. Qué agente las
tiene lo decide el partner (Luis, 2026-11-16); el conector solo garantiza que nunca
publican, que no reintentan lo que crea y que lo que la clave no alcanza se dice.
"""

from __future__ import annotations

import copy
import json
import uuid
from typing import Any

import httpx
import pytest
from _quedate_support import (
    EXAMPLES,
    HOST_DATA,
    HOST_ID,
    LISTING_DATA,
    LISTING_ID,
    OTHER_HOST,
    OTHER_LISTING,
    installed,
    result,
    serve_everything,
    tool,
)

from nexus_mcp.base import ToolError
from nexus_mcp.servers.quedate import tools

pytestmark = [pytest.mark.unit]

TENANT = uuid.UUID("00000000-0000-0000-0000-0000000000a4")
STAFF = uuid.UUID("00000000-0000-0000-0000-0000000000c5")
NEW_HOST = {**HOST_DATA, "email": "nuevo@example.com", "phone": "+584120000002"}


@pytest.fixture
def env() -> Any:
    with installed(TENANT, STAFF) as e:
        serve_everything(e.rec)
        yield e


def _page(rows: list[tuple[str, str]], page: int = 1, last: int = 1) -> dict[str, Any]:
    base = EXAMPLES["listings_page_200"]["data"]["data"][0]
    out = copy.deepcopy(EXAMPLES["listings_page_200"])
    out["data"].update(
        data=[{**base, "id": i, "user_id": u} for i, u in rows],
        current_page=page,
        last_page=last,
        total=len(rows),
    )
    return out


async def test_list_hosts_pages_by_ten(env: Any) -> None:
    out = result(await tool("quedate.list_hosts").invoke({"page": 2}))
    (sent,) = env.rec.sent
    assert sent.params == {"page": "2", "per_page": str(tools.MAX_ITEMS)}
    row = EXAMPLES["hosts_page_200"]["data"]["data"][0]
    assert out["items"][0]["id"] == row["id"]
    assert out["items"][0]["listings_count"] == row["listings_count"]
    assert "V-00000000" not in json.dumps(out), "la lista no lleva el documento"


async def test_get_host_carries_status_and_listings(env: Any) -> None:
    out = result(await tool("quedate.get_host").invoke({"host_id": HOST_ID}))
    data = EXAMPLES["host_get_200"]["data"]
    assert out["id"] == HOST_ID
    assert out["kyc_selfie_status"] == data["kyc_selfie_status"]
    assert "document_number" not in out


async def test_a_host_of_another_key_is_said_not_reached(env: Any) -> None:
    env.rec.on("GET", f"/agent/hosts/{OTHER_HOST}", 403, EXAMPLES["forbidden_403"])
    with pytest.raises(ToolError, match="no alcanza"):
        await tool("quedate.get_host").invoke({"host_id": OTHER_HOST})


async def test_create_host_is_not_retried(env: Any) -> None:
    out = result(await tool("quedate.create_host").invoke(NEW_HOST))
    assert out == {
        "created": True,
        "host_id": HOST_ID,
        "already_existed": False,
        "rejected_field": None,
        "message": None,
    }
    (sent,) = env.rec.to("POST", "/agent/hosts")
    assert sent.body["phone"] == NEW_HOST["phone"]
    assert env.rec.retries_asked[0] == 0


async def test_create_host_with_a_taken_email_of_this_key_returns_it(env: Any) -> None:
    env.rec.on("POST", "/agent/hosts", 422, EXAMPLES["host_email_taken_422"])
    out = result(
        await tool("quedate.create_host").invoke({**NEW_HOST, "email": "ana.prueba@example.com"})
    )
    assert out["created"] is False and out["already_existed"] is True
    assert out["host_id"] == HOST_ID


async def test_create_host_without_answer_is_audited(env: Any) -> None:
    env.rec.fail("POST", "/agent/hosts", httpx.ReadTimeout("slow"))
    with pytest.raises(ToolError, match="list_hosts"):
        await tool("quedate.create_host").invoke(NEW_HOST)
    assert len(env.rec.to("POST", "/agent/hosts")) == 1
    assert env.store.audits == [
        (TENANT, STAFF, "connector.external_write_unconfirmed", "create_host")
    ]


async def test_host_verification_link_stores_nothing(env: Any) -> None:
    out = result(await tool("quedate.host_verification_link").invoke({"host_id": HOST_ID}))
    assert out["url"].startswith("https://") and out["reused"] is False
    assert env.store.links == {}


async def test_host_identity_uses_photos_of_this_conversation_only(env: Any) -> None:
    other = uuid.UUID("00000000-0000-0000-0000-0000000000c6")
    (foreign,) = env.photos.give(other, 1)
    with pytest.raises(ToolError, match="no está entre"):
        await tool("quedate.upload_host_identity").invoke(
            {"host_id": HOST_ID, "document_photo_id": foreign}
        )
    assert env.photos.reads == [] and env.rec.sent == []
    (doc,) = env.photos.give(STAFF, 1)
    out = result(
        await tool("quedate.upload_host_identity").invoke(
            {"host_id": HOST_ID, "document_photo_id": doc}
        )
    )
    assert out["uploaded"] is True
    (sent,) = env.rec.to("POST", f"/agent/hosts/{HOST_ID}/kyc")
    assert sent.parts == ["document_image"]


async def test_list_listings_without_host_is_one_page(env: Any) -> None:
    out = result(await tool("quedate.list_listings").invoke({"page": 1}))
    assert out["items"][0]["host_id"] == HOST_ID
    assert len(env.rec.sent) == 1


async def test_list_listings_filters_by_host_here_because_quedate_ignores_it(env: Any) -> None:
    rows = [(f"l-{i}", HOST_ID if i % 3 == 0 else OTHER_HOST) for i in range(30)]
    env.rec.routes.pop(("GET", "/agent/listings"))
    env.rec.then("GET", "/agent/listings", 200, _page(rows[:15], 1, 2))
    env.rec.then("GET", "/agent/listings", 200, _page(rows[15:], 2, 2))
    out = result(await tool("quedate.list_listings").invoke({"page": 1, "host_id": HOST_ID}))
    assert out["total"] == 10 and out["last_page"] == 1
    assert {i["host_id"] for i in out["items"]} == {HOST_ID}
    assert all("host_id" not in s.params for s in env.rec.sent)


async def test_get_managed_listing_never_leaks_the_calendar_token(env: Any) -> None:
    out = result(await tool("quedate.get_managed_listing").invoke({"listing_id": LISTING_ID}))
    assert out["host_id"] == HOST_ID
    dumped = json.dumps(out)
    assert "ical" not in dumped and "commission" not in dumped


async def test_create_listing_sends_the_given_host(env: Any) -> None:
    out = result(await tool("quedate.create_listing").invoke({**LISTING_DATA, "host_id": HOST_ID}))
    assert out["listing_id"] == LISTING_ID
    (sent,) = env.rec.to("POST", "/agent/listings")
    assert sent.body["host_id"] == HOST_ID
    assert env.rec.retries_asked[0] == 0


async def test_create_listing_without_answer_is_audited(env: Any) -> None:
    env.rec.fail("POST", "/agent/listings", httpx.ReadTimeout("slow"))
    with pytest.raises(ToolError, match="Compruébalo"):
        await tool("quedate.create_listing").invoke({**LISTING_DATA, "host_id": HOST_ID})
    assert env.store.audits[-1][2:] == ("connector.external_write_unconfirmed", "create_listing")


async def test_a_rejected_catalog_id_on_a_team_listing_says_to_look_it_up_again(
    env: Any,
) -> None:
    """4.9, la de equipo."""
    text = "The selected property type id is invalid."
    env.rec.on(
        "POST",
        "/agent/listings",
        422,
        {
            "success": False,
            "error_code": "VALIDATION_ERROR",
            "message": text,
            "errors": {"property_type_id": [text]},
        },
    )
    with pytest.raises(ToolError, match="No se creó nada") as caught:
        await tool("quedate.create_listing").invoke({**LISTING_DATA, "host_id": HOST_ID})
    assert "quedate.listing_options" in str(caught.value)


async def test_photos_upload_is_not_retried_and_audited_on_timeout(env: Any) -> None:
    ids = env.photos.give(STAFF, 2)
    env.rec.fail("POST", f"/agent/listings/{LISTING_ID}/media", httpx.ReadTimeout("slow"))
    with pytest.raises(ToolError, match="Compruébalo"):
        await tool("quedate.add_listing_photos").invoke(
            {"listing_id": LISTING_ID, "photo_ids": ids}
        )
    assert len(env.rec.to("POST", f"/agent/listings/{LISTING_ID}/media")) == 1
    assert env.store.audits[-1][2:] == ("connector.external_write_unconfirmed", "upload_photos")


@pytest.mark.parametrize(
    ("name", "status"),
    [("quedate.submit_listing", "pending_approval"), ("quedate.hide_listing", "hidden")],
)
async def test_team_status_changes_never_publish(env: Any, name: str, status: str) -> None:
    env.rec.on(
        "PATCH",
        f"/agent/listings/{OTHER_LISTING}/status",
        body={"success": True, "data": {"id": OTHER_LISTING, "status": status}},
    )
    out = result(await tool(name).invoke({"listing_id": OTHER_LISTING}))
    (sent,) = env.rec.to("PATCH", f"/agent/listings/{OTHER_LISTING}/status")
    assert sent.body == {"status": status} and out["status"] == status


async def test_a_listing_of_another_key_is_said_not_reached(env: Any) -> None:
    env.rec.on("PATCH", f"/agent/listings/{OTHER_LISTING}/status", 403, EXAMPLES["forbidden_403"])
    with pytest.raises(ToolError, match="no alcanza"):
        await tool("quedate.hide_listing").invoke({"listing_id": OTHER_LISTING})
