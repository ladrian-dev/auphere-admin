"""¿Puede «Automático» atender a un agente nuevo? (spec 047, T145 · 39.2, D44).

Un agente nuevo no tiene certificaciones propias, así que en las tareas de
conversación solo le atiende la **reserva** del perfil; en ``classify``, la
reserva o un despliegue certificado por clase. Cada una, con el filtro duro del
cliente («Solo UE», restricción soberana).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from nexus_api.services.router_catalog import (
    CatalogSnapshot,
    ClassCertification,
    Deployment,
    Price,
    ProfilePolicy,
    Taxonomy,
    auto_servable,
    default_model_policy_for,
    deployment_from_row,
)

TASKS = [
    {"code": "classify", "conversation": False, "needs": ["strict_structured_outputs"]},
    {"code": "answer", "conversation": True, "needs": ["context_window"]},
    {"code": "tool_turn", "conversation": True, "needs": ["tools"]},
]


def _dep(
    key: str, *, residency: str = "eu", zero: bool = True, status: str = "active"
) -> Deployment:
    return deployment_from_row(
        {
            "id": uuid.uuid5(uuid.NAMESPACE_URL, key),
            "provider": key.split("/", 1)[0],
            "model_id": key,
            "residency": residency,
            "zero_retention": zero,
            "retention_how": "store=false" if zero else None,
            "contract_dpa": True,
            "subprocessor_listed": True,
            "status": status,
            "capabilities": {"tools": True, "strict_structured_outputs": True},
        },
        prices=[Price(valid_from=date(2026, 10, 1), input=Decimal("1"), output=Decimal("2"))],
    )


def _world(
    deployments: list[Deployment],
    *,
    reserves: dict[str, str | None],
    certified_classify: list[str] = (),  # type: ignore[assignment]
) -> CatalogSnapshot:
    policy: dict[str, Any] = {
        "tasks": {
            task: {"min_quality": 0.9, "reserve": reserve} for task, reserve in reserves.items()
        }
    }
    certs = tuple(
        ClassCertification(
            deployment_key=key,
            task="classify",
            battery_version=1,
            quality=0.95,
            passed=True,
            scores={},
            certified_at=datetime(2026, 10, 20, tzinfo=UTC),
            invalidated_at=None,
        )
        for key in certified_classify
    )
    return CatalogSnapshot(
        taxonomy=Taxonomy.from_row(1, TASKS),
        deployments={d.key: d for d in deployments},
        class_certs=certs,
        profiles={"auto": ProfilePolicy.from_row("auto", 1, policy)},
        battery_version=1,
    )


EU = _dep("eu/reserve")
GLOBAL = _dep("global/reserve", residency="global")
LEAKY = _dep("eu/leaky", zero=False)
ALL_EU = {"classify": EU.key, "answer": EU.key, "tool_turn": EU.key}


def test_auto_serves_a_new_agent_when_every_reserve_passes_the_filter() -> None:
    world = _world([EU], reserves=ALL_EU)
    assert auto_servable(world)
    assert default_model_policy_for(world) == {"kind": "profile", "profile": "auto"}


def test_todays_catalog_serves_nobody() -> None:
    """D44: sin retención cero comprobada, ni la reserva pasa."""
    world = _world([LEAKY], reserves={t: LEAKY.key for t in ALL_EU})
    assert not auto_servable(world)
    assert default_model_policy_for(world) is None


def test_a_conversation_task_needs_its_reserve_a_new_agent_has_no_certificate() -> None:
    world = _world([EU], reserves={**ALL_EU, "answer": None}, certified_classify=[EU.key])
    assert not auto_servable(world)


def test_classify_is_served_by_a_certified_deployment_without_reserve() -> None:
    world = _world([EU], reserves={**ALL_EU, "classify": None}, certified_classify=[EU.key])
    assert auto_servable(world)


def test_the_clients_residency_counts() -> None:
    world = _world([GLOBAL], reserves={t: GLOBAL.key for t in ALL_EU})
    assert auto_servable(world)
    assert not auto_servable(world, eu_only=True)
    assert default_model_policy_for(world, eu_only=True) is None


def test_without_the_auto_profile_nobody_is_born_in_auto() -> None:
    world = _world([EU], reserves=ALL_EU)
    empty = CatalogSnapshot(
        taxonomy=world.taxonomy,
        deployments=world.deployments,
        class_certs=(),
        profiles={},
        battery_version=None,
    )
    assert not auto_servable(empty)
