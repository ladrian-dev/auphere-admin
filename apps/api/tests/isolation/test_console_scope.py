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
   own ``system_prompt`` is the partner's asset and is allow-listed.
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
ALLOWED_RESPONSE_FIELDS = {"system_prompt", "summary", "detail"}


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
    props: set[str] = set()
    for status_code, resp in op.get("responses", {}).items():
        if not str(status_code).startswith("2"):
            continue
        _walk_schema(resp, openapi["components"]["schemas"], set(), props)
    offenders = (props & FORBIDDEN_RESPONSE_FIELDS) - ALLOWED_RESPONSE_FIELDS
    assert not offenders, f"{route_id} response exposes {offenders}"


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
        .replace("{membership_id}", str(uuid.uuid4()))
        .replace("{invitation_id}", str(uuid.uuid4()))
        .replace("{token}", "a" * 43)
    )


def _minimal_body(route: APIRoute) -> dict[str, Any] | None:
    """A body that passes validation for the client-scoped write routes, so
    the 404 we assert is the mapping's and not a 422."""
    bodies = {
        ("PATCH", "/console/clients/{ref}"): {"name": "x"},
        ("POST", "/console/clients/{ref}/status"): {"status": "paused"},
        ("DELETE", "/console/clients/{ref}"): {"confirm_name": "x"},
        ("POST", "/console/clients/{ref}/agent/versions"): {"system_prompt": "x"},
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
