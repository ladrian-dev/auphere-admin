"""Contrato de las 27 herramientas ``quedate.*`` (spec 061, enmienda del 2026-11-16;
requisitos 1.2, 2.1, 3.1, 4.1, 4.4 y 6.1).

Cada herramienta se ejecuta contra un Quédate falso que guarda la petición tal como
sale. Cada petición tiene que:

- existir: las del agente en ``AGENT`` (su documentación y lo que Quédate dev aceptó);
  las públicas en la copia congelada del ``openapi.json`` general;
- llevar en la consulta, el cuerpo o el multipart solo campos documentados y todos
  los obligatorios;
- ir al entorno de la conexión: producción o desarrollo, nada más;
- las del agente, con la clave del negocio; las públicas, **sin** ``Authorization``.

Y ninguna herramienta acepta tenant, cliente, clave ni conversación como argumento;
las de la persona, tampoco ``host_id`` (garantía 8).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from _quedate_support import (
    HOST_DATA,
    HOST_ID,
    HOSTS,
    LISTING_DATA,
    LISTING_ID,
    OpenAPI,
    agent_op,
    installed,
    serve_everything,
    tool,
)

from nexus_mcp.servers.quedate import tools
from nexus_mcp.servers.quedate.accounts import Link
from nexus_mcp.servers.quedate.client import QuedateClient
from nexus_mcp.servers.quedate.errors import QuedateValidationError

pytestmark = [pytest.mark.unit]

TENANT = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
CUSTOMER = uuid.UUID("00000000-0000-0000-0000-0000000000c1")
PHOTO = "photo"  # se sustituye por ids reales en la prueba

CASES: dict[str, dict[str, Any]] = {
    # catálogo y públicas
    "quedate.list_locations": {},
    "quedate.listing_options": {},
    "quedate.search_listings": {
        "city": "Caracas",
        "check_in": "2026-12-10",
        "check_out": "2026-12-15",
        "guests": 2,
    },
    "quedate.get_listing": {"listing": LISTING_ID},
    "quedate.quote_stay": {
        "listing_id": LISTING_ID,
        "check_in": "2026-12-10",
        "check_out": "2026-12-15",
        "guests": 2,
    },
    "quedate.booking_settings": {},
    # fotos
    "quedate.recent_photos": {},
    # de la persona
    "quedate.register_me": {**HOST_DATA, "email": "ana@example.com", "email_confirmed": True},
    "quedate.my_host": {},
    "quedate.my_verification_link": {},
    "quedate.upload_my_identity": {"document_photo_id": PHOTO, "selfie_photo_id": PHOTO + "2"},
    "quedate.create_my_listing": dict(LISTING_DATA),
    "quedate.add_my_listing_photos": {"listing_id": LISTING_ID, "photo_ids": [PHOTO]},
    "quedate.submit_my_listing": {"listing_id": LISTING_ID},
    "quedate.hide_my_listing": {"listing_id": LISTING_ID},
    "quedate.my_listings": {},
    # de equipo
    "quedate.list_hosts": {"page": 1},
    "quedate.get_host": {"host_id": HOST_ID},
    "quedate.create_host": {**HOST_DATA, "email": "otra@example.com", "phone": "+584120000001"},
    "quedate.host_verification_link": {"host_id": HOST_ID},
    "quedate.upload_host_identity": {"host_id": HOST_ID, "document_photo_id": PHOTO},
    "quedate.list_listings": {"page": 1, "host_id": HOST_ID},
    "quedate.get_managed_listing": {"listing_id": LISTING_ID},
    "quedate.create_listing": {**LISTING_DATA, "host_id": HOST_ID},
    "quedate.add_listing_photos": {"listing_id": LISTING_ID, "photo_ids": [PHOTO]},
    "quedate.submit_listing": {"listing_id": LISTING_ID},
    "quedate.hide_listing": {"listing_id": LISTING_ID},
}

#: Las que necesitan a la persona vinculada antes de empezar.
NEEDS_LINK = {
    "quedate.my_host",
    "quedate.my_verification_link",
    "quedate.upload_my_identity",
    "quedate.create_my_listing",
    "quedate.add_my_listing_photos",
    "quedate.submit_my_listing",
    "quedate.hide_my_listing",
    "quedate.my_listings",
}


def test_every_tool_has_a_contract_case() -> None:
    assert {t.name for t in tools.QUEDATE_TOOLS} == set(CASES)
    assert len(CASES) == 27


def _args(name: str, photo_ids: list[str]) -> dict[str, Any]:
    args = dict(CASES[name])
    swap = {PHOTO: photo_ids[0], PHOTO + "2": photo_ids[1]}
    for k, v in list(args.items()):
        if isinstance(v, str) and v in swap:
            args[k] = swap[v]
        elif isinstance(v, list):
            args[k] = [swap.get(x, x) for x in v]
    return args


@pytest.mark.parametrize("environment", ["production", "development"])
@pytest.mark.parametrize("name", sorted(CASES))
async def test_each_request_is_in_the_contract(name: str, environment: str) -> None:
    spec = OpenAPI()
    with installed(TENANT, CUSTOMER) as env:
        env.store.environment = environment
        env.store.phones[CUSTOMER] = "+584120000000"
        if name in NEEDS_LINK:
            env.store.links[(TENANT, CUSTOMER)] = Link(host_id=HOST_ID)
        serve_everything(env.rec)
        ids = env.photos.give(CUSTOMER, 2)
        await tool(name).invoke(_args(name, ids))
        sent = env.rec.sent

    if name != "quedate.recent_photos":
        assert sent, f"{name} no llamó a Quédate"
    for s in sent:
        where = f"{name}: {s.method} {s.path}"
        assert s.host == HOSTS[environment], where
        if s.path.startswith("/agent/"):
            op = agent_op(s.method, s.path)
            assert op is not None, f"{where} no está en la API del agente"
            assert s.headers.get("authorization") == f"Bearer {env.store.token}", where
            assert set(s.params) <= op.query, where
            if op.json_allowed is not None:
                assert isinstance(s.body, dict), where
                assert set(s.body) <= op.json_allowed, f"{where}: {set(s.body) - op.json_allowed}"
                assert op.json_required <= set(s.body), (
                    f"{where}: faltan {op.json_required - set(s.body)}"
                )
            else:
                assert s.body is None, where
            if op.parts_allowed is not None:
                assert s.parts, where
                assert set(s.parts) <= op.parts_allowed, where
                assert op.parts_required <= set(s.parts), where
            if s.method == "PATCH":
                assert s.body["status"] in {"pending_approval", "hidden"}, where
        else:
            op_g = spec.operation(s.method, s.path)
            assert op_g is not None, f"{where} no está en el contrato general"
            assert "authorization" not in s.headers, f"{where}: una pública lleva clave"
            assert set(s.params) <= spec.query_names(op_g), where
            schema = spec.body_schema(op_g)
            if schema is not None:
                props = set(schema.get("properties", {}))
                assert set(s.body) <= props, where
                assert set(schema.get("required", [])) <= set(s.body), where


@pytest.mark.parametrize("status", ["published", "draft", "active"])
async def test_the_client_never_sends_any_status_but_review_or_hidden(status: str) -> None:
    """Luis, 2026-11-16: el agente nunca publica."""
    client = QuedateClient(token="k")
    with pytest.raises(QuedateValidationError):
        await client.set_status(LISTING_ID, status)  # type: ignore[arg-type]


FORBIDDEN_ARGS = {"tenant_id", "customer_id", "conversation_id", "token", "api_key", "key"}


@pytest.mark.parametrize("cls", tools.QUEDATE_TOOLS, ids=lambda c: c.name)
def test_no_tool_takes_identity_or_keys_as_arguments(cls: Any) -> None:
    props = set(cls.input_model.model_json_schema().get("properties", {}))
    assert not props & FORBIDDEN_ARGS, cls.name
    if cls.name in tools.PERSON_TOOLS:
        assert "host_id" not in props, f"{cls.name}: el anfitrión sale del vínculo"
