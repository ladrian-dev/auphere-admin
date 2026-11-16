"""Las herramientas de la persona que escribe (spec 061, enmienda del 2026-11-16;
requisitos 3.1-3.12, 4.1-4.7 y CE-002, CE-004).

Su anfitrión sale del vínculo resuelto en el servidor, nunca de un argumento. Un
Quédate falso por transporte, un almacén de vínculos y unas fotos en memoria. La
base de datos de verdad (RLS, FK, cascada) la prueba
``apps/api/tests/isolation/test_061_customer_connector_accounts.py``.
"""

from __future__ import annotations

import copy
import json
import uuid
from datetime import UTC, datetime, timedelta
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
from nexus_mcp.servers.quedate.accounts import Link

pytestmark = [pytest.mark.unit]

TENANT = uuid.UUID("00000000-0000-0000-0000-0000000000a3")
MARIA = uuid.UUID("00000000-0000-0000-0000-0000000000c3")
PEDRO = uuid.UUID("00000000-0000-0000-0000-0000000000c4")
REGISTER = {**HOST_DATA, "email": "ana@example.com", "email_confirmed": True}


@pytest.fixture
def env() -> Any:
    with installed(TENANT, MARIA) as e:
        e.store.phones[MARIA] = "+584120000000"
        serve_everything(e.rec)
        yield e


def _link(env: Any, host_id: str = HOST_ID, **over: Any) -> None:
    env.store.links[(TENANT, MARIA)] = Link(host_id=host_id, **over)


def _listings_with(*rows: tuple[str, str]) -> dict[str, Any]:
    """Una página de la lista de anuncios de la clave: ``(id, user_id)``."""
    base = EXAMPLES["listings_page_200"]["data"]["data"][0]
    page = copy.deepcopy(EXAMPLES["listings_page_200"])
    page["data"]["data"] = [{**base, "id": i, "user_id": u} for i, u in rows]
    page["data"]["total"] = len(rows)
    return page


# ── alta ─────────────────────────────────────────────────────────────────


async def test_register_creates_the_host_and_links_it_to_the_person(env: Any) -> None:
    out = result(await tool("quedate.register_me").invoke(REGISTER))
    assert out["registered"] is True and out["kyc_verified"] is False
    assert env.store.links[(TENANT, MARIA)].host_id == HOST_ID
    assert env.store.audits == [(TENANT, MARIA, "connector.customer_account_linked", None)]
    (sent,) = env.rec.to("POST", "/agent/hosts")
    assert sent.body["email"] == "ana@example.com"
    assert sent.body["phone"] == "+584120000000", "el teléfono sale del chat (3.2)"
    assert sent.body["nationality"] == "VEN"
    assert env.store.locks == 1
    assert env.rec.retries_asked[-1] == 0, "crear un anfitrión no se reintenta"


async def test_register_twice_creates_nothing_more(env: Any) -> None:
    """CE-004: repetir el alta de una persona vinculada no llama a Quédate."""
    _link(env)
    out = result(await tool("quedate.register_me").invoke(REGISTER))
    assert out["registered"] is False and out["already_linked"] is True
    assert env.rec.sent == []


async def test_register_without_the_email_read_back_never_calls_quedate(env: Any) -> None:
    """3.3."""
    out = result(await tool("quedate.register_me").invoke({**REGISTER, "email_confirmed": False}))
    assert out["registered"] is False
    assert env.rec.sent == [] and env.store.links == {}


async def test_a_taken_email_of_this_key_links_that_host(env: Any) -> None:
    """3.5: el correo ya es de un anfitrión que creó esta clave."""
    env.rec.on("POST", "/agent/hosts", 422, EXAMPLES["host_email_taken_422"])
    out = result(
        await tool("quedate.register_me").invoke({**REGISTER, "email": "ANA.PRUEBA@example.com"})
    )
    assert out["registered"] is True and out["linked_existing"] is True
    assert env.store.links[(TENANT, MARIA)].host_id == HOST_ID


