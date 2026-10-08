"""Isolation guarantee — scope of the ``/console/*`` family (CP-04, CP-21).

Structural tests over EVERY registered console route — not a sample. A
new endpoint is covered the moment it is mounted; one that breaks a rule
turns this red before it can ship.

1. **No endpoint accepts ``tenant_id`` or ``partner_id``** — in the path,
   the query, a header, or anywhere in the request body schema.
2. **No response schema carries an internal tenant id** — a partner
   speaks ``external_client_ref``.
3. **No response schema can carry a message body** (decision C8): the
   OpenAPI of ``/console/*`` is walked and any property named like
   content is refused (``content``, ``text``, ``body``, ``transcript``,
   ``media_transcript``, ``interactive_payload``, ``tool_calls``, ``notes``,
   ``reason``, ``takeover_context``, ``outcome_feedback``…). The agent's
   own ``system_prompt`` is the partner's asset and is allow-listed. A
   property whose value is a closed vocabulary (an enum) cannot carry
   anyone's words and does not count. **One exception, by prefix**: the
   Inbox of the client console (``/console/lite/inbox/*``, spec 030) — see
   ``BODY_ROUTES_PREFIX``.
4. **Every ``{ref}`` route resolves the client under the principal's
   partner**: partner A calling any client route with partner B's ref gets
   an opaque 404, and the body is byte-identical to the one for a ref that
   does not exist at all.
5. **Every route is behind the console principal**: no token → 401 on
   every registered path.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.routing import APIRoute

from nexus_api.main import app

pytestmark = [pytest.mark.isolation]

FORBIDDEN_PARAMS = {"tenant_id", "partner_id", "tenantid", "partnerid", "tenant", "partner"}

# Property names that would carry a message body. Kept generous on purpose.
FORBIDDEN_RESPONSE_FIELDS = {
    "content",
    "text",
    "body",
    "message",
    "messages",
    "transcript",
    "media_transcript",
    "interactive_payload",
    "tool_calls",
    "takeover_context",
    "outcome_feedback",
    "notes",
    "reason",
    "payload",
    "before_json",
    "after_json",
    "tenant_id",
    "tenantid",
}
# Allowed on the exact models that legitimately own them.
#
# Deliberately TINY, and it stays tiny: this set is subtracted from the
# offenders of EVERY console route, so widening it to unblock one lane
# blinds the check on the other ~60 endpoints.
#
# The Companion (CO-01) is the one lane that legitimately serves a
# transcript over REST — its own, never an end customer's: what Auphere
# said to the partner and what the partner said back. It does NOT get an
# entry here. ``GET /console/companion/runs/{id}/events`` answers
# ``{seq, event, data}`` with ``data`` as an untyped object, which is the
# honest shape (the payloads are heterogeneous by design) and therefore
# carries no property name for the walk below to inspect. That is not a
# guarantee — an opaque dict can hold anything — so the guarantee is built
# where the events are WRITTEN: ``api/companion_streaming.py`` publishes
# against a closed catalogue of event → allowed payload keys, and
# ``test_companion_no_customer_bodies.py`` proves no key in it can carry an
# end customer's message body. Any Companion tool added in CO-02+ has to
# pass that test, not this one.
ALLOWED_RESPONSE_FIELDS = {"system_prompt", "summary", "detail"}

# Exact ``(schema, property)`` pairs whose NAME looks like a body but whose
# VALUE cannot carry an end customer's words. Keyed by schema, never by name
# alone, so an entry here blinds nothing else. Each one says why.
ALLOWED_FIELDS_BY_SCHEMA: dict[tuple[str, str], str] = {
    ("CatalogErrorOut", "message"): (
        "What Meta answered when it rejected a catalogue operation — a "
        "provider error about the partner's product catalogue, never text a "
        "customer wrote."
    ),
}

# Spec 030 (ADR-041): the Inbox of the client console is the ONE place in
# ``/console/*`` that serves message bodies — thread text, the internal
# note, saved replies. C8 protects the end customer's words from the
# PARTNER; a business reading its OWN conversations does not cross that
# line. What keeps this from being a hole:
#
# - only the person of a client with the ``inbox`` module reaches these
#   routes (``require_client_principal("inbox")``); no partner member does —
#   ``test_lite_bodies_only_in_inbox.py`` calls every one of them with a
#   partner token and with a client WITHOUT the module and expects 403;
# - every query runs under that client's RLS, so a body of another client
#   does not exist for it (``test_lite_client_vs_client.py``);
# - internal ids never come back, here or anywhere (``tenant_id`` stays
#   forbidden on these routes too).
#
# It sits next to the Companion's for the same reason: two lanes that serve
# text, each with its own proof, and nothing widened for the other ~60
# endpoints.
BODY_ROUTES_PREFIX = "/console/lite/inbox/"


def _console_routes() -> list[APIRoute]:
    return [r for r in app.routes if isinstance(r, APIRoute) and r.path.startswith("/console")]


def _route_ids() -> list[str]:
    return [f"{sorted(r.methods)[0]} {r.path}" for r in _console_routes()]


def _walk_schema(node: Any, components: dict[str, Any], seen: set[str], out: set[str]) -> None:
    """Collect every property name reachable from ``node``."""
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            name = ref.rsplit("/", 1)[-1]
            if name not in seen:
                seen.add(name)
                _walk_schema(components.get(name, {}), components, seen, out)
            return
        # An OpenAPI response or request body wraps its schema in
        # ``content → <media type> → schema``. Without this descent the walk
        # starts at the wrapper, finds no properties, and every check below
        # passes vacuously — which is exactly what happened until spec 030.
        for media in (node.get("content") or {}).values():
            if isinstance(media, dict):
                _walk_schema(media.get("schema"), components, seen, out)
        for prop in node.get("properties") or {}:
            out.add(prop)
        for key in ("items", "additionalProperties"):
            if key in node:
                _walk_schema(node[key], components, seen, out)
        for key in ("anyOf", "oneOf", "allOf"):
            for sub in node.get(key) or []:
                _walk_schema(sub, components, seen, out)
        for prop_schema in (node.get("properties") or {}).values():
            _walk_schema(prop_schema, components, seen, out)
    elif isinstance(node, list):
        for item in node:
            _walk_schema(item, components, seen, out)


def _is_closed_vocabulary(node: Any, components: dict[str, Any]) -> bool:
    """An enum (or a single constant), optionally nullable: no free text fits."""
    if not isinstance(node, dict):
        return False
    ref = node.get("$ref")
    if isinstance(ref, str):
        return _is_closed_vocabulary(components.get(ref.rsplit("/", 1)[-1], {}), components)
    if "enum" in node or "const" in node:
        return True
    options = node.get("anyOf") or node.get("oneOf")
    if options:
        real = [o for o in options if not (isinstance(o, dict) and o.get("type") == "null")]
        return bool(real) and all(_is_closed_vocabulary(o, components) for o in real)
    return False


def _response_fields(
    node: Any,
    components: dict[str, Any],
    seen: set[str],
    out: set[tuple[str, str]],
    owner: str = "",
) -> None:
    """Every ``(schema, property)`` that can carry free text, reachable from
    ``node`` — through the OpenAPI ``content → schema`` wrapper too."""
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            name = ref.rsplit("/", 1)[-1]
            if name not in seen:
                seen.add(name)
                schema = components.get(name, {})
                _response_fields(schema, components, seen, out, schema.get("title") or name)
            return
        for media in (node.get("content") or {}).values():
            if isinstance(media, dict):
                _response_fields(media.get("schema"), components, seen, out, owner)
        for prop, prop_schema in (node.get("properties") or {}).items():
            if not _is_closed_vocabulary(prop_schema, components):
                out.add((owner, prop))
            _response_fields(prop_schema, components, seen, out, owner)
        for key in ("items", "additionalProperties"):
            if key in node:
                _response_fields(node[key], components, seen, out, owner)
        for key in ("anyOf", "oneOf", "allOf"):
            for sub in node.get(key) or []:
                _response_fields(sub, components, seen, out, owner)
    elif isinstance(node, list):
        for item in node:
            _response_fields(item, components, seen, out, owner)


def _route_response_fields(op: dict[str, Any], components: dict[str, Any]) -> set[tuple[str, str]]:
    fields: set[tuple[str, str]] = set()
    for status_code, resp in op.get("responses", {}).items():
        if str(status_code).startswith("2"):
            _response_fields(resp, components, set(), fields)
    return fields


def _offenders(path: str, fields: set[tuple[str, str]]) -> set[str]:
    in_inbox = path.startswith(BODY_ROUTES_PREFIX)
    out: set[str] = set()
    for owner, prop in fields:
        if prop not in FORBIDDEN_RESPONSE_FIELDS or prop in ALLOWED_RESPONSE_FIELDS:
            continue
        if (owner, prop) in ALLOWED_FIELDS_BY_SCHEMA:
            continue
        if in_inbox and prop not in {"tenant_id", "tenantid"}:
            continue
        out.add(f"{owner}.{prop}")
    return out


@pytest.fixture(scope="module")
def openapi() -> dict[str, Any]:
    return app.openapi()


def test_the_family_is_mounted() -> None:
    routes = _console_routes()
    assert len(routes) >= 20, [r.path for r in routes]


@pytest.mark.parametrize("route_id", _route_ids())
def test_no_route_accepts_tenant_or_partner_identifiers(
    route_id: str, openapi: dict[str, Any]
) -> None:
    method, path = route_id.split(" ", 1)
    op = openapi["paths"][path][method.lower()]
    # Path / query / header params.
    for param in op.get("parameters", []):
        assert param["name"].lower().replace("-", "_") not in FORBIDDEN_PARAMS, (
            f"{route_id} accepts {param['name']} in {param['in']}"
        )
    # Request body properties, recursively.
    body = op.get("requestBody")
    if body:
        props: set[str] = set()
        _walk_schema(body, openapi["components"]["schemas"], set(), props)
        offenders = {p for p in props if p.lower() in FORBIDDEN_PARAMS}
        assert not offenders, f"{route_id} body accepts {offenders}"


@pytest.mark.parametrize("route_id", _route_ids())
def test_no_response_carries_bodies_or_internal_ids(route_id: str, openapi: dict[str, Any]) -> None:
    method, path = route_id.split(" ", 1)
    op = openapi["paths"][path][method.lower()]
    fields = _route_response_fields(op, openapi["components"]["schemas"])
    offenders = _offenders(path, fields)
    assert not offenders, f"{route_id} response exposes {offenders}"


def test_the_walk_reads_real_responses(openapi: dict[str, Any]) -> None:
    """Control of the control, on the REAL OpenAPI.

    Until spec 030 the walk started at the response wrapper
    (``{"content": {"application/json": {"schema": …}}}``), found no
    properties and let every route pass — the check above was vacuous for
    every console endpoint and nobody noticed, because the only control fed
    the walker an already-unwrapped schema. This one fails if that happens
    again: every route whose 2xx answer is a JSON object must yield fields.
    """
    components = openapi["components"]["schemas"]
    empty: list[str] = []
    for route_id in _route_ids():
        method, path = route_id.split(" ", 1)
        op = openapi["paths"][path][method.lower()]
        refs = [
            media.get("schema", {}).get("$ref")
            for code, resp in op.get("responses", {}).items()
            if str(code).startswith("2")
            for media in (resp.get("content") or {}).values()
        ]
        seen_props: set[str] = set()
        for code, resp in op.get("responses", {}).items():
            if str(code).startswith("2"):
                _walk_schema(resp, components, set(), seen_props)
        if any(refs) and not seen_props:
            empty.append(route_id)
    assert not empty, f"responses walked to nothing: {empty}"
    thread = openapi["paths"]["/console/lite/inbox/conversations/{conversation_id}/messages"]
    assert ("ThreadItemOut", "text") in _route_response_fields(thread["get"], components)


def test_closed_vocabularies_and_the_inbox_are_the_only_ways_out() -> None:
    """The exceptions are exact: a free-text ``reason`` is still caught, the
    same field under the Inbox is not, and ``tenant_id`` never passes."""
    comps = {
        "Free": {"title": "Free", "properties": {"reason": {"type": "string"}}},
        "Closed": {
            "title": "Closed",
            "properties": {"reason": {"anyOf": [{"enum": ["a", "b"]}, {"type": "null"}]}},
        },
        "Leak": {"title": "Leak", "properties": {"tenant_id": {"type": "string"}}},
    }
    walk = lambda name: _response_fields({"$ref": f"#/x/{name}"}, comps, set(), out := set()) or out  # noqa: E731
    assert _offenders("/console/clients/{ref}/x", walk("Free")) == {"Free.reason"}
    assert _offenders("/console/clients/{ref}/x", walk("Closed")) == set()
    assert _offenders("/console/lite/inbox/x", walk("Free")) == set()
    assert _offenders("/console/lite/inbox/x", walk("Leak")) == {"Leak.tenant_id"}


def test_the_body_check_would_catch_a_leak(openapi: dict[str, Any]) -> None:
    """Control of the control: a schema with ``content`` is detected."""
    fake = {"properties": {"items": {"type": "array", "items": {"$ref": "#/components/schemas/X"}}}}
    comps = {"X": {"properties": {"content": {"type": "string"}}}}
    props: set[str] = set()
    _walk_schema(fake, comps, set(), props)
    assert "content" in props


@pytest.mark.parametrize("route_id", _route_ids())
async def test_every_route_requires_the_principal(route_id: str, client) -> None:
    method, path = route_id.split(" ", 1)
    concrete = _fill(path, ref="whatever")
    resp = await client.request(method, concrete)
    assert resp.status_code == 401, f"{route_id} answered {resp.status_code} without a token"


def _fill(path: str, *, ref: str) -> str:
    """Give every path parameter a syntactically valid value."""
    return (
        path.replace("{ref}", ref)
        .replace("{version}", "1")
        .replace("{key_id}", str(uuid.uuid4()))
        .replace("{channel_id}", str(uuid.uuid4()))
        .replace("{name}", "hello_world")
        .replace("{membership_id}", str(uuid.uuid4()))
        .replace("{invitation_id}", str(uuid.uuid4()))
        .replace("{token}", "a" * 43)
        .replace("{tool_name}", "calendar.list_slots")
        .replace("{doc_id}", str(uuid.uuid4()))
        .replace("{device_id}", str(uuid.uuid4()))  # spec 002: máquinas del partner
        .replace("{thread_id}", str(uuid.uuid4()))
        .replace("{run_id}", str(uuid.uuid4()))
        .replace("{notification_id}", str(uuid.uuid4()))
        .replace("{teammate_id}", str(uuid.uuid4()))  # spec 003: el roster
        .replace("{task_id}", str(uuid.uuid4()))
        .replace("{action_id}", str(uuid.uuid4()))
        # spec 030: la Bandeja del cliente
        .replace("{conversation_id}", str(uuid.uuid4()))
        .replace("{message_id}", str(uuid.uuid4()))
        .replace("{reply_id}", str(uuid.uuid4()))
    )


def _minimal_body(route: APIRoute) -> dict[str, Any] | None:
    """A body that passes validation for the client-scoped write routes, so
    the 404 we assert is the mapping's and not a 422."""
    bodies = {
        ("PATCH", "/console/clients/{ref}"): {"name": "x"},
        ("POST", "/console/clients/{ref}/status"): {"status": "paused"},
        ("DELETE", "/console/clients/{ref}"): {"confirm_name": "x"},
        ("POST", "/console/clients/{ref}/agent/versions"): {"system_prompt": "x"},
        ("POST", "/console/clients/{ref}/agent/from-seed"): {
            "seed_template": "generic_v1",
            "placeholders": {},
        },
        ("PUT", "/console/clients/{ref}/agent/settings"): {"settings": {}},
        ("PUT", "/console/clients/{ref}/tools"): {"tools": []},
        ("PUT", "/console/clients/{ref}/tools/{tool_name}/mode"): {"mode": "always"},
        ("PUT", "/console/clients/{ref}/skills"): {"skills": []},
        ("PUT", "/console/clients/{ref}/allocation"): {"cap_cents": 1},
        ("PUT", "/console/clients/{ref}/model"): {"model_id": "openai/gpt-5.6-sol"},
        # Spec 016 (R6): la agenda pública de AgendaPro.
        ("PUT", "/console/clients/{ref}/integrations/agendapro/public-url"): {
            "public_url": "https://demo.site.agendapro.com/cl/sucursal"
        },
        ("PUT", "/console/clients/{ref}/workflow"): {
            "trigger": "event",
            "steps": ["end"],
            "stop": "end",
        },
        ("POST", "/console/clients/{ref}/knowledge/url"): {"url": "https://example.com/x"},
        ("POST", "/console/knowledge/url"): {"url": "https://example.com/x"},
        ("POST", "/console/clients/{ref}/channels/whatsapp/signup"): {
            "code": "x",
            "waba_id": "1",
            "mode": "cloud_api",
        },
        ("POST", "/console/clients/{ref}/channels/whatsapp/templates"): {
            "name": "x",
            "body_text": "hi",
        },
        ("PATCH", "/console/clients/{ref}/channels/{channel_id}/role"): {"role": "agent"},
        ("POST", "/console/clients/{ref}/channels/diagnostics/test-send"): {"to": "+34600000000"},
        ("POST", "/console/clients/{ref}/playground/threads"): {"title": "x"},
        ("PATCH", "/console/clients/{ref}/playground/threads/{thread_id}"): {"title": "x"},
        ("POST", "/console/clients/{ref}/playground/threads/{thread_id}/runs"): {"prompt": "x"},
    }
    return bodies.get((sorted(route.methods)[0], route.path))


