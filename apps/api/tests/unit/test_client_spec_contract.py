"""Spec 047, T072 — el ClientSpec de Pydantic es el del contrato (requisito 8.3).

``services/business/client_spec.ClientSpec`` y
``specs/047-la-fabrica-de-agentes/contracts/client-spec.schema.json`` tienen que
decir lo mismo, campo a campo: los mismos nombres, los mismos obligatorios, los
mismos límites, los mismos patrones y vocabularios, lo mismo de solo lectura y
nada más (``additionalProperties: false``). Se comprueba de dos maneras:

1. **Los esquemas, normalizados.** Se resuelven las referencias y se quita lo
   que solo cambia la forma de escribirlo (títulos, descripciones, ``anyOf``
   con ``null`` frente a ``type: [x, "null"]``, ``const`` frente a un ``enum``
   de uno). Lo que queda tiene que ser idéntico. Igual el parche
   (``$defs.patch``).
2. **Con documentos.** Uno completo vale para los dos (``jsonschema`` sobre el
   contrato y Pydantic); cada uno de los rotos, ninguno lo acepta.

Y el validador sin modelo: lo que el esquema no puede decir.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from nexus_api.services.business.client_spec import (
    ClientSpec,
    Patch,
    diff_ops,
    hhmm_to_minutes,
    minutes_to_hhmm,
    state_hash,
    validate_document,
    validate_value,
)

CONTRACT = (
    Path(__file__).resolve().parents[4]
    / "specs"
    / "047-la-fabrica-de-agentes"
    / "contracts"
    / "client-spec.schema.json"
)

_IGNORED = {"title", "description", "default", "$schema", "$id", "examples", "$comment"}


def _resolve(ref: str, root: dict[str, Any]) -> dict[str, Any]:
    node: Any = root
    for part in ref.lstrip("#/").split("/"):
        node = node[part]
    return dict(node)


def normalise(node: Any, root: dict[str, Any], depth: int = 0) -> Any:
    """Lo que dice un esquema, sin la forma de escribirlo."""
    assert depth < 40, "a $ref cycle?"
    if isinstance(node, list):
        return [normalise(n, root, depth + 1) for n in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        outer = {k: v for k, v in node.items() if k != "$ref"}
        merged = {**_resolve(node["$ref"], root), **outer}
        return normalise(merged, root, depth + 1)
    out: dict[str, Any] = {}
    nullable = False
    node = {k: v for k, v in node.items() if k not in _IGNORED}
    for key in ("anyOf", "oneOf"):
        if key not in node:
            continue
        options = node.pop(key)
        if all(isinstance(o, dict) and set(o) == {"required"} for o in options):
            out["requires_one_of"] = sorted(json.dumps(sorted(o["required"])) for o in options)
            continue
        real = [o for o in options if not (isinstance(o, dict) and o.get("type") == "null")]
        nullable = nullable or len(real) != len(options)
        if len(real) == 1:
            node = {**real[0], **node}
        else:
            out["union"] = sorted(
                json.dumps(normalise(o, root, depth + 1), sort_keys=True) for o in real
            )
    kind = node.pop("type", None)
    if isinstance(kind, list):
        nullable = nullable or "null" in kind
        rest = [k for k in kind if k != "null"]
        kind = rest[0] if len(rest) == 1 else sorted(rest)
    if "const" in node:
        node["enum"] = [node.pop("const")]
    if "enum" in node:
        values = node.pop("enum")
        nullable = nullable or None in values
        out["enum"] = sorted(json.dumps(v) for v in values if v is not None)
        kind = None  # el vocabulario ya dice el tipo
    if kind is not None:
        out["type"] = kind
    if nullable:
        out["nullable"] = True
    for key, value in node.items():
        if key == "properties":
            out[key] = {p: normalise(v, root, depth + 1) for p, v in value.items()}
        elif key == "required":
            out[key] = sorted(value)
        elif key in ("items", "if", "then"):
            out[key] = normalise(value, root, depth + 1)
        elif key == "additionalProperties":
            if value is True:
                continue
            out[key] = normalise(value, root, depth + 1) if isinstance(value, dict) else value
        elif key == "$defs":
            continue
        else:
            out[key] = value
    return out


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    return json.loads(CONTRACT.read_text())


def _diff(a: Any, b: Any, path: str = "") -> list[str]:
    if isinstance(a, dict) and isinstance(b, dict):
        out: list[str] = []
        for key in sorted(set(a) | set(b)):
            if key not in a:
                out.append(f"{path}/{key}: only in the contract")
            elif key not in b:
                out.append(f"{path}/{key}: only in Pydantic")
            else:
                out.extend(_diff(a[key], b[key], f"{path}/{key}"))
        return out
    return [] if a == b else [f"{path}: pydantic={a!r} contract={b!r}"]


def test_the_pydantic_schema_is_the_contract(contract: dict[str, Any]) -> None:
    generated = ClientSpec.model_json_schema()
    ours = normalise(generated, generated)
    theirs = normalise(contract, contract)
    assert _diff(ours, theirs) == []


def test_the_patch_is_the_contract(contract: dict[str, Any]) -> None:
    generated = Patch.model_json_schema()
    ours = normalise(generated, generated)
    theirs = normalise(contract["$defs"]["patch"], contract)
    assert _diff(ours, theirs) == []


def test_the_normaliser_sees_a_difference(contract: dict[str, Any]) -> None:
    """Control del control: un límite cambiado se nota."""
    tampered = copy.deepcopy(contract)
    tampered["properties"]["business"]["properties"]["name"]["maxLength"] = 61
    generated = ClientSpec.model_json_schema()
    assert _diff(normalise(generated, generated), normalise(tampered, tampered)) == [
        "/properties/business/properties/name/maxLength: pydantic=60 contract=61"
    ]


# ── con documentos ─────────────────────────────────────────────────────────

FULL: dict[str, Any] = {
    "schema_version": "1",
    "business": {
        "name": "Barbería Cultor",
        "niche": "Barbería de barrio con 2 sedes",
        "info": "cultorbarber.com",
        "website": "https://cultorbarber.com",
        "country": "ES",
        "timezone": "Europe/Madrid",
        "price_currency": "EUR",
        "wallet_currency": "EUR",
        "eu_only": True,
    },
    "locations": [
        {
            "id": "4b0c8a5e-3f0e-4d0b-9b8e-2a6f3a1c9d10",
            "name": "Cultor Centro",
            "address": "Calle Mayor 1, Madrid",
            "phone_e164": "+34600123456",
            "hours": {"layout": "daily", "days": {"mon": [{"open": "10:00", "close": "20:00"}]}},
        }
    ],
    "hours": {
        "layout": "blocks",
        "days": {
            "mon": [{"open": "10:00", "close": "14:00"}, {"open": "16:00", "close": "20:00"}],
            "fri": [{"open": "22:00", "close": "02:00"}],
            "sun": [],
        },
    },
    "special_dates": [
        {"name": "Navidad", "from": "2026-12-25", "to": "2026-12-25", "closed": True},
        {
            "from": "2026-12-31",
            "to": "2026-12-31",
            "closed": False,
            "shifts": [{"open": "10:00", "close": "14:00"}],
        },
    ],
    "services": [
        {
            "name": "Corte de pelo",
            "bookable": True,
            "duration_min": 30,
            "price": {"kind": "amount", "amount_minor": 1500},
            "staff": "all",
        },
        {"name": "Cera", "bookable": False, "price": {"kind": "free"}},
    ],
    "policies": {"cancellation": "Avisa con 24 h.", "payments": "Tarjeta y efectivo."},
    "faqs": [{"q": "¿Hay que pedir cita?", "a": "Sí, por WhatsApp.", "suggested": True}],
    "links": [
        {"network": "web", "url": "https://cultorbarber.com"},
        {"network": "instagram", "handle": "@cultorbarber"},
    ],
}

BROKEN: dict[str, Any] = {
    "an unknown field": {"business_hours": {}},
    "a name of 61": {"business": {"name": "x" * 61}},
    "a niche of 1": {"business": {"niche": "x"}},
    "a lowercase country": {"business": {"country": "es"}},
    "a wallet in GBP": {"business": {"wallet_currency": "GBP"}},
    "seven shifts in a day": {
        "hours": {"layout": "blocks", "days": {"mon": [{"open": "10:00", "close": "11:00"}] * 7}}
    },
    "a closing at 25:00": {
        "hours": {"layout": "blocks", "days": {"mon": [{"open": "10:00", "close": "25:00"}]}}
    },
    "a bookable service without duration": {"services": [{"name": "Corte", "bookable": True}]},
    "a duration of 500": {"services": [{"name": "Corte", "bookable": True, "duration_min": 500}]},
    "a negative price": {
        "services": [
            {"name": "Corte", "bookable": False, "price": {"kind": "amount", "amount_minor": -1}}
        ]
    },
    "a link with neither url nor handle": {"links": [{"network": "instagram"}]},
    "an unknown network": {"links": [{"network": "myspace", "handle": "x"}]},
    "an empty answer": {"faqs": [{"q": "¿Qué?", "a": ""}]},
    "an older schema": {"schema_version": "0"},
}


def _broken(change: dict[str, Any]) -> dict[str, Any]:
    doc = copy.deepcopy(FULL)
    for key, value in change.items():
        if key == "business":
            doc["business"].update(value)
        else:
            doc[key] = value
    return doc


def _contract_accepts(contract: dict[str, Any], doc: dict[str, Any]) -> bool:
    try:
        jsonschema.Draft202012Validator(contract).validate(doc)
    except jsonschema.ValidationError:
        return False
    return True


def test_a_full_document_is_valid_for_both(contract: dict[str, Any]) -> None:
    assert _contract_accepts(contract, FULL)
    spec, problems = validate_document(FULL)
    assert spec is not None and problems == []


@pytest.mark.parametrize("case", sorted(BROKEN))
def test_a_broken_document_is_rejected_by_both(case: str, contract: dict[str, Any]) -> None:
    doc = _broken(BROKEN[case])
    assert not _contract_accepts(contract, doc), f"the contract accepts {case}"
    _spec, problems = validate_document(doc)
    assert problems, f"pydantic accepts {case}"


# ── el validador sin modelo ─────────────────────────────────────────────────


def test_the_validator_says_what_the_schema_cannot() -> None:
    doc = copy.deepcopy(FULL)
    doc["business"]["timezone"] = "Europe/Madird"
    doc["hours"]["days"]["tue"] = [
        {"open": "10:00", "close": "14:00"},
        {"open": "13:00", "close": "18:00"},
    ]
    doc["special_dates"].append({"from": "2026-08-10", "to": "2026-08-01", "closed": True})
    doc["services"].append({"name": "Té", "bookable": True, "duration_min": 7})
    doc["links"].append({"network": "instagram", "handle": "cultorbarber"})
    _spec, problems = validate_document(doc)
    found = {(p.pointer, p.code) for p in problems}
    assert ("/business/timezone", "invalid_timezone") in found
    assert ("/hours/days/tue", "shifts_overlap") in found
    assert ("/special_dates/2/to", "range_reversed") in found
    assert ("/services/2/duration_min", "duration_step") in found
    assert ("/links/2", "duplicate_link") in found


def test_one_value_is_checked_where_it_goes() -> None:
    assert validate_value("/business/name", "Cultor") == []
    assert validate_value("/business/timezone", "Mars/Olympus")[0].code == "invalid_timezone"
    assert validate_value("/business/sovereign", True)[0].code == "read_only"
    assert validate_value("/documents/x", {})[0].code in {"read_only", "invalid_pointer"}
    assert validate_value("/policies/cancellation", "x" * 1001)
    assert validate_value("/services/-", {"name": "Corte", "bookable": False}) == []
    assert validate_value("/services/-", {"name": "Corte", "bookable": True})
    assert validate_value("/locations/-", {"name": "Centro", "phone_e164": "600"})


def test_minutes_and_hours_go_both_ways() -> None:
    assert minutes_to_hhmm(1320) == "22:00"
    assert minutes_to_hhmm(1560, closing=True) == "02:00"
    assert minutes_to_hhmm(1440, closing=True) == "24:00"
    assert hhmm_to_minutes("22:00", "02:00") == (1320, 1560)
    assert hhmm_to_minutes("00:00", "24:00") == (0, 1440)
    assert hhmm_to_minutes("10:00", "10:00") == (600, 2040)


# ── importar: lo que cambia, y nada se borra ────────────────────────────────


def test_importing_proposes_changes_and_never_deletes() -> None:
    current = copy.deepcopy(FULL)
    current["services"][0]["id"] = "11111111-1111-4111-8111-111111111111"
    incoming = copy.deepcopy(current)
    incoming["business"]["niche"] = "Barbería clásica"
    incoming["services"][0]["price"] = {"kind": "amount", "amount_minor": 1800}
    incoming["services"].append({"name": "Afeitado", "bookable": True, "duration_min": 20})
    incoming["services"].pop(1)  # falta en el documento: no se archiva
    incoming["links"].append({"network": "tiktok", "handle": "cultor"})
    ops = diff_ops(current, incoming)
    paths = [(o["op"], o["path"]) for o in ops]
    assert ("replace", "/business/niche") in paths
    assert ("replace", "/services/11111111-1111-4111-8111-111111111111") in paths
    assert ("add", "/services/-") in paths
    assert ("add", "/links/-") in paths
    assert all(o["op"] != "archive" for o in ops)
    assert diff_ops(current, current) == []


def test_the_state_hash_ignores_provenance_and_documents() -> None:
    a = copy.deepcopy(FULL)
    b = copy.deepcopy(FULL)
    b["documents"] = [{"title": "carta.pdf", "status": "read"}]
    b["provenance"] = {"/business/name": {"source": "person", "at": "2026-10-27T10:00:00Z"}}
    assert state_hash(a) == state_hash(b)
    b["business"]["niche"] = "Otra cosa"
    assert state_hash(a) != state_hash(b)
