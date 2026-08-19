"""El gate de los evals del Companion (CO-07).

Dos piezas cumplen dos funciones distintas y por eso son dos:

- ``pytest -m evals`` **es la barrera**. Rompe el build. Corre con el resto
  de la suite en CI, así que un caso rojo para el PR aunque nadie ejecute
  este script.
- este script **es el informe**. Corre la misma barrera y además deja el
  reparto del dataset y los dos números de R1 en las primeras líneas de la
  salida, para que cuando CI se ponga rojo no haya que abrir el log entero
  buscando la cifra.

No reimplementa la medición: la de verdad necesita el mundo sembrado y las
lecturas reales contra la base, y eso vive en los fixtures. Duplicarlo aquí
sería tener dos medidores que se pueden desincronizar — y el que mintiera
sería este, que es el que se lee.

Uso::

    uv run python scripts/companion_evals.py            # barrera + informe
    uv run python scripts/companion_evals.py --live     # además, modo live
    uv run python scripts/companion_evals.py --report   # solo el reparto, sin base

Código de salida: el de ``pytest``. 0 = dentro de umbral.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parent.parent


def _static_summary() -> str:
    """El reparto del dataset. No necesita base de datos ni modelo: es lo
    que se puede decir del conjunto sin correrlo."""
    sys.path.insert(0, str(API_ROOT / "src"))
    from nexus_api.services.evals.companion.dataset import load_dataset
    from nexus_api.services.evals.companion.report import family_counts, pending_counts

    cases = load_dataset()
    lines = [
        "Companion · dataset CO-07",
        "=" * 40,
        f"casos totales: {len(cases)}",
    ]
    lines += [f"  {family:<16} {count}" for family, count in family_counts(cases).items()]
    pending = pending_counts(cases)
    if pending:
        lines.append("pendientes (xfail):")
        lines += [f"  {what:<16} {count}" for what, count in sorted(pending.items())]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    live = "--live" in argv
    print(_static_summary(), flush=True)
    if "--report" in argv:
        return 0

    env = dict(os.environ)
    if live:
        env["NEXUS_COMPANION_EVAL_LIVE"] = "1"
        print("\nmodo LIVE: se llama al modelo real. Esto cuesta dinero.\n", flush=True)

    # ``-s`` para que el informe de R1 salga por la salida estándar: lo
    # imprime ``test_the_gate_reports_no_breach``, que es donde se mide.
    return subprocess.call(
        [sys.executable, "-m", "pytest", "-m", "evals", "-q", "-s", "--tb=short"],
        cwd=API_ROOT,
        env=env,
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
