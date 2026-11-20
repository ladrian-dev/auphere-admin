"""Spec 065, T001 (requisito 4.12; research.md §D13): LiteLLM se comporta igual en todas partes.

Lo que se prueba en CI tiene que ser lo que corre en AWS:

- la misma versión de LiteLLM en el lock de la API y en el del worker (el build de prod del
  2026-11-18 llevó 1.83.0 a la API y 1.83.14 al worker);
- el mapa de modelos local, fijado antes de que nada importe LiteLLM, en vez del que se
  descarga de GitHub al arrancar;
- encima, las entradas de los modelos del catálogo que ese mapa local no conoce: sin ellas
  LiteLLM rechaza el ``tool_choice`` de GPT-5.6 y el razonamiento de Haiku 5.5;
- y una sola puerta: nadie importa ``litellm`` por su cuenta.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
API_SRC = ROOT / "apps/api/src"
WORKER_SRC = ROOT / "apps/worker/src"

#: Ficheros que pueden importar ``litellm`` directamente, con su motivo.
ALLOWED_IMPORTERS: dict[str, str] = {
    "nexus_api/core/litellm_map.py": "la puerta",
    "nexus_api/core/litellm_smoke.py": (
        "la prueba de humo del build (python -m): fija el mapa local ella misma y no corre "
        "en ningún servicio"
    ),
}

#: Los modelos que ofrece la spec 065 aunque una migración todavía no los haya sembrado.
OFFER_065 = (
    "openai/gpt-5.6-sol",
    "openai/gpt-5.6-terra",
    "openai/gpt-5.6-luna",
    "anthropic/claude-opus-5-5",
    "anthropic/claude-sonnet-5-5",
    "anthropic/claude-haiku-5-5",
)


def _locked_version(lock: Path, package: str) -> str:
    data = tomllib.loads(lock.read_text(encoding="utf-8"))
    for entry in data["package"]:
        if entry["name"] == package:
            return str(entry["version"])
    raise AssertionError(f"{package} no está en {lock}")


def test_the_api_and_the_worker_lock_the_same_litellm() -> None:
    api = _locked_version(ROOT / "apps/api/uv.lock", "litellm")
    worker = _locked_version(ROOT / "apps/worker/uv.lock", "litellm")
    assert api == worker, f"LiteLLM {api} en la API y {worker} en el worker"


def test_the_pinned_entries_were_copied_for_the_locked_version() -> None:
    data = json.loads((API_SRC / "nexus_api/core/litellm_models.json").read_text())
    worker = _locked_version(ROOT / "apps/worker/uv.lock", "litellm")
    assert data["litellm_version"] == worker, (
        "al subir LiteLLM hay que revisar las entradas fijadas y su prueba en el cable"
    )


PROBE = r"""
import json, os
import nexus_worker  # noqa: F401 — lo primero que carga un proceso del worker
pinned_on_import = os.environ.get("LITELLM_LOCAL_MODEL_COST_MAP")
import nexus_worker.runtime.llm  # noqa: F401 — el transporte
from importlib import resources
from nexus_api.core.litellm_map import litellm_module, pinned_entries
from nexus_api.core.respond_catalog import BOOT_HOP_MODEL_IDS
from nexus_worker.platform_models import default_models

litellm = litellm_module()
bundled = json.loads(resources.files("litellm").joinpath(
    "model_prices_and_context_window_backup.json").read_text())
wanted = set(default_models().values()) | set(BOOT_HOP_MODEL_IDS) | set(json.loads(os.environ["PROBE_OFFER"]))
unknown = []
for model in sorted(wanted):
    short = model.split("/", 1)[1] if "/" in model else model
    if model not in bundled and short not in bundled and short not in pinned_entries():
        unknown.append(model)
print("RESULT" + json.dumps({
    "pinned_on_import": pinned_on_import,
    "pinned_now": os.environ.get("LITELLM_LOCAL_MODEL_COST_MAP"),
    "registered": sorted(k for k in pinned_entries() if k in litellm.model_cost),
    "unknown": unknown,
}))
"""


def _probe() -> dict[str, object]:
    env = {k: v for k, v in os.environ.items() if k != "LITELLM_LOCAL_MODEL_COST_MAP"}
    env["PROBE_OFFER"] = json.dumps(OFFER_065)
    done = subprocess.run(
        [sys.executable, "-c", PROBE], capture_output=True, text=True, env=env, timeout=120
    )
    assert done.returncode == 0, done.stderr[-2000:]
    line = next(x for x in done.stdout.splitlines() if x.startswith("RESULT"))
    out: dict[str, object] = json.loads(line[len("RESULT") :])
    return out


def test_importing_the_worker_pins_the_local_map_and_registers_our_entries() -> None:
    out = _probe()
    assert out["pinned_on_import"] == "True", "el mapa se fija antes de cualquier import de LiteLLM"
    assert out["pinned_now"] == "True"
    assert out["registered"] == sorted(
        json.loads((API_SRC / "nexus_api/core/litellm_models.json").read_text())["models"]
    )


def test_every_model_the_platform_can_call_is_known_to_the_pinned_map() -> None:
    out = _probe()
    assert out["unknown"] == [], (
        f"modelos que el mapa fijado no conoce: {out['unknown']}. Añadir su entrada a "
        "nexus_api/core/litellm_models.json, copiada del mapa publicado."
    )


def _imports_litellm(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            alias.name == "litellm" or alias.name.startswith("litellm.") for alias in node.names
        ):
            return True
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "litellm":
            return True
    return False


def test_nobody_imports_litellm_but_the_gate() -> None:
    offenders = []
    for src in (API_SRC, WORKER_SRC):
        for path in sorted(src.rglob("*.py")):
            relative = path.relative_to(src).as_posix()
            if relative in ALLOWED_IMPORTERS:
                continue
            if _imports_litellm(ast.parse(path.read_text(encoding="utf-8"))):
                offenders.append(relative)
    assert offenders == [], (
        f"importan litellm sin pasar por nexus_api.core.litellm_map: {offenders}"
    )
