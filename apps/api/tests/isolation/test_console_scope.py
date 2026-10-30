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

import re
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
    ("VisibleOut", "reason"): (
        "Spec 047: the code of why an agent or a channel is paused or has a "
        "problem (``manual``, ``no_balance``, ``agent_cap``, ``auth_expired``…), "
        "set by the system or by a console action — never text."
    ),
    ("SessionOut", "transcript"): (
        "Spec 047 (requisito 20): a playground session over the agent's draft, "
        "with simulated time and agenda. Every «customer» turn is typed by the "
        "partner's own person testing; the playground has no channel, so no end "
        "customer can be in it."
    ),
    ("TestOut", "transcript"): (
        "Spec 047, enmienda (61.6): the conversation of one run of the agent's "
        "own test, between the draft and Auphere's simulated customer over a "
        "simulated agenda, without a channel: no end customer takes part in it. "
        "What it CAN carry of one (T217, security review of 2026-10-30): a test "
        "created from a weekly suggestion (``kind = conversation``, "
        "``services/improvement/suggestions.py``) has its ``first_message``, "
        "``persona`` and ``plan`` written by a model that read the week's real "
        "conversations, masked only for names, phones, e-mails and documents; "
        "the simulated customer then speaks from them, and ``TestOut`` serves "
        "those three fields too. Contained by: the model is told never to copy "
        "a real message; ``_store`` drops the suggestion whose texts carry a "
        "contact's data (``Contacts.found_in``) or whose test copies a message "
        "of the batch almost literally (word n-grams, ``copies_a_message``); "
        "and only members of the partner that owns the client, with "
        "``agents:read``, read it. The residue that stays: a paraphrase that is "
        "not literal and names no one."
    ),
    ("TestAttemptOut", "transcript"): (
        "Every pass of the last run of a test: the same conversations as "
        "``TestOut.transcript`` (which is one of them), with the same residue "
        "and the same containment. Typed so this walk reads it."
    ),
    ("TestTurnOut", "text"): (
        "One turn of those conversations: what the simulated customer or the "
        "draft said. See ``TestOut.transcript``."
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


def test_every_pass_of_a_test_is_seen_by_the_walk(openapi: dict[str, Any]) -> None:
    """Spec 047, T217 (security review of 2026-10-30): the passes of a test
    (``TestOut.attempts``) carry the same conversations as ``TestOut.transcript``.
    Typed, the walk reads them, word for word, and their exceptions are explicit
    in ``ALLOWED_FIELDS_BY_SCHEMA``; an untyped ``dict`` would hide them."""
    components = openapi["components"]["schemas"]
    suite = openapi["paths"]["/console/clients/{ref}/agents/{agent_id}/tests"]["get"]
    fields = _route_response_fields(suite, components)
    for pair in (("TestOut", "transcript"), ("TestAttemptOut", "transcript")):
        assert pair in fields, sorted(fields)
        assert pair in ALLOWED_FIELDS_BY_SCHEMA, pair
    assert ("TestTurnOut", "text") in fields
    assert ("TestTurnOut", "text") in ALLOWED_FIELDS_BY_SCHEMA


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


def _fill(path: str, *, ref: str, ids: dict[str, str] | None = None) -> str:
    """Give every path parameter a syntactically valid value.

    ``ids`` points a parameter at a REAL object (spec 047, T021): the C8 sweep
    below fills ``{conversation_id}``, ``{channel_id}``, ``{job_id}``… with
    objects of a client whose base is full of message bodies and phones, so a
    route that leaked them would answer with them instead of a 404. Any
    parameter nobody names gets a fresh UUID: a route mounted tomorrow with a
    new ``{x}`` is filled the day it lands, never left as literal braces."""
    for name, value in (ids or {}).items():
        path = path.replace("{" + name + "}", value)
    path = (
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
        # spec 031: los teléfonos de la persona de cliente
        .replace("{phone_id}", str(uuid.uuid4()))
    )
    return re.sub(r"\{[a-z_]+\}", lambda _m: str(uuid.uuid4()), path)


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
        # Spec 047: el constructor, las pruebas, la publicación y la bolsa.
        ("POST", "/console/clients/{ref}/agents/draft-jobs"): {"name": "x", "start": "blank"},
        ("POST", "/console/clients/{ref}/agents/{agent_id}/test-runs"): {"scope": "all"},
        ("POST", "/console/clients/{ref}/agents/{agent_id}/publish"): {},
        ("POST", "/console/clients/{ref}/bag/assign"): {
            "amount": {"amount_micros": 100000, "currency": "USD"}
        },
        ("POST", "/console/clients/{ref}/bag/lower"): {
            "amount": {"amount_micros": 100000, "currency": "USD"}
        },
        ("PUT", "/console/clients/{ref}/bag/refill"): {"up_to": None},
        ("PUT", "/console/clients/{ref}/bag/currency"): {"currency": "USD"},
        ("POST", "/console/clients/{ref}/bag/request"): {},
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


# ── 7. C8 con datos: ninguna lectura del partner trae palabras ni teléfonos ──
#
# Spec 047, T021 (requisitos 56.9 y 51.2). Las comprobaciones 1-3 miran el
# OpenAPI: un campo que se llame como un cuerpo. Esta mira lo que la ruta
# DEVUELVE de verdad, contra una base llena de cuerpos de mensaje, notas,
# transcripciones, llamadas a herramientas, nombres y teléfonos de clientes
# finales (``_partner_world``). Un campo con nombre inocente (``summary``,
# ``detail``, un ``dict`` sin tipo) que acabara llevando el mensaje de alguien
# lo pone en rojo. Recorre todas las lecturas del partner, las de A2 incluidas
# (``/console/jobs/{job_id}``, ``/console/search``), el día que se montan.

_SEARCH_PARAMS = {"q", "query", "search", "term"}


def _partner_reads() -> list[str]:
    return sorted(
        r.path
        for r in _console_routes()
        if "GET" in r.methods
        and not r.path.startswith("/console/lite")
        # Las de SSE no terminan; lo que emiten lo cubren sus propias suites.
        and not r.path.endswith("/stream")
    )


def _sample(schema: dict[str, Any], components: dict[str, Any]) -> str:
    """Un valor válido para un parámetro obligatorio de la query."""
    ref = schema.get("$ref")
    if isinstance(ref, str):
        return _sample(components.get(ref.rsplit("/", 1)[-1], {}), components)
    for option in schema.get("anyOf") or schema.get("oneOf") or []:
        if option.get("type") != "null":
            return _sample(option, components)
    if "enum" in schema:
        return str(schema["enum"][0])
    kind, fmt = schema.get("type"), schema.get("format")
    if kind in {"integer", "number"}:
        return str(schema.get("minimum", 1))
    if kind == "boolean":
        return "true"
    if fmt == "uuid":
        return str(uuid.uuid4())
    if fmt == "date":
        return "2026-10-01"
    if fmt == "date-time":
        return "2026-10-01T00:00:00Z"
    return "x"


def _query_for(
    op: dict[str, Any], world: dict[str, Any], components: dict[str, Any]
) -> dict[str, str]:
    """Los obligatorios, con un valor válido; los de búsqueda, con el nombre del
    cliente final (buscarlo es otra forma de filtrarlo); el cliente, el de A."""
    params: dict[str, str] = {}
    for p in op.get("parameters", []):
        if p.get("in") != "query":
            continue
        name = p["name"]
        if name in _SEARCH_PARAMS:
            params[name] = world["canaries"].name
        elif name in {"client", "ref", "client_ref"}:
            params[name] = world["ref"]
        elif p.get("required"):
            params[name] = _sample(p.get("schema") or {}, components)
    return params


@pytest.mark.parametrize("path", _partner_reads())
async def test_no_partner_read_carries_an_end_customers_words_or_phone(
    path: str, client, db_session, console_world, openapi: dict[str, Any]
) -> None:
    from ._partner_world import partner_world

    world = await partner_world(db_session, console_world)
    op = openapi["paths"][path]["get"]
    resp = await client.get(
        _fill(path, ref=world["ref"], ids=world["ids"]),
        params=_query_for(op, world, openapi["components"]["schemas"]),
        headers=world["headers"](),
    )
    leaked = sorted(
        label
        for label, canary in world["canaries"].words_and_phones().items()
        if canary in resp.text
    )
    assert not leaked, f"GET {path} ({resp.status_code}) devuelve: {leaked}"


async def test_the_c8_sweep_reaches_real_data(client, db_session, console_world) -> None:
    """Control del control: el mundo tiene los datos y las rutas llegan a ellos.

    Las conversaciones del partner las cuentan (sin cuerpos), el trabajo existe
    para ``/console/jobs/{job_id}``, y la Bandeja de la persona del cliente —el
    único sitio de ``/console/*`` que sirve cuerpos— sí devuelve el cuerpo
    marcado: si no, su ausencia en las rutas del partner no probaría nada."""
    from ._partner_world import partner_world

    world = await partner_world(db_session, console_world)
    convs = await client.get(
        f"/console/clients/{world['ref']}/conversations", headers=world["headers"]()
    )
    assert convs.status_code == 200 and convs.json()["total"] >= 3, convs.text[:300]
    if any(r.path == "/console/jobs/{job_id}" for r in _console_routes()):
        job = await client.get(
            f"/console/jobs/{world['ids']['job_id']}", headers=world["headers"]()
        )
        assert job.status_code == 200, job.text[:300]
    thread = await client.get(
        f"/console/lite/inbox/conversations/{world['ids']['conversation_id']}/messages",
        headers=world["client_headers"](),
    )
    assert thread.status_code == 200, thread.text[:300]
    assert world["canaries"].body_in in thread.text
    assert world["canaries"].body_out in thread.text


def test_fill_never_leaves_a_parameter_unfilled() -> None:
    """Una ruta con un ``{x}`` que nadie conoce se rellena igual (la de mañana)."""
    filled = _fill("/console/clients/{ref}/agents/{agent_id}/thing/{brand_new}", ref="r")
    assert "{" not in filled and filled.startswith("/console/clients/r/agents/")
    assert _fill("/console/jobs/{job_id}", ref="r", ids={"job_id": "J"}) == "/console/jobs/J"