@pytest.mark.parametrize(
    "phone", ["+584149999999", None], ids=["another-phone", "no-phone-in-the-chat"]
)
async def test_a_taken_email_with_another_phone_links_nothing(env: Any, phone: str | None) -> None:
    """/cso del 2026-11-16: el correo lo puede decir cualquiera. Sin el teléfono del
    chat, el anfitrión de otra persona no se vincula (3.5)."""
    if phone is None:
        env.store.phones.pop(MARIA)
    else:
        env.store.phones[MARIA] = phone
    env.rec.on("POST", "/agent/hosts", 422, EXAMPLES["host_email_taken_422"])
    out = result(
        await tool("quedate.register_me").invoke({**REGISTER, "email": "ana.prueba@example.com"})
    )
    assert out["registered"] is False and out["rejected_field"] == "email"
    assert "equipo del negocio" in out["message"]
    assert env.store.links == {}


async def test_a_host_already_linked_to_someone_else_is_not_linked_again(env: Any) -> None:
    """Un anfitrión, una persona por negocio (/cso del 2026-11-16)."""
    env.store.links[(TENANT, PEDRO)] = Link(host_id=HOST_ID)
    env.rec.on("POST", "/agent/hosts", 422, EXAMPLES["host_email_taken_422"])
    out = result(
        await tool("quedate.register_me").invoke({**REGISTER, "email": "ana.prueba@example.com"})
    )
    assert out["registered"] is False and out["rejected_field"] == "email"
    assert (TENANT, MARIA) not in env.store.links


async def test_a_taken_email_outside_this_key_links_nothing(env: Any) -> None:
    env.rec.on("POST", "/agent/hosts", 422, EXAMPLES["host_email_taken_422"])
    out = result(
        await tool("quedate.register_me").invoke({**REGISTER, "email": "otra.persona@example.com"})
    )
    assert out["registered"] is False and out["rejected_field"] == "email"
    assert env.store.links == {}


async def test_a_rejected_field_is_named_and_nothing_is_linked(env: Any) -> None:
    env.rec.on(
        "POST",
        "/agent/hosts",
        422,
        {
            "success": False,
            "error_code": "VALIDATION_ERROR",
            "message": "Validation failed",
            "errors": {"document_number": ["El formato de la cédula no es válido."]},
        },
    )
    out = result(await tool("quedate.register_me").invoke(REGISTER))
    assert out["registered"] is False and out["rejected_field"] == "document_number"
    assert out["message"] == "El formato de la cédula no es válido."
    assert env.store.links == {}


async def test_register_timeout_is_audited_and_not_retried(env: Any) -> None:
    """4.6: Quédate pudo crearlo; queda en la auditoría y nada se repite solo."""
    env.rec.fail("POST", "/agent/hosts", httpx.ReadTimeout("slow"))
    with pytest.raises(ToolError, match="puede que la haya dado de alta"):
        await tool("quedate.register_me").invoke(REGISTER)
    assert len(env.rec.to("POST", "/agent/hosts")) == 1
    assert env.store.audits == [(TENANT, MARIA, "connector.customer_account_link_failed", None)]
    assert env.store.links == {}


async def test_a_link_that_cannot_be_saved_is_audited(env: Any) -> None:
    env.store.save_fails = True
    with pytest.raises(ToolError, match="no pude vincularla"):
        await tool("quedate.register_me").invoke(REGISTER)
    assert env.store.audits[-1][2] == "connector.customer_account_link_failed"


async def test_register_needs_the_person_of_the_turn() -> None:
    with installed(TENANT, None) as e:
        serve_everything(e.rec)
        with pytest.raises(ToolError):
            await tool("quedate.register_me").invoke(REGISTER)
        assert e.rec.sent == []


# ── su anfitrión ─────────────────────────────────────────────────────────


