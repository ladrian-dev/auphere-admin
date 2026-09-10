"""Garantía 2 — el catálogo por teammate es lo que el modelo ve (spec 003, R4).

La lista blanca del Companion (``ALL_TOOLS``) es exhaustiva; el catálogo de un
teammate es un **subconjunto** de ella, se comprueba en lo que recibe el
``CompanionToolbelt`` —no en la pantalla— y cambia en el siguiente turno cuando
cambian el oficio o los permisos.

En rojo bloquea el merge.
"""

from __future__ import annotations

import uuid

import pytest

from nexus_api.companion.tools import CompanionToolbelt
from nexus_api.companion.tools.catalog import ALL_TOOLS, READ_TOOLS
from nexus_api.core.console_auth import InProcessActor
from nexus_api.db.models import Teammate
from nexus_api.services.teammate_catalog import (
    ToolNotInCatalog,
    for_teammate,
    permissions_to_tool_names,
    validate_tool_names,
)

pytestmark = [pytest.mark.isolation]

ALL_NAMES = {t.name for t in ALL_TOOLS}
READ_NAMES = {t.name for t in READ_TOOLS}


def _teammate(**overrides) -> Teammate:
    perms = {"read": True, "write": False, "spend": False, "publish": False, "contact": False}
    perms.update(overrides.pop("permissions", {}))
    return Teammate(
        id=uuid.uuid4(),
        partner_id=uuid.uuid4(),
        name="Vera",
        job="Finanzas",
        model="auphere-haiku",
        tool_names=permissions_to_tool_names(perms),
        permissions=perms,
        local_exec=False,
        created_by="seed",
        **overrides,
    )


def _belt(names: list[str], mode: str = "build") -> CompanionToolbelt:
    return CompanionToolbelt(
        actor=InProcessActor(user_id="u", partner_id=uuid.uuid4(), jti="t"),
        mode=mode,
        allowed_tools=frozenset(names),
    )


def _model_sees(belt: CompanionToolbelt) -> set[str]:
    return {spec["function"]["name"] for spec in belt.specs()}


def test_a_read_only_teammate_receives_only_reads_and_never_the_machine():
    vera = _teammate()
    names = for_teammate(vera, mode="build", machine_present=True)
    assert set(names) <= READ_NAMES
    assert "shell_local" not in names
    seen = _model_sees(_belt(names))
    assert seen == set(names)
    assert not (seen - ALL_NAMES)


def test_write_permission_adds_proposals_and_still_stays_inside_the_catalog():
    nilo = _teammate(permissions={"write": True})
    names = for_teammate(nilo, mode="build", machine_present=False)
    assert set(names) > READ_NAMES or set(names) - READ_NAMES
    assert set(names) <= ALL_NAMES
    assert "shell_local" not in names  # sin local_exec, nunca


def test_consult_mode_still_wins_over_the_teammate():
    nilo = _teammate(permissions={"write": True})
    names = for_teammate(nilo, mode="consult", machine_present=True)
    assert set(names) <= READ_NAMES
    assert _model_sees(_belt(names, mode="consult")) <= READ_NAMES


def test_a_name_outside_the_catalog_is_refused_not_ignored():
    with pytest.raises(ToolNotInCatalog):
        validate_tool_names(["console.whoami", "github.merge"])


def test_changing_the_job_changes_what_the_next_turn_sees():
    vera = _teammate()
    before = set(for_teammate(vera, mode="build", machine_present=False))
    vera.permissions = {**vera.permissions, "write": True}
    vera.tool_names = permissions_to_tool_names(vera.permissions)
    after = set(for_teammate(vera, mode="build", machine_present=False))
    assert after > before


def test_the_toolbelt_never_publishes_what_the_teammate_was_not_given():
    belt = _belt(["console.whoami"])
    assert _model_sees(belt) == {"console.whoami"}
