"""El catálogo de despliegues y su activación (spec 047, T135 · requisitos 41.1 y 41.2).

Una fila de ``model_profiles`` es un **despliegue** (ADR-036): un modelo en un
proveedor y una ruta. El contrato (``contracts/router-and-catalog.md`` §2) fija
su forma con un ejemplo en JSON; este test **lee ese ejemplo del contrato** —no
una copia— y comprueba que el tipo del catálogo lo entiende y lo devuelve con
las mismas claves, y que una fila de la base da lo mismo.

La activación es la puerta: un despliegue no entra en el router si le falta algo,
y el rechazo dice **qué** le falta, todo de una vez, para que el admin no lo
descubra a base de intentos.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from nexus_api.services.router_catalog import (
    ACTIVATION_MESSAGES,
    ActivationRejected,
    Capabilities,
    Deployment,
    Price,
    TokenEstimate,
    activation_problems,
    deployment_from_row,
    estimate_cost_micros,
    license_excluded,
    require_activatable,
)

CONTRACT = (
    Path(__file__).resolve().parents[4]
    / "specs"
    / "047-la-fabrica-de-agentes"
    / "contracts"
    / "router-and-catalog.md"
)


def contract_example() -> dict[str, Any]:
    """El primer bloque ``json`` de §2 del contrato, tal cual."""
    text = CONTRACT.read_text(encoding="utf-8")
    section = re.search(r"^## 2\..*?$(.*?)^## ", text, re.MULTILINE | re.DOTALL)
    assert section, "no encuentro §2 en router-and-catalog.md"
    block = re.search(r"```json\n(.*?)```", section.group(1), re.DOTALL)
    assert block, "§2 sin ejemplo en JSON"
    # El ejemplo abrevia la fuente con «…»: sigue siendo JSON válido.
    payload: dict[str, Any] = json.loads(block.group(1))
    return payload


def _keys(value: Any, prefix: str = "") -> set[str]:
    """Todas las rutas de claves de un JSON, para comparar formas y no valores."""
    out: set[str] = set()
    if isinstance(value, dict):
        for key, inner in value.items():
            path = f"{prefix}.{key}" if prefix else key
            out.add(path)
            out |= _keys(inner, path)
    elif isinstance(value, list):
        for inner in value:
            out |= _keys(inner, f"{prefix}[]")
    return out


# ── los campos ──────────────────────────────────────────────────────────────


def test_the_deployment_type_speaks_the_contract() -> None:
    example = contract_example()
    deployment = Deployment.from_contract(example)
    assert deployment.key == example["id"]
    assert deployment.family == "anthropic-claude"
    assert deployment.residency == "eu"
    assert deployment.zero_retention is True
    assert deployment.retention_how == "data_retention_mode:none"
    assert deployment.capabilities.tools and deployment.capabilities.strict_structured_outputs
    assert deployment.capabilities.cache_mode == "explicit"
    assert deployment.capabilities.tool_name_charset == "dotted_ok"
    assert deployment.capabilities.context_window == 200_000
    price = deployment.prices[0]
    assert price.valid_from == date(2026, 10, 26)
    assert price.input == Decimal("0.11") and price.output == Decimal("0.55")
    assert price.surcharge == {
        "above_tokens": 100000,
        "multiplier": 5,
        "applies_to": "whole_request",
    }

    back = deployment.to_contract()
    missing = sorted(_keys(example) - _keys(back))
    extra = sorted(_keys(back) - _keys(example))
    assert not missing, f"campos del contrato que el catálogo pierde: {missing}"
    assert not extra, f"campos que el catálogo inventa fuera del contrato: {extra}"


def _row(**over: Any) -> dict[str, Any]:
    """Una fila de ``model_profiles`` con todas las columnas de la 0180."""
    row: dict[str, Any] = {
        "id": uuid.uuid4(),
        "provider": "aws_bedrock",
        "model_id": "bedrock/eu.anthropic.claude-haiku-5-5",
        "display_name": "Claude Haiku 5.5 (UE)",
        "route": "eu.anthropic.claude-haiku-5-5",
        "region": "eu-south-2",
        "family": "anthropic-claude",
        "residency": "eu",
        "zero_retention": True,
        "retention_how": "data_retention_mode:none",
        "license_id": None,
        "license_url": None,
        "license_read_at": None,
        "contract_dpa": True,
        "subprocessor_listed": True,
        "status": "draft",
        "retire_after": None,
        "capabilities": {
            "tools": True,
            "strict_structured_outputs": True,
            "cache_mode": "explicit",
        },
        "quota": {"tpm": 400000, "rpm": None, "verified_at": None},
        "supports_tools": True,
        "supports_vision": True,
        "max_context": 200000,
        "cache_min_tokens": 512,
        "quota_weight_input": Decimal("0.0242"),
        "quota_weight_cache_read": Decimal("0.00242"),
        "quota_weight_output": Decimal("0.121"),
    }
    row.update(over)
    return row


def test_a_database_row_carries_every_field() -> None:
    price = Price(
        valid_from=date(2026, 10, 1),
        input=Decimal("0.11"),
        output=Decimal("0.55"),
        surcharge={"above_tokens": 100000, "multiplier": 5, "applies_to": "whole_request"},
    )
    deployment = deployment_from_row(_row(), prices=[price])
    shape = deployment.to_contract()
    assert _keys(shape) >= _keys(contract_example()) - {"license"}
    # El recargo es opcional: un precio sin él no lo inventa.
    plain = Price(valid_from=date(2026, 10, 1), input=Decimal("1"), output=Decimal("5"))
    assert "long_context_surcharge" not in plain.to_contract()
    assert shape["route"] == "eu.anthropic.claude-haiku-5-5"
    assert shape["region"] == "eu-south-2"
    assert shape["quota"]["tpm"] == 400000
    assert shape["meter_weights"] == {"w_in": 0.0242, "w_cache": 0.00242, "w_out": 0.121}
    assert deployment.weighted


def test_a_row_from_before_0180_derives_its_capabilities_from_the_old_columns() -> None:
    """Las filas de hoy tienen ``capabilities = {}``: lo que ya se sabía de ellas
    (herramientas, visión, contexto, mínimo de caché) no se pierde."""
    deployment = deployment_from_row(
        _row(capabilities={}, supports_tools=True, supports_vision=False, max_context=128000),
        prices=[],
    )
    assert deployment.capabilities.tools is True
    assert deployment.capabilities.vision is False
    assert deployment.capabilities.context_window == 128000
    assert deployment.capabilities.cache_min_tokens == 512


def test_prices_have_a_validity_and_the_current_one_wins() -> None:
    old = Price(valid_from=date(2026, 1, 1), input=Decimal("1"), output=Decimal("5"))
    new = Price(valid_from=date(2026, 11, 1), input=Decimal("2"), output=Decimal("10"))
    deployment = deployment_from_row(_row(), prices=[new, old])
    assert deployment.price_on(date(2026, 10, 27)) == old
    assert deployment.price_on(date(2026, 11, 1)) == new
    assert deployment.price_on(date(2025, 12, 31)) is None


def test_the_long_context_surcharge_applies_to_the_whole_request() -> None:
    """Haiku 5.5 cobra el request entero a 5 veces por encima de 100.000 tokens."""
    price = Price(
        valid_from=date(2026, 10, 26),
        input=Decimal("1"),
        output=Decimal("5"),
        surcharge={"above_tokens": 100000, "multiplier": 5, "applies_to": "whole_request"},
    )
    short = estimate_cost_micros(price, TokenEstimate(input_tokens=10_000, output_tokens=1_000))
    long_ = estimate_cost_micros(price, TokenEstimate(input_tokens=200_000, output_tokens=1_000))
    assert short == 10_000 + 5_000  # 1 $/M por 10k + 5 $/M por 1k, en micros
    assert long_ == 5 * (200_000 + 5_000)
    assert estimate_cost_micros(Price(valid_from=date(2026, 1, 1)), TokenEstimate(1, 1)) is None


def test_capabilities_have_safe_defaults() -> None:
    """Una capacidad que nadie declaró es una que no se tiene."""
    caps = Capabilities.from_json({})
    assert not caps.tools and not caps.vision and not caps.strict_structured_outputs
    assert caps.cache_mode == "none"
    assert caps.reasoning_control == "none"
    with pytest.raises(ValueError, match="cache_mode"):
        Capabilities.from_json({"cache_mode": "magic"})


# ── la activación ───────────────────────────────────────────────────────────


def _ready(**over: Any) -> Deployment:
    return deployment_from_row(_row(**over), prices=[])


def test_a_complete_deployment_activates() -> None:
    assert activation_problems(_ready(), class_certified_tasks={"tool_turn"}) == ()
    require_activatable(_ready(), class_certified_tasks={"tool_turn"})


@pytest.mark.parametrize(
    ("over", "certified", "code"),
    [
        ({"zero_retention": False}, {"tool_turn"}, "no_zero_retention"),
        ({"contract_dpa": False}, {"tool_turn"}, "no_zero_retention"),
        ({"subprocessor_listed": False}, {"tool_turn"}, "subprocessor_not_listed"),
        (
            {"license_id": "apache-2.0", "license_url": "https://x", "license_read_at": None},
            {"tool_turn"},
            "license_unread",
        ),
        (
            {
                "license_id": "llama-4-community",
                "license_url": "https://x",
                "license_read_at": datetime(2026, 10, 1, tzinfo=UTC),
            },
            {"tool_turn"},
            "license_excluded",
        ),
        (
            {
                "license_id": "qwen3.8-flash-next",
                "license_url": "https://x",
                "license_read_at": datetime(2026, 10, 1, tzinfo=UTC),
            },
            {"tool_turn"},
            "license_excluded",
        ),
        (
            {
                "license_id": "agpl-3.0",
                "license_url": "https://x",
                "license_read_at": datetime(2026, 10, 1, tzinfo=UTC),
            },
            {"tool_turn"},
            "license_excluded",
        ),
        ({"quota_weight_output": None}, {"tool_turn"}, "unweighted"),
        ({}, set(), "no_class_certification"),
    ],
)
def test_activation_is_refused_saying_what_is_missing(
    over: dict[str, Any], certified: set[str], code: str
) -> None:
    problems = activation_problems(_ready(**over), class_certified_tasks=certified)
    assert problems == (code,), problems
    with pytest.raises(ActivationRejected) as err:
        require_activatable(_ready(**over), class_certified_tasks=certified)
    assert err.value.missing == (code,)
    # El motivo se dice en palabras, no solo con un código.
    assert ACTIVATION_MESSAGES[code] in str(err.value)


def test_every_missing_piece_is_reported_at_once() -> None:
    broken = _ready(
        zero_retention=False,
        subprocessor_listed=False,
        quota_weight_input=None,
        quota_weight_cache_read=None,
        quota_weight_output=None,
    )
    assert set(activation_problems(broken, class_certified_tasks=set())) == {
        "no_zero_retention",
        "subprocessor_not_listed",
        "unweighted",
        "no_class_certification",
    }


def test_every_problem_has_its_words() -> None:
    assert set(ACTIVATION_MESSAGES) == {
        "no_zero_retention",
        "subprocessor_not_listed",
        "license_unread",
        "license_excluded",
        "unweighted",
        "no_class_certification",
    }
    assert all(m.strip() for m in ACTIVATION_MESSAGES.values())


@pytest.mark.parametrize(
    ("license_id", "excluded"),
    [
        ("llama-4-community", True),
        ("Llama-4-Maverick", True),
        ("qwen3.8-flash-next", True),
        ("agpl-3.0", True),
        ("AGPL-3.0-or-later", True),
        ("apache-2.0", False),
        ("mit", False),
        ("llama-3.3", False),
        (None, False),
    ],
)
def test_the_excluded_licenses(license_id: str | None, excluded: bool) -> None:
    assert license_excluded(license_id) is excluded