async def test_my_host_reads_the_linked_host_only(env: Any) -> None:
    _link(env)
    out = result(await tool("quedate.my_host").invoke({}))
    assert out["linked"] is True and out["kyc_verified"] is False
    assert out["kyc_document_status"] == EXAMPLES["host_get_200"]["data"]["kyc_document_status"]
    assert [s.path for s in env.rec.sent] == [f"/agent/hosts/{HOST_ID}"]
    dumped = json.dumps(out)
    assert "ana.prueba@example.com" not in dumped and "V-00000000" not in dumped


async def test_my_host_without_a_link_points_to_register(env: Any) -> None:
    out = result(await tool("quedate.my_host").invoke({}))
    assert out["linked"] is False and "register_me" in out["next_step"]
    assert env.rec.sent == []


async def test_a_host_the_key_no_longer_reaches_is_marked_for_review(env: Any) -> None:
    """3.10: una clave nueva deja huérfanos a los anfitriones; 403, no se adivina."""
    _link(env)
    env.rec.on("GET", f"/agent/hosts/{HOST_ID}", 403, EXAMPLES["forbidden_403"])
    with pytest.raises(ToolError, match="ya no lo alcanza"):
        await tool("quedate.my_host").invoke({})
    assert env.store.links[(TENANT, MARIA)].needs_review is True
    out = result(await tool("quedate.my_host").invoke({}))
    assert out["needs_review"] is True
    assert len(env.rec.sent) == 1, "marcado, ya no se vuelve a llamar"


# ── verificación de identidad ────────────────────────────────────────────


async def test_the_verification_link_is_fetched_once_and_reused(env: Any) -> None:
    """3.7."""
    _link(env)
    first = result(await tool("quedate.my_verification_link").invoke({}))
    assert first["url"].startswith("https://") and first["reused"] is False
    again = result(await tool("quedate.my_verification_link").invoke({}))
    assert again == {**first, "reused": True}
    assert len(env.rec.to("GET", f"/agent/hosts/{HOST_ID}/kyc-link")) == 1


async def test_a_link_about_to_expire_is_renewed(env: Any) -> None:
    soon = (datetime.now(UTC) + timedelta(hours=3)).isoformat()
    _link(env, state={"verification_link": {"url": "https://old.example/kyc", "expires_at": soon}})
    out = result(await tool("quedate.my_verification_link").invoke({}))
    assert out["reused"] is False and out["url"] != "https://old.example/kyc"


async def test_a_link_that_is_not_https_is_not_passed_on(env: Any) -> None:
    _link(env)
    env.rec.on(
        "GET",
        f"/agent/hosts/{HOST_ID}/kyc-link",
        body={"success": True, "data": {"kyc_url": "javascript:alert(1)", "expires_in_days": 7}},
    )
    with pytest.raises(ToolError):
        await tool("quedate.my_verification_link").invoke({})


async def test_identity_upload_sends_the_chosen_photos_in_order(env: Any) -> None:
    _link(env)
    doc, selfie = env.photos.give(MARIA, 2)
    out = result(
        await tool("quedate.upload_my_identity").invoke(
            {"document_photo_id": doc, "selfie_photo_id": selfie}
        )
    )
    assert out["uploaded"] is True
    (sent,) = env.rec.to("POST", f"/agent/hosts/{HOST_ID}/kyc")
    assert sent.parts == ["document_image", "selfie_image"]
    assert env.photos.reads == [doc, selfie]


async def test_an_identity_upload_without_answer_is_audited(env: Any) -> None:
    """La subida menos reversible: si Quédate no responde, queda en la auditoría."""
    _link(env)
    (doc,) = env.photos.give(MARIA, 1)
    env.rec.fail("POST", f"/agent/hosts/{HOST_ID}/kyc", httpx.ReadTimeout("slow"))
    with pytest.raises(ToolError):
        await tool("quedate.upload_my_identity").invoke({"document_photo_id": doc})
    assert len(env.rec.to("POST", f"/agent/hosts/{HOST_ID}/kyc")) == 1
    assert env.store.audits == [
        (TENANT, MARIA, "connector.external_write_unconfirmed", "upload_identity")
    ]


