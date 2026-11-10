"""Un catálogo de prueba para el router (spec 047, T136 y T137).

**Ninguna prueba llama a un proveedor real**: el catálogo es de pago. Esto arma
despliegues, certificaciones y perfiles de mentira, con dos reglas para que la
mentira no se aleje de la verdad:

- la taxonomía es **la de la migración 0180** (la que siembra los datos), y se
  compara con la tabla del contrato (``router-and-catalog.md`` §1);
- el perfil «Automático» es **el JSON del contrato** (§3), leído del documento.

Los despliegues sí son inventados (``eu-a/haiku``, ``eu-b/open``…): lo que se
prueba es la política, no qué modelo concreto gana hoy.
"""

from __future__ import annotations

import importlib.util
import json
import re
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from nexus_api.services.router_catalog import (
    CatalogSnapshot,
    ClassCertification,
    Deployment,
    Price,
    ProfilePolicy,
    Taxonomy,
    deployment_from_row,
)

ROOT = Path(__file__).resolve().parents[4]
CONTRACT = ROOT / "specs" / "047-la-fabrica-de-agentes" / "contracts" / "router-and-catalog.md"
MIGRATION = ROOT / "apps" / "api" / "alembic" / "versions" / "0180_model_catalog_and_router.py"

TENANT = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
NEIGHBOUR = uuid.UUID("00000000-0000-0000-0000-0000000000b2")
AGENT = uuid.UUID("00000000-0000-0000-0000-00000000a9e1")
SIBLING = uuid.UUID("00000000-0000-0000-0000-00000000a9e2")


def migration_taxonomy() -> list[dict[str, Any]]:
    spec = importlib.util.spec_from_file_location("_mig_0180", MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return [dict(t) for t in module.TAXONOMY_V1]


def taxonomy() -> Taxonomy:
    return Taxonomy.from_row(1, migration_taxonomy())


def contract_task_table() -> dict[str, bool]:
    """Código → «de conversación», de la tabla de §1 del contrato."""
    text = CONTRACT.read_text(encoding="utf-8")
    section = re.search(r"^## 1\..*?$(.*?)^## ", text, re.MULTILINE | re.DOTALL)
    assert section
    out: dict[str, bool] = {}
    for row in re.finditer(
        r"^\|\s*`([a-z_]+)`\s*\|([^|]*)\|([^|]*)\|([^|]*)\|", section.group(1), re.M
    ):
        out[row.group(1)] = "Sí" in row.group(4)
    return out


def contract_profile() -> dict[str, Any]:
    """El perfil de ejemplo de §3 (``auto``, versión 3)."""
    text = CONTRACT.read_text(encoding="utf-8")
    section = re.search(r"^## 3\..*?$(.*?)^## ", text, re.MULTILINE | re.DOTALL)
    assert section
    block = re.search(r"```json\n(.*?)```", section.group(1), re.DOTALL)
    assert block
    payload: dict[str, Any] = json.loads(block.group(1))
    return payload


def profile(name: str = "auto", **task_overrides: dict[str, Any]) -> ProfilePolicy:
    """El perfil del contrato con las tareas que una prueba necesita añadir.

    El contrato fija ``classify``, ``tool_turn``, ``answer`` y ``escalate``; las
    demás tareas las pone la prueba que las usa, a la vista."""
    policy = contract_profile()
    policy["profile"] = name
    tasks = dict(policy["tasks"])
    for task, over in task_overrides.items():
        tasks[task] = {**tasks.get(task, {"min_quality": 0.9}), **over}
    policy["tasks"] = tasks
    return ProfilePolicy.from_row(name, int(policy["version"]), policy)


_PRICE_DAY = date(2026, 10, 1)


def dep(
    key: str,
    *,
    provider: str,
    family: str = "anthropic-claude",
    residency: str = "eu",
    price_in: str = "1",
    price_out: str = "5",
    status: str = "active",
    zero_retention: bool = True,
    retention_how: str | None = "data_retention_mode:none",
    caps: dict[str, Any] | None = None,
    license_id: str | None = None,
    route: str | None = None,
) -> Deployment:
    capabilities = {
        "tools": True,
        "parallel_tools": True,
        "strict_structured_outputs": True,
        "structured_outputs": True,
        "vision": True,
        "cache_mode": "explicit",
        "reasoning_control": "effort",
        "context_window": 200_000,
        "tier": "basic",
    }
    capabilities.update(caps or {})
    row = {
        "id": uuid.uuid5(uuid.NAMESPACE_URL, key),
        "provider": provider,
        "model_id": key,
        "display_name": key,
        "route": route or key,
        "region": "eu-south-2" if residency == "eu" else None,
        "family": family,
        "residency": residency,
        "zero_retention": zero_retention,
        "retention_how": retention_how if zero_retention else None,
        "license_id": license_id,
        "license_url": "https://example.invalid/license" if license_id else None,
        "license_read_at": datetime(2026, 10, 1, tzinfo=UTC) if license_id else None,
        "contract_dpa": True,
        "subprocessor_listed": True,
        "status": status,
        "retire_after": None,
        "capabilities": capabilities,
        "quota": {},
        "supports_tools": bool(capabilities.get("tools")),
        "supports_vision": bool(capabilities.get("vision")),
        "max_context": capabilities.get("context_window"),
        "cache_min_tokens": 512,
        "quota_weight_input": Decimal("0.22"),
        "quota_weight_cache_read": Decimal("0.022"),
        "quota_weight_output": Decimal("1.1"),
    }
    price = Price(
        valid_from=_PRICE_DAY,
        input=Decimal(price_in),
        output=Decimal(price_out),
        cache_read=Decimal(price_in) / 10,
        source_url="https://example.invalid/prices",
    )
    return deployment_from_row(row, prices=[price])


def cert(
    deployment: Deployment,
    task: str,
    quality: float = 0.95,
    *,
    passed: bool = True,
    p95_ms: int | None = None,
    battery_version: int = 1,
) -> ClassCertification:
    scores: dict[str, Any] = {"pass3": quality}
    if p95_ms is not None:
        scores["latency_p95_ms"] = p95_ms
    return ClassCertification(
        deployment_key=deployment.key,
        task=task,
        battery_version=battery_version,
        quality=quality,
        passed=passed,
        scores=scores,
        certified_at=datetime(2026, 10, 20, tzinfo=UTC),
        invalidated_at=None,
    )


def snapshot(
    deployments: list[Deployment],
    certs: list[ClassCertification],
    *profiles: ProfilePolicy,
) -> CatalogSnapshot:
    return CatalogSnapshot(
        taxonomy=taxonomy(),
        deployments={d.key: d for d in deployments},
        class_certs=tuple(certs),
        profiles={p.profile: p for p in profiles},
        battery_version=1,
    )
