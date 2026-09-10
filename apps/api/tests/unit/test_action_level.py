"""Requisito 7.1 — cada aprobación nace con su nivel de aviso.

Tres niveles y una regla: lo que toca la máquina o es de riesgo alto interrumpe
(`critico`); lo que cambia algo marca la bandeja (`aviso`); el resto no
interrumpe. El nivel se fija al proponer, no al pintar: la pantalla no puede
inventarse la urgencia de algo que no vio hacer.
"""

from __future__ import annotations

import pytest

from nexus_api.core.action_level import ACTION_LEVELS, level_for


@pytest.mark.parametrize("kind", ["local_exec"])
def test_touching_the_machine_is_always_critical(kind: str):
    assert level_for(kind=kind, risk="low") == "critico"


def test_high_risk_is_critical_whatever_it_touches():
    assert level_for(kind="prompt", risk="high") == "critico"
    assert level_for(kind="publish", risk="high") == "critico"


def test_a_change_marks_the_tray():
    assert level_for(kind="prompt", risk="low") == "aviso"
    assert level_for(kind="client", risk="medium") == "aviso"


def test_what_changes_nothing_does_not_interrupt():
    assert level_for(kind="support_ticket", risk="low") == "informativo"
    assert level_for(kind="", risk=None) == "informativo"


def test_the_three_levels_are_the_ones_the_contract_names():
    assert ACTION_LEVELS == ("critico", "aviso", "informativo")
    assert all(
        level_for(kind=k, risk=r) in ACTION_LEVELS
        for k in ("prompt", "local_exec", "x")
        for r in ("low", "high", None)
    )