async def test_a_photo_of_someone_else_is_never_read_nor_sent(env: Any) -> None:
    """3.8 y garantía 8: las fotos son las de la conversación de la persona del turno."""
    _link(env)
    (pedros,) = env.photos.give(PEDRO, 1)
    with pytest.raises(ToolError, match="no está entre"):
        await tool("quedate.upload_my_identity").invoke({"document_photo_id": pedros})
    assert env.photos.reads == []
    assert env.rec.to("POST", f"/agent/hosts/{HOST_ID}/kyc") == []


async def test_the_same_photo_twice_is_refused(env: Any) -> None:
    _link(env)
    (doc,) = env.photos.give(MARIA, 1)
    with pytest.raises(ToolError, match="repetidas"):
        await tool("quedate.upload_my_identity").invoke(
            {"document_photo_id": doc, "selfie_photo_id": doc}
        )
    assert env.rec.sent == []


# ── sus anuncios ─────────────────────────────────────────────────────────


async def test_create_my_listing_uses_the_linked_host_and_is_not_retried(env: Any) -> None:
    _link(env)
    out = result(await tool("quedate.create_my_listing").invoke(LISTING_DATA))
    assert out["listing_id"] == LISTING_ID and out["status"] == "draft"
    (sent,) = env.rec.to("POST", "/agent/listings")
    assert sent.body["host_id"] == HOST_ID
    assert env.rec.retries_asked[-1] == 0


async def test_create_my_listing_ignores_a_host_id_slipped_in(env: Any) -> None:
    """Garantía 8: un ``host_id`` en los argumentos no llega a Quédate."""
    _link(env)
    with pytest.raises(Exception):  # noqa: B017 — cualquier rechazo de validación vale
        await tool("quedate.create_my_listing").invoke({**LISTING_DATA, "host_id": OTHER_HOST})
    assert env.rec.to("POST", "/agent/listings") == []


async def test_a_listing_create_without_answer_is_audited_once(env: Any) -> None:
    """4.6."""
    _link(env)
    env.rec.fail("POST", "/agent/listings", httpx.ReadTimeout("slow"))
    with pytest.raises(ToolError, match="Compruébalo"):
        await tool("quedate.create_my_listing").invoke(LISTING_DATA)
    assert len(env.rec.to("POST", "/agent/listings")) == 1
    assert env.store.audits == [
        (TENANT, MARIA, "connector.external_write_unconfirmed", "create_listing")
    ]


async def test_photos_go_only_to_a_listing_of_the_person(env: Any) -> None:
    """4.5: antes de escribir, el anuncio tiene que ser de su anfitrión."""
    _link(env)
    env.rec.on(
        "GET",
        "/agent/listings",
        body=_listings_with((LISTING_ID, HOST_ID), (OTHER_LISTING, OTHER_HOST)),
    )
    ids = env.photos.give(MARIA, 3)
    out = result(
        await tool("quedate.add_my_listing_photos").invoke(
            {"listing_id": LISTING_ID, "photo_ids": ids}
        )
    )
    assert out["total_photos"] == EXAMPLES["media_200"]["data"]["total_photos"]
    (sent,) = env.rec.to("POST", f"/agent/listings/{LISTING_ID}/media")
    assert sent.parts == ["files[]"] * 3

    with pytest.raises(ToolError, match="no es de esta persona"):
        await tool("quedate.add_my_listing_photos").invoke(
            {"listing_id": OTHER_LISTING, "photo_ids": ids}
        )
    assert env.rec.to("POST", f"/agent/listings/{OTHER_LISTING}/media") == []


