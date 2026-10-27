"""Eje C8, con C1 y C9 — el partner no ve cuerpos, teléfonos de clientes finales
ni costes (spec 047, T021 · requisitos 56.9, 51.2 y 54.11).

Rendimiento (51), sugerencias (51.3), correcciones (52.3) y el Panel (48.4) son
las superficies nuevas de la 047 que resumen lo que pasa en las conversaciones
para el partner: justo donde un cuerpo o un teléfono se cuela «solo para dar
contexto». Hoy existe el Panel; las demás llegan en sus bloques. Este archivo
barre **todas** las rutas del partner de ``/console/*`` y crece solo:

1. **C9 en el esquema**: ninguna respuesta tiene un campo de coste (lo que le
   cuesta a Auphere), salvo las etiquetas relativas inventariadas abajo. El
   partner ve precios, nunca costes (requisito 54.11).
2. **C1/C8 en el esquema**: ningún campo con forma de teléfono, salvo los del
   propio negocio, inventariados uno a uno.
3. **C9 con datos**: sobre ``_partner_world`` —que siembra un coste de modelo
   con dígitos inconfundibles en ``messages`` y ``usage_records``—, ninguna
   lectura del partner los devuelve.
4. **Las superficies**: cada ruta de Panel, Rendimiento, sugerencias o
   correcciones que exista responde con datos de verdad en ese mundo, para que
   los barridos de arriba y el de cuerpos y teléfonos de ``test_console_scope``
   (§7) no pasen en falso sobre una respuesta vacía. Una superficie nueva entra
   el día que se monta.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from nexus_api.main import app

from ._partner_world import COST_DIGITS, partner_world
from .test_console_scope import (
    _console_routes,
    _fill,
    _partner_reads,
    _query_for,
    _route_ids,
    _route_response_fields,
)

pytestmark = [pytest.mark.isolation]  # asyncio_mode=auto

_COST = re.compile(r"cost|margin|markup|provider_price")
_PHONE = re.compile(r"phone|msisdn|wa_id|identifier|from_number|to_number|e164")

#: ``(esquema, campo)`` con nombre de coste que no es un coste.
COST_FIELDS_ALLOWED: dict[tuple[str, str], str] = {
    ("ConsoleModelOut", "relative_cost"): (
        "Multiplicador entero respecto al modelo más barato (x1, x3…), sacado de los "
        "pesos de crédito (``models.relative_costs``): un precio relativo, no un coste."
    ),
    ("ModelChoiceOut", "cost_label"): (
        "Etiqueta bajo/medio/alto/desconocido (``model_choices.cost_labels``)."
    ),
}

#: ``(esquema, campo)`` con forma de teléfono que es del propio negocio.
PHONE_FIELDS_ALLOWED: dict[tuple[str, str], str] = {
    ("ClientHealthOut", "display_phone_number"): "El número de WhatsApp del negocio.",
    ("ChannelOut", "provider_identifier"): "El número o el id del canal del negocio.",
    ("ChannelDetailOut", "provider_identifier"): "El número o el id del canal del negocio.",
    ("LinkSignupOut", "display_phone_number"): "El número que el dueño acaba de conectar.",
    ("WhatsAppSignupOut", "display_phone_number"): "El número que se acaba de conectar.",
    ("AudienceNumberOut", "phone"): (
        "Los números que el propio partner escribió para «Solo mi equipo»: no salen "
        "de ninguna conversación. Las excepciones de «A todos» (32.3) entran aquí "
        "con la misma regla: los teclea el partner."
    ),
    ("LocationOut", "phone_e164"): (
        "El teléfono de una sede del propio negocio (las sedes de Negocio, requisito 9.1): lo "
        "escribe el partner o lo lee de la web del negocio, nunca de una conversación."
    ),
}

#: Las superficies de la 047 que resumen conversaciones para el partner. El
#: Panel del cliente (T067) entra el día que se monta.
SURFACES: dict[str, re.Pattern[str]] = {
    "panel": re.compile(
        r"^/console/home$|^/console/clients/\{ref\}$|^/console/clients/\{ref\}/panel$"
        r"|/conversations(/stats)?$"
    ),
    "rendimiento": re.compile(r"/performance"),
    "sugerencias": re.compile(r"/suggestions"),
    "correcciones": re.compile(r"/corrections"),
}


def _partner_fields(pattern: re.Pattern[str]) -> dict[tuple[str, str], list[str]]:
    openapi = app.openapi()
    components = openapi["components"]["schemas"]
    found: dict[tuple[str, str], list[str]] = {}
    for route_id in _route_ids():
        method, path = route_id.split(" ", 1)
        if path.startswith("/console/lite"):
            continue
        op = openapi["paths"][path][method.lower()]
        for owner, prop in _route_response_fields(op, components):
            if pattern.search(prop):
                found.setdefault((owner, prop), []).append(route_id)
    return found


# ── 1 y 2: el esquema ──────────────────────────────────────────────────────


def test_no_partner_response_carries_a_cost() -> None:
    found = _partner_fields(_COST)
    offenders = {
        f"{o}.{p}": routes for (o, p), routes in found.items() if (o, p) not in COST_FIELDS_ALLOWED
    }
    assert not offenders, f"respuestas del partner con costes (C9): {offenders}"
    assert not COST_FIELDS_ALLOWED.keys() - found.keys(), (
        "excepciones de coste que ya no hacen falta"
    )


def test_no_partner_response_carries_a_phone_but_the_business_own() -> None:
    found = _partner_fields(_PHONE)
    offenders = {
        f"{o}.{p}": routes for (o, p), routes in found.items() if (o, p) not in PHONE_FIELDS_ALLOWED
    }
    assert not offenders, f"respuestas del partner con teléfonos (C1/C8): {offenders}"
    assert not PHONE_FIELDS_ALLOWED.keys() - found.keys(), "excepciones de teléfono que sobran"


def test_the_schema_checks_see_a_planted_field() -> None:
    """Control: el mismo recorrido, sobre un esquema con un coste y un teléfono."""
    comps = {
        "RowOut": {
            "title": "RowOut",
            "properties": {
                "cost_micros": {"type": "integer"},
                "customer_phone": {"type": "string"},
                "turns": {"type": "integer"},
            },
        }
    }
    op = {
        "responses": {"200": {"content": {"application/json": {"schema": {"$ref": "#/x/RowOut"}}}}}
    }
    fields = _route_response_fields(op, comps)
    assert {p for _o, p in fields if _COST.search(p)} == {"cost_micros"}
    assert {p for _o, p in fields if _PHONE.search(p)} == {"customer_phone"}


# ── 3 y 4: con datos ───────────────────────────────────────────────────────


async def _read_everything(client, world: dict[str, Any]) -> dict[str, tuple[int, str]]:
    openapi = app.openapi()
    components = openapi["components"]["schemas"]
    out: dict[str, tuple[int, str]] = {}
    for path in _partner_reads():
        op = openapi["paths"][path]["get"]
        resp = await client.get(
            _fill(path, ref=world["ref"], ids=world["ids"]),
            params=_query_for(op, world, components),
            headers=world["headers"](),
        )
        out[path] = (resp.status_code, resp.text)
    return out


async def test_no_partner_read_returns_a_model_cost(client, db_session, console_world) -> None:
    world = await partner_world(db_session, console_world)
    answers = await _read_everything(client, world)
    leaked = sorted(path for path, (_status, text) in answers.items() if COST_DIGITS in text)
    assert not leaked, f"lecturas del partner que devuelven el coste del modelo (C9): {leaked}"


async def test_every_surface_answers_with_real_data(client, db_session, console_world) -> None:
    world = await partner_world(db_session, console_world)
    reads = set(_partner_reads())
    mounted = {
        surface: sorted(p for p in reads if pattern.search(p))
        for surface, pattern in SURFACES.items()
    }
    assert mounted["panel"], "no encuentro las rutas del Panel; ¿cambiaron de sitio?"
    answers = await _read_everything(client, world)
    for surface, paths in mounted.items():
        for path in paths:
            status, text = answers[path]
            assert status == 200, f"{surface}: {path} → {status} {text[:200]}"
            leaked = [
                label
                for label, canary in world["canaries"].words_and_phones().items()
                if canary in text
            ]
            assert not leaked, f"{surface}: {path} devuelve {leaked}"
    # El Panel cuenta las conversaciones del mundo: la respuesta no está vacía.
    stats = answers["/console/clients/{ref}/conversations/stats"]
    assert '"conversations":' in stats[1] and '"conversations":0' not in stats[1], stats[1][:200]
    # El Panel del cliente (T067) también: su mes cuenta las del mundo.
    panel = answers["/console/clients/{ref}/panel"]
    assert '"conversations":' in panel[1] and '"conversations":0,' not in panel[1], panel[1][:300]


def test_every_partner_read_is_swept() -> None:
    """Las lecturas del barrido son todas las GET del partner salvo las SSE."""
    gets = {
        r.path
        for r in _console_routes()
        if "GET" in r.methods and not r.path.startswith("/console/lite")
    }
    assert set(_partner_reads()) == {p for p in gets if not p.endswith("/stream")}
