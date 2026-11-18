"""Los tramos de la tubería cubren todas las pruebas de la API, sin repetir ninguna.

La tubería no corre ``pytest`` sobre ``tests/``: corre cada tramo sobre la lista
de archivos que le da ``tests/ci_shards.py``. Si esa lista se deja un
archivo, sus pruebas dejan de correr en la tubería **sin ningún rojo**. Esta es
la prueba que lo impide (docs/tuberia-en-30-minutos.md).
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tomllib
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

_API = Path(__file__).resolve().parents[2]
_SCRIPT = _API / "tests" / "ci_shards.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ci_shards_script", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


shards = _load()


def _what_pytest_collects() -> set[str]:
    """Los archivos que ``pytest`` recogería de ``tests/`` con su configuración."""
    found: set[str] = set()
    for path in (_API / "tests").rglob("*.py"):
        relative = path.relative_to(_API)
        if any(part.startswith((".", "__")) for part in relative.parts[:-1]):
            continue
        if path.name.startswith("test_") or path.name.endswith("_test.py"):
            found.add(relative.as_posix())
    return found


def test_the_script_sees_every_test_file() -> None:
    assert set(shards.test_files()) == _what_pytest_collects()
    assert "tests/unit/test_ci_shards.py" in shards.test_files()


def test_pytest_keeps_the_patterns_the_script_assumes() -> None:
    """Si ``pyproject.toml`` cambia dónde o cómo busca pytest, el script tiene que
    cambiar con él; si no, los tramos dejarían fuera lo que pytest sí ve."""
    options = tomllib.loads((_API / "pyproject.toml").read_text())["tool"]["pytest"]["ini_options"]
    assert options.get("testpaths") == ["tests"]
    assert "python_files" not in options
    assert shards.PATTERNS == ("test_*.py", "*_test.py")


@pytest.mark.parametrize("total", range(1, 11))
def test_every_file_lands_in_exactly_one_shard(total: int) -> None:
    files = shards.test_files()
    split = shards.split(files, shards.load_durations(), total)
    assert len(split) == total
    flat = [name for shard in split for name in shard]
    assert sorted(flat) == files
    assert len(flat) == len(set(flat))


def test_a_file_without_a_measure_still_runs() -> None:
    split = shards.split(["tests/a.py", "tests/new.py"], {"tests/a.py": 10.0}, 2)
    assert sorted(name for shard in split for name in shard) == ["tests/a.py", "tests/new.py"]


def test_the_split_is_deterministic_and_balanced() -> None:
    durations = {f"tests/t{i}.py": float(i) for i in range(1, 21)}
    files = sorted(durations)
    first = shards.split(files, durations, 4)
    assert first == shards.split(list(reversed(files)), durations, 4)
    loads = [sum(durations[f] for f in shard) for shard in first]
    assert max(loads) - min(loads) <= max(durations.values())


def test_the_measure_is_valid_json_of_seconds() -> None:
    """Una medida vieja no deja fuera ningún archivo —la lista sale del disco—; solo
    desequilibra el reparto, y ``--refresh`` la pone al día."""
    data = json.loads(shards.DURATIONS.read_text())
    assert data and all(isinstance(s, int | float) and s >= 0 for s in data.values())
