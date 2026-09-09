"""Requisito 13.5 y 13.2 — el aislamiento del sustrato exige TRES rutas, no una.

La evaluación lo aprendió por las malas: ``KIROCREW_HOME`` no gobierna el workspace
del agente, que por defecto cae en ``~/workplace/``. Durante el spike el home real se
materializó dos veces, una de ellas con un simple ``--version``. Estos tests existen
para que eso no vuelva a pasar en producto.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from auphere_edition.runtime_env import (
    REQUIRED_PATH_KEYS,
    IncompleteIsolation,
    assert_isolated,
    substrate_env,
)


def test_the_three_path_keys_are_all_set(tmp_path: Path) -> None:
    env = substrate_env(tmp_path)
    for key in REQUIRED_PATH_KEYS:
        assert env.get(key), f"{key} sin valor: una sola variable no aísla"


def test_every_path_is_rooted_in_the_declared_base(tmp_path: Path) -> None:
    env = substrate_env(tmp_path)
    for key in REQUIRED_PATH_KEYS:
        assert Path(env[key]).is_relative_to(tmp_path)


def test_no_path_falls_in_the_real_home(tmp_path: Path) -> None:
    env = substrate_env(tmp_path)
    home = Path.home().resolve()
    for key in REQUIRED_PATH_KEYS:
        assert not Path(env[key]).resolve().is_relative_to(home)


def test_telemetry_is_off(tmp_path: Path) -> None:
    assert substrate_env(tmp_path)["KIROCREW_TELEMETRY_DISABLED"] == "1"


def test_assert_isolated_rejects_a_partial_environment(tmp_path: Path) -> None:
    """Fijar solo el data home es el error que la evaluación cometió."""
    env = substrate_env(tmp_path)
    del env["KIROCREW_WORKSPACE"]
    with pytest.raises(IncompleteIsolation) as excinfo:
        assert_isolated(env)
    assert "KIROCREW_WORKSPACE" in str(excinfo.value)


def test_assert_isolated_accepts_a_complete_environment(tmp_path: Path) -> None:
    assert_isolated(substrate_env(tmp_path)) is None
