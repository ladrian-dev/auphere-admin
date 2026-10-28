"""La calibración del juez — spec 047, T087 (requisito 21.8).

El juez de las pruebas no bloquea una publicación hasta demostrar que coincide con
las personas: corre sobre un conjunto etiquetado a mano en español
(``judge_calibration_es.json``) y su **acuerdo** con las etiquetas, criterio a
criterio, queda como la certificación de clase de la tarea ``judge`` de ese
despliegue (``model_task_certifications``). Aprueba con un 85 % o más.

El informe (cada ejemplo, la etiqueta, lo que dijo el juez y si coinciden) se
guarda en ``scores`` y lo enseña el panel de operador.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.services.testing.judge import (
    CALIBRATION_THRESHOLD,
    JUDGE_TASK,
    agreement,
    calibration_set,
    judge_messages,
    parse_judge,
)

#: La versión del conjunto etiquetado: la «batería» de la tarea ``judge``.
CALIBRATION_VERSION: Final = 1

Judge = Callable[[list[dict[str, str]]], Awaitable[str]]


@dataclass
class CalibrationReport:
    agreement: float
    passed: bool
    items: list[dict[str, Any]] = field(default_factory=list)

    def scores(self) -> dict[str, Any]:
        return {
            "agreement": round(self.agreement, 4),
            "threshold": CALIBRATION_THRESHOLD,
            "set_version": CALIBRATION_VERSION,
            "items": self.items,
        }


async def calibrate(judge: Judge) -> CalibrationReport:
    labels: list[Any] = []
    verdicts: list[Any] = []
    items: list[dict[str, Any]] = []
    for example in calibration_set():
        raw = await judge(
            judge_messages(
                criteria=example["criteria"],
                transcript=example["transcript"],
                actions=example.get("actions") or [],
            )
        )
        result = parse_judge(raw, example["criteria"])
        for dim in result.dimensions:
            label = example["labels"].get(dim.key, "unknown")
            labels.append(label)
            verdicts.append(dim.verdict)
            items.append(
                {
                    "id": example["id"],
                    "key": dim.key,
                    "label": label,
                    "judge": dim.verdict,
                    "match": label == dim.verdict,
                }
            )
    score = agreement(labels, verdicts)
    return CalibrationReport(agreement=score, passed=score >= CALIBRATION_THRESHOLD, items=items)


async def record(
    session: AsyncSession, deployment_id: uuid.UUID, report: CalibrationReport
) -> None:
    """Guarda la calibración como la certificación de la tarea ``judge`` del
    despliegue (la anterior de la misma versión se sustituye)."""
    await session.execute(
        sa.text(
            "INSERT INTO model_task_certifications "
            "(deployment_id, task, battery_version, scores, quality, passed) "
            "VALUES (:d, :t, :v, CAST(:s AS jsonb), :q, :p) "
            "ON CONFLICT (deployment_id, task, battery_version) DO UPDATE SET "
            "scores = EXCLUDED.scores, quality = EXCLUDED.quality, passed = EXCLUDED.passed, "
            "certified_at = now(), invalidated_at = NULL"
        ),
        {
            "d": deployment_id,
            "t": JUDGE_TASK,
            "v": CALIBRATION_VERSION,
            "s": json.dumps(report.scores(), ensure_ascii=False),
            "q": Decimal(str(round(report.agreement, 4))),
            "p": report.passed,
        },
    )


async def latest_report(session: AsyncSession) -> list[dict[str, Any]]:
    rows = (
        (
            await session.execute(
                sa.text(
                    "SELECT c.deployment_id, p.model_id, c.quality, c.passed, c.scores, "
                    "c.certified_at, c.invalidated_at FROM model_task_certifications c "
                    "JOIN model_profiles p ON p.id = c.deployment_id "
                    "WHERE c.task = :t ORDER BY c.certified_at DESC"
                ),
                {"t": JUDGE_TASK},
            )
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]


__all__ = ["CALIBRATION_VERSION", "CalibrationReport", "calibrate", "latest_report", "record"]
