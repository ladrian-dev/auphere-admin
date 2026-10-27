"""Lo que mide la certificación por clase y su nota (spec 047, requisito 42.1).

Cada caso de la batería se repite tres veces. Las métricas:

- ``pass3``: la fracción de casos que aciertan **en las tres** repeticiones;
- ``reasks``: repreguntas por caso;
- ``unsupported_claims``: afirmaciones sin fuente por caso;
- ``tool_args_valid``: fracción de repeticiones con los argumentos de herramienta
  válidos al primer intento (de las que llamaron a alguna);
- ``language_drift``: fracción de repeticiones que contestaron en otro idioma sin
  que nadie lo pidiera;
- ``latency_p50_ms`` / ``latency_p95_ms``, sin razonamiento, y las mismas con el
  sufijo ``_reasoning``, con él.

La nota (de 0 a 1) es una combinación ponderada con los pesos que el admin publica con
la versión de la batería; pass^3 manda.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class CaseRun:
    """Una repetición de un caso, tal como la juzgó el juez."""

    passed: bool
    reasks: int = 0
    unsupported_claims: int = 0
    #: None si la repetición no llamó a ninguna herramienta.
    tool_args_valid: bool | None = None
    language_drift: bool = False
    latency_ms: int = 0
    reasoning: bool = False


def _percentile(values: Sequence[int], p: float) -> float | None:
    """Rango más cercano: el valor que deja debajo el ``p`` de las muestras."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(p * len(ordered)))
    return float(ordered[rank - 1])


def class_metrics(runs: Mapping[str, Sequence[CaseRun]]) -> dict[str, float | None]:
    cases = [list(r) for r in runs.values() if r]
    if not cases:
        raise ValueError("una certificación sin repeticiones no mide nada")
    every = [r for case in cases for r in case]
    with_tools = [r.tool_args_valid for r in every if r.tool_args_valid is not None]
    plain = [r.latency_ms for r in every if not r.reasoning]
    thinking = [r.latency_ms for r in every if r.reasoning]
    return {
        "pass3": sum(all(r.passed for r in case) for case in cases) / len(cases),
        "reasks": sum(sum(r.reasks for r in case) for case in cases) / len(cases),
        "unsupported_claims": sum(sum(r.unsupported_claims for r in case) for case in cases)
        / len(cases),
        "tool_args_valid": (sum(with_tools) / len(with_tools)) if with_tools else None,
        "language_drift": sum(r.language_drift for r in every) / len(every),
        "latency_p50_ms": _percentile(plain, 0.5),
        "latency_p95_ms": _percentile(plain, 0.95),
        "latency_p50_ms_reasoning": _percentile(thinking, 0.5),
        "latency_p95_ms_reasoning": _percentile(thinking, 0.95),
    }


def _goodness(metric: str, value: float | None) -> float | None:
    """Cada métrica, como «cuánto de bien» entre 0 y 1."""
    if value is None:
        return 1.0 if metric == "tool_args_valid" else None
    if metric in ("pass3", "tool_args_valid"):
        return value
    if metric in ("reasks", "unsupported_claims"):
        return 1.0 / (1.0 + value)
    if metric == "language_drift":
        return 1.0 - value
    return None


def quality(metrics: Mapping[str, float | None], weights: Mapping[str, float]) -> float:
    """La nota de la tarea: media ponderada de lo que se midió."""
    total = 0.0
    weight = 0.0
    for metric, w in weights.items():
        good = _goodness(metric, metrics.get(metric))
        if good is None or w <= 0:
            continue
        total += w * good
        weight += w
    return total / weight if weight else 0.0


__all__ = ["CaseRun", "class_metrics", "quality"]
