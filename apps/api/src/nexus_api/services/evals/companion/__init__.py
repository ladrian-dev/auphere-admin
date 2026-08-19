"""Evals del Companion de la consola (CO-07).

El quinto mecanismo anti-alucinación del §9 de la investigación: *"un
dataset de ~60 casos —consultas con respuesta conocida, peticiones ambiguas
que deben provocar pregunta, intentos de cruce de partner que deben fallar,
peticiones destructivas que deben rechazarse— corriendo en CI. Es lo que
impide que una mejora del prompt rompa una garantía en silencio."*

Dos modos, y la diferencia importa (D1 de ``docs/companion/PLAN-CO-07.md``):

- **offline**, el de CI: el modelo es un guion y todo lo demás es real.
  Prueba el motor y las garantías de plataforma.
- **live**, opcional: el modelo real. Prueba al modelo, y por eso no puede
  ser una barrera de CI.

El juez LLM vive aquí dentro y **solo** aquí: la verificación del camino del
usuario es código determinista (corrección C5 de la Parte II).
"""

from __future__ import annotations

from nexus_api.services.evals.companion.assertions import (
    capability_is_unreachable,
    check_case,
    r1_verdict,
    resolved_without_asking,
)
from nexus_api.services.evals.companion.dataset import (
    FAMILIES,
    CompanionCase,
    DatasetError,
    Expect,
    Step,
    load_dataset,
    load_family,
)
from nexus_api.services.evals.companion.driver import (
    ScriptedModel,
    TurnResult,
    candidates_for,
    run_case,
)
from nexus_api.services.evals.companion.report import (
    R1_FALSE_POSITIVE_THRESHOLD,
    R1_RECALL_THRESHOLD,
    R1Metric,
    family_counts,
    measure_r1,
    render,
)

__all__ = [
    "FAMILIES",
    "R1_FALSE_POSITIVE_THRESHOLD",
    "R1_RECALL_THRESHOLD",
    "CompanionCase",
    "DatasetError",
    "Expect",
    "R1Metric",
    "ScriptedModel",
    "Step",
    "TurnResult",
    "candidates_for",
    "capability_is_unreachable",
    "check_case",
    "family_counts",
    "load_dataset",
    "load_family",
    "measure_r1",
    "r1_verdict",
    "render",
    "resolved_without_asking",
    "run_case",
]
