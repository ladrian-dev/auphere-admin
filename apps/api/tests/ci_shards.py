"""Reparte las pruebas de la API en tramos que la tubería corre en paralelo.

Cada tramo es un job de ``ci.yml`` con su propio Postgres, así que un tramo no
puede pisar las filas de otro. El reparto es por archivo —las pruebas de un
archivo corren juntas y en su orden— y usa como peso lo que tardó cada archivo
la última vez que se midió (``ci_durations.json``). Un archivo que no está
en la medida entra con la mediana: **la lista de archivos sale del disco, no de
la medida**, así que una prueba nueva no puede quedarse fuera de la tubería.
``tests/unit/test_ci_shards.py`` lo comprueba.

    python tests/ci_shards.py --total 6 --index 0      archivos del tramo 0
    python tests/ci_shards.py --total 6                cómo queda el reparto
    python tests/ci_shards.py --refresh junit/*.xml    vuelve a medir

Por qué existe: docs/tuberia-en-30-minutos.md.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

API = Path(__file__).resolve().parents[1]
TESTS = API / "tests"
DURATIONS = Path(__file__).with_name("ci_durations.json")

#: Los patrones por defecto de pytest; ``pyproject.toml`` no los cambia, y
#: ``tests/unit/test_ci_shards.py`` falla si alguien los cambia allí.
PATTERNS = ("test_*.py", "*_test.py")


def test_files() -> list[str]:
    """Todos los archivos de prueba bajo ``tests/``, relativos a ``apps/api``."""
    found: set[str] = set()
    for pattern in PATTERNS:
        for path in TESTS.rglob(pattern):
            relative = path.relative_to(API)
            if any(part.startswith((".", "__")) for part in relative.parts[:-1]):
                continue
            found.add(relative.as_posix())
    return sorted(found)


def load_durations() -> dict[str, float]:
    if not DURATIONS.exists():
        return {}
    data: dict[str, float] = json.loads(DURATIONS.read_text())
    return data


def split(files: list[str], durations: dict[str, float], total: int) -> list[list[str]]:
    """El más pesado primero, al tramo que menos lleva (LPT). Determinista."""
    if total < 1:
        raise ValueError("total debe ser al menos 1")
    known = [durations[f] for f in files if f in durations]
    default = statistics.median(known) if known else 1.0
    weighted = sorted(((durations.get(f, default), f) for f in files), key=lambda x: (-x[0], x[1]))
    loads = [0.0] * total
    shards: list[list[str]] = [[] for _ in range(total)]
    for weight, name in weighted:
        target = min(range(total), key=lambda i: (loads[i], i))
        loads[target] += weight
        shards[target].append(name)
    return [sorted(shard) for shard in shards]


def estimated_seconds(shard: list[str], durations: dict[str, float]) -> float:
    known = list(durations.values())
    default = statistics.median(known) if known else 1.0
    return sum(durations.get(f, default) for f in shard)


def _file_of(testcase: ET.Element) -> str | None:
    """``classname`` es ``tests.integration.test_x`` o ``tests.integration.test_x.TestClase``."""
    if testcase.get("file"):
        return testcase.get("file")
    parts = (testcase.get("classname") or "").split(".")
    while parts:
        candidate = "/".join(parts) + ".py"
        if (API / candidate).is_file():
            return candidate
        parts.pop()
    return None


def refresh(reports: list[Path]) -> dict[str, float]:
    """Suma el tiempo de cada prueba por archivo, a partir de los JUnit de los tramos
    (``gh run download <run> -p 'junit-api-*'``). Los archivos que ya no existen se
    van; los que no aparecen en los informes conservan su medida anterior."""
    measured: dict[str, float] = defaultdict(float)
    for report in reports:
        for testcase in ET.parse(report).getroot().iter("testcase"):
            name = _file_of(testcase)
            if name:
                measured[name] += float(testcase.get("time") or 0)
    current = set(test_files())
    merged = {f: s for f, s in load_durations().items() if f in current}
    merged.update({f: round(s, 1) for f, s in measured.items() if f in current})
    return dict(sorted(merged.items()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--total", type=int, help="número de tramos")
    parser.add_argument("--index", type=int, help="tramo a listar, desde 0")
    parser.add_argument("--refresh", nargs="+", type=Path, metavar="JUNIT")
    args = parser.parse_args(argv)

    if args.refresh:
        data = refresh(args.refresh)
        DURATIONS.write_text(json.dumps(data, indent=0, ensure_ascii=False) + "\n")
        print(f"{DURATIONS.name}: {len(data)} archivos, {sum(data.values()) / 60:.1f} min en serie")
        return 0
    if not args.total:
        parser.error("falta --total")

    durations = load_durations()
    shards = split(test_files(), durations, args.total)
    if args.index is not None:
        if not 0 <= args.index < args.total:
            parser.error(f"--index va de 0 a {args.total - 1}")
        print("\n".join(shards[args.index]))
        return 0
    for i, shard in enumerate(shards):
        minutes = estimated_seconds(shard, durations) / 60
        print(f"tramo {i}: {len(shard):4d} archivos, ~{minutes:5.1f} min")
    return 0


if __name__ == "__main__":
    sys.exit(main())