async def test_a_listing_missing_from_the_key_is_not_written(env: Any) -> None:
    _link(env)
    env.rec.on("GET", "/agent/listings", body=_listings_with((LISTING_ID, HOST_ID)))
    with pytest.raises(ToolError, match="no es de esta persona"):
        await tool("quedate.submit_my_listing").invoke({"listing_id": OTHER_LISTING})
    assert [s for s in env.rec.sent if s.method == "PATCH"] == []


async def test_ownership_is_searched_across_pages(env: Any) -> None:
    _link(env)
    page1 = _listings_with((OTHER_LISTING, OTHER_HOST))
    page1["data"].update(current_page=1, last_page=2)
    page2 = _listings_with((LISTING_ID, HOST_ID))
    page2["data"].update(current_page=2, last_page=2)
    env.rec.routes.pop(("GET", "/agent/listings"))
    env.rec.then("GET", "/agent/listings", 200, page1).then("GET", "/agent/listings", 200, page2)
    out = result(await tool("quedate.submit_my_listing").invoke({"listing_id": LISTING_ID}))
    assert out["status"] == "pending_approval"
    assert [s.params.get("page") for s in env.rec.to("GET", "/agent/listings")] == ["1", "2"]


@pytest.mark.parametrize(
    ("name", "status"),
    [("quedate.submit_my_listing", "pending_approval"), ("quedate.hide_my_listing", "hidden")],
)
async def test_status_changes_never_publish(env: Any, name: str, status: str) -> None:
    """Luis, 2026-11-16: el agente manda a revisión de Quédate u oculta; nunca publica."""
    _link(env)
    env.rec.on(
        "PATCH",
        f"/agent/listings/{LISTING_ID}/status",
        body={"success": True, "data": {"id": LISTING_ID, "status": status}},
    )
    out = result(await tool(name).invoke({"listing_id": LISTING_ID}))
    (sent,) = env.rec.to("PATCH", f"/agent/listings/{LISTING_ID}/status")
    assert sent.body == {"status": status}
    assert out["status"] == status


async def test_my_listings_are_only_the_persons(env: Any) -> None:
    _link(env)
    env.rec.on(
        "GET",
        "/agent/listings",
        body=_listings_with((LISTING_ID, HOST_ID), (OTHER_LISTING, OTHER_HOST)),
    )
    out = result(await tool("quedate.my_listings").invoke({}))
    assert [i["id"] for i in out["items"]] == [LISTING_ID] and out["total"] == 1
    assert "ical" not in json.dumps(out)


@pytest.mark.parametrize(
    "name",
    [
        "quedate.my_verification_link",
        "quedate.create_my_listing",
        "quedate.submit_my_listing",
        "quedate.hide_my_listing",
    ],
)
async def test_without_a_link_person_writes_never_reach_quedate(env: Any, name: str) -> None:
    args = LISTING_DATA if name == "quedate.create_my_listing" else {}
    if name in ("quedate.submit_my_listing", "quedate.hide_my_listing"):
        args = {"listing_id": LISTING_ID}
    with pytest.raises(ToolError, match="register_me"):
        await tool(name).invoke(args)
    assert env.rec.sent == []


async def test_a_link_under_review_blocks_writes(env: Any) -> None:
    _link(env, needs_review=True)
    with pytest.raises(ToolError, match="ya no lo alcanza"):
        await tool("quedate.create_my_listing").invoke(LISTING_DATA)
    assert env.rec.sent == []


async def test_one_persons_link_is_not_anothers() -> None:
    """Garantía 8: Pedro, en el mismo negocio, no ve el anfitrión de María."""
    with installed(TENANT, PEDRO) as e:
        e.store.links[(TENANT, MARIA)] = Link(host_id=HOST_ID)
        serve_everything(e.rec)
        out = result(await tool("quedate.my_host").invoke({}))
        assert out["linked"] is False
        assert e.rec.sent == []
