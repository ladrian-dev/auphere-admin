"""Aislamiento del sustrato: las tres rutas, fijadas antes del primer arranque.

Requisitos 13.2 y 13.5.

**Por qué tres y no una.** ``KIROCREW_HOME`` gobierna el data home, pero **no** el
workspace del agente: eso es ``KIROCREW_WORKSPACE``, que por defecto cae en
``~/workplace/kirocrew-workspace/<canal>/``, fuera del data home. Y ``KIRO_HOME``
gobierna el home compartido de la familia, bajo el que el data home anida. Fijar una
sola deja las otras dos apuntando al home real del partner.

**Antes del primer arranque, no después.** Un simple ``--version`` ya materializa el
data home. Por eso ``apply`` se llama antes de lanzar nada, y ``assert_isolated``
existe para que el lanzador no pueda arrancar con un entorno a medias.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Las tres rutas. Fijar un subconjunto no aísla: es el error que hay que impedir.
REQUIRED_PATH_KEYS: tuple[str, ...] = (
    "KIROCREW_HOME",
    "KIRO_HOME",
    "KIROCREW_WORKSPACE",
)

TELEMETRY_KEY = "KIROCREW_TELEMETRY_DISABLED"


class IncompleteIsolation(RuntimeError):
    """El entorno no fija las tres rutas. Arrancar así toca el home del partner."""


def substrate_env(base: Path) -> dict[str, str]:
    """Entorno completo del sustrato, enteramente bajo *base*.

    *base* es la ubicación que declara el empaquetado — nunca el home del partner.
    """
    root = Path(base)
    return {
        "KIROCREW_HOME": str(root / "substrate" / "home"),
        "KIRO_HOME": str(root / "substrate" / "kiro"),
        "KIROCREW_WORKSPACE": str(root / "substrate" / "workspace"),
        TELEMETRY_KEY: "1",
    }


def assert_isolated(env: dict[str, str]) -> None:
    """Falla si falta cualquiera de las tres rutas o si la telemetría no está apagada.

    Se llama en el lanzador antes de arrancar el sustrato. Falla cerrado: no arrancar
    es preferible a arrancar escribiendo en el home de otra persona.
    """
    missing = [k for k in REQUIRED_PATH_KEYS if not env.get(k)]
    if missing:
        raise IncompleteIsolation(
            "aislamiento incompleto del sustrato; faltan: "
            + ", ".join(missing)
            + ". Fijar solo el data home NO aísla el workspace del agente."
        )
    if env.get(TELEMETRY_KEY) != "1":
        raise IncompleteIsolation(f"{TELEMETRY_KEY} debe valer '1' antes del primer arranque")


def apply(base: Path, environ: dict[str, str] | None = None) -> dict[str, str]:
    """Fija el entorno del sustrato **antes** de lanzarlo, y lo devuelve.

    Crea los directorios: que existan de antemano evita que el sustrato los resuelva
    contra su propio defecto si alguno falta.
    """
    target = environ if environ is not None else os.environ
    env = substrate_env(base)
    assert_isolated(env)
    for key in REQUIRED_PATH_KEYS:
        Path(env[key]).mkdir(parents=True, exist_ok=True)
    target.update(env)
    return env
