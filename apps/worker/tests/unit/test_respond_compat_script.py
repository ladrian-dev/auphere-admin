"""Spec 065, T055: ``scripts/respond_compat.py``, la batería real (research.md §D9.2).

Lo que se prueba sin llamar a ningún proveedor: los argumentos, que se niega a correr con
``--env prod`` antes de importar nada que pueda llamar (LiteLLM, el turno), qué escenarios
corre con cada modelo, que el turno va en modo estricto y las cuentas del informe.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "respond_compat.py"
SIX = (
    "openai/gpt-5.6-sol",
    "openai/gpt-5.6-terra",
    "openai/gpt-5.6-luna",
    "anthropic/claude-opus-5-5",
    "anthropic/claude-sonnet-5-5",
    "anthropic/claude-haiku-5-5",
)


@pytest.fixture(scope="module")
def compat() -> ModuleType:
    spec = importlib.util.spec_from_file_location("respond_compat", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["respond_compat"] = module  # ``dataclass`` busca su módulo aquí
    spec.loader.exec_module(module)
    return module


def test_it_refuses_prod_before_importing_anything_that_calls(tmp_path: Path) -> None:
    probe = (
        "import runpy, sys\n"
        f"sys.argv = ['respond_compat.py', '--env', 'prod', '--models', 'all']\n"
        "try:\n"
        f"    runpy.run_path({str(SCRIPT)!r}, run_name='__main__')\n"
        "except SystemExit as exit:\n"
        "    heavy = [m for m in ('litellm', 'nexus_worker.runtime.llm',\n"
        "             'nexus_worker.runtime.pipeline') if m in sys.modules]\n"
        "    print('EXIT', exit.code, 'HEAVY', heavy)\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, timeout=120
    )
    assert "EXIT 2 HEAVY []" in done.stdout, done.stdout + done.stderr[-2000:]
    assert "se niega a correr con --env prod" in done.stderr


def test_prod_is_refused_whatever_else_is_asked(compat: ModuleType) -> None:
    for argv in (["--env", "prod"], ["--env", "prod", "--models", "openai/gpt-5.6-sol"]):
        with pytest.raises(SystemExit) as exit:
            compat.parse_args(argv)
        assert exit.value.code == 2


@pytest.mark.parametrize("env", ["production", "", "PROD-eu"])
def test_an_unknown_environment_is_an_error(compat: ModuleType, env: str) -> None:
    with pytest.raises(SystemExit) as exit:
        compat.parse_args(["--env", env])
    assert exit.value.code == 2


def test_all_is_the_six_and_every_scenario(compat: ModuleType) -> None:
    args = compat.parse_args(["--env", "staging"])
    assert set(args.models) == set(SIX)
    assert set(args.scenarios) == {*compat.SCENARIOS, *compat.PROVIDER_FACTS}
    # Los que pide la tarea, por su nombre.
    assert set(compat.SCENARIOS) == {
        "no_tools",
        "three_tools",
        "image",
        "switch_between_turns",
        "fallback_mid_turn",
        "cross_after_tools",
        "booking_brake_retry",
        "long_turn_to_close",
    }
    assert set(compat.PROVIDER_FACTS) == {
        "openai_cache_write_reported",
        "prompt_tokens_include_writes",
        "cache_marker_is_not_an_edit",
    }


def test_a_subset_and_what_is_unknown(compat: ModuleType) -> None:
    args = compat.parse_args(
        ["--env", "local", "--models", "anthropic/claude-opus-5-5", "--scenarios", "no_tools"]
    )
    assert args.models == ("anthropic/claude-opus-5-5",)
    assert args.scenarios == ("no_tools",)
    for argv in (
        ["--env", "staging", "--models", "anthropic/claude-sonnet-4-6"],
        ["--env", "staging", "--scenarios", "teletransporte"],
    ):
        with pytest.raises(SystemExit):
            compat.parse_args(argv)


def test_each_scenario_runs_where_it_makes_sense(compat: ModuleType) -> None:
    pairs = compat.plan(SIX, (*compat.SCENARIOS, *compat.PROVIDER_FACTS))
    cross = {m for m, s in pairs if s == "cross_after_tools"}
    assert cross == {m for m in SIX if m.startswith("openai/")}
    assert {m for m, s in pairs if s == "openai_cache_write_reported"} == cross
    assert {m for m, s in pairs if s == "cache_marker_is_not_an_edit"} == set(SIX) - cross
    for scenario in ("fallback_mid_turn", "booking_brake_retry", "prompt_tokens_include_writes"):
        assert {m for m, s in pairs if s == scenario} == set(SIX), scenario


def test_the_turn_runs_in_strict_mode(compat: ModuleType) -> None:
    router = compat._router()
    assert router.prefix_mismatch_behavior == "error"
    from nexus_worker.runtime.llm import respond_hop_extra

    extra = respond_hop_extra(
        "anthropic/claude-opus-5-5",
        None,
        tools=True,
        prefix_mismatch=router.prefix_mismatch_behavior,
    )
    assert extra is not None
    assert extra["thinking"]["block_binding"] == {"prefix_mismatch_behavior": "error"}


def test_the_report_counts(compat: ModuleType) -> None:
    assert compat.p95([]) is None
    assert compat.p95([1.0]) == 1.0
    assert compat.p95([float(n) for n in range(1, 101)]) == 95.0
    assert compat.spend_factor({"openai/gpt-5.6-sol": 0.02, "x": 0.03}, "x") == 1.5
    assert compat.spend_factor({"x": 0.03}, "x") is None

    outcome = compat.Outcome
    summary = compat.report(
        [
            outcome(
                "openai/gpt-5.6-sol",
                "no_tools",
                True,
                calls=[{"model": "openai/gpt-5.6-sol", "elapsed_s": 1.2, "cost_usd": 0.01}],
            ),
            outcome(
                "anthropic/claude-opus-5-5",
                "no_tools",
                False,
                "turn_failure",
                calls=[{"model": "anthropic/claude-opus-5-5", "elapsed_s": 3.0, "cost_usd": 0.05}],
            ),
        ]
    )
    assert summary["green"] is False
    opus = summary["models"]["anthropic/claude-opus-5-5"]
    assert (opus["p95_s"], opus["spend_vs_sol"], opus["green"]) == (3.0, 5.0, False)
    assert "rojo: no_tools" in compat.markdown(summary)
    json.dumps(summary)  # el informe es JSON