@pytest.mark.parametrize(
    "route_id",
    [rid for rid in _route_ids() if "{ref}" in rid],
)
async def test_other_partners_client_ref_is_an_opaque_404(
    route_id: str, client, console_world
) -> None:
    """Partner A + partner B's ref → 404 with the SAME body as a ref that
    does not exist. Parametrised over every client-scoped route."""
    method, path = route_id.split(" ", 1)
    route = next(r for r in _console_routes() if r.path == path and method in r.methods)
    a, b = console_world["a"], console_world["b"]
    body = _minimal_body(route)

    foreign = await client.request(
        method, _fill(path, ref=b["ref"]), headers=a["headers"](), json=body
    )
    missing = await client.request(
        method, _fill(path, ref="does-not-exist"), headers=a["headers"](), json=body
    )
    assert foreign.status_code == 404, f"{route_id}: {foreign.status_code} {foreign.text}"
    assert missing.status_code == 404
    assert foreign.json() == missing.json() == {"detail": "Unknown client reference"}


# ── 6. la lectura compuesta del Resumen (spec 018, R1) ─────────────────


async def test_the_summary_composes_four_reads_and_none_of_them_leaks(
    client, console_world, db_session
) -> None:
    """El Resumen junta cuatro lecturas; juntarlas no puede abrir una puerta.

    Tres de las cuatro son rutas ``{ref}`` y ya las cubre la barrida
    parametrizada de arriba. **La cuarta no**: el consumo se pide con
    ``/console/usage?client={ref}``, que es una ruta de partner con un
    filtro en la query — no la ve ningún caso de los anteriores, y es
    justo por donde se leería el gasto de un cliente ajeno.
    """
    a, b = console_world["a"], console_world["b"]

    ajeno = await client.get(f"/console/usage?client={b['ref']}&days=30", headers=a["headers"]())
    fantasma = await client.get("/console/usage?client=no-existe&days=30", headers=a["headers"]())

    # Contesta 404, no un informe vacío — que es más fuerte de lo que hacía
    # falta: ni siquiera devuelve la forma del informe. Y el cuerpo es el
    # mismo que para un ref que no existe, así que no se puede averiguar si
    # ese cliente es de alguien.
    assert ajeno.status_code == fantasma.status_code == 404
    assert ajeno.json() == fantasma.json()
    assert b["ref"] not in ajeno.text

    # Y las otras tres, compuestas como las compone la pantalla, siguen
    # contestando lo mismo que por separado: 404 opaco.
    for path in (
        f"/console/clients/{b['ref']}",
        f"/console/clients/{b['ref']}/conversations/stats",
        f"/console/clients/{b['ref']}/channels",
        f"/console/clients/{b['ref']}/connectors",
    ):
        r = await client.get(path, headers=a["headers"]())
        assert r.status_code == 404, f"{path} → {r.status_code}"
        assert r.json() == {"detail": "Unknown client reference"}
