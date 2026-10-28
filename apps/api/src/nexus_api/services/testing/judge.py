"""El juez de las pruebas y su calibración — spec 047, T086 y T087 (requisitos 21.3 y 21.8; research D18).

Dos comprobaciones por pasada, en este orden:

1. **El estado final** (21.3), sin modelo: lo que la prueba espera que quede
   hecho (``expected_state``) contra lo que quedó en el mundo simulado. Una cita
   que no existe no la arregla una buena frase.
2. **El juez** (21.8), de otra familia que el agente: **una dimensión por
   criterio**, cada una ``pass``, ``fail`` o ``unknown`` («No sé»), con su porqué.

El juez **no bloquea** una publicación hasta estar calibrado contra etiquetas
humanas en español: la calibración es la certificación de clase de la tarea
``judge`` (``model_task_certifications``), con el acuerdo con las etiquetas como
nota. Sin ella, sus dimensiones se enseñan pero la pasada se decide solo por el
estado final.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Literal

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

Verdict = Literal["pass", "fail", "unknown"]

#: El acuerdo mínimo con las etiquetas humanas para que el juez bloquee.
CALIBRATION_THRESHOLD: Final = 0.85
CALIBRATION_SET: Final = Path(__file__).with_name("judge_calibration_es.json")
JUDGE_TASK: Final = "judge"


# ── el estado final ─────────────────────────────────────────────────────────


def _subset(expected: Any, actual: Any, path: str, checked: list[str]) -> bool:
    if isinstance(expected, Mapping):
        if not isinstance(actual, Mapping):
            checked.append(f"{path}: se esperaba un objeto")
            return False
        ok = True
        for key, value in expected.items():
            ok = _subset(value, actual.get(key), f"{path}/{key}", checked) and ok
        return ok
    good = bool(expected == actual)
    checked.append(
        f"{path}: se esperaba {json.dumps(expected, ensure_ascii=False)} y quedó "
        f"{json.dumps(actual, ensure_ascii=False)}"
        if not good
        else f"{path}: ok"
    )
    return good


#: Claves del estado esperado que solo dicen de dónde sale una respuesta: el
#: juez las mira, el estado no.
_ADVISORY: Final = frozenset({"answered_from"})


def check_state(
    expected: Mapping[str, Any], final: Mapping[str, Any]
) -> tuple[bool | None, list[str]]:
    """``(None, [])`` si la prueba no espera ningún estado; si no, si se cumple
    y lo que se comprobó, en palabras."""
    wanted = {k: v for k, v in (expected or {}).items() if k not in _ADVISORY}
    if not wanted:
        return None, []
    checked: list[str] = []
    ok = _subset(wanted, final, "", checked)
    return ok, checked


# ── el juez ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Dimension:
    key: str
    verdict: Verdict
    why: str = ""

    def to_json(self) -> dict[str, str]:
        return {"key": self.key, "verdict": self.verdict, "why": self.why}


@dataclass(frozen=True)
class JudgeResult:
    dimensions: tuple[Dimension, ...] = field(default_factory=tuple)

    @property
    def any_fail(self) -> bool:
        return any(d.verdict == "fail" for d in self.dimensions)

    @property
    def all_unknown(self) -> bool:
        return bool(self.dimensions) and all(d.verdict == "unknown" for d in self.dimensions)


JUDGE_SYSTEM: Final = (
    "Eres el juez de las pruebas de un agente de WhatsApp de un negocio. Lees una "
    "conversación SIMULADA (no hay clientes reales) y decides, criterio a criterio, si el "
    "agente lo cumplió. Para cada criterio responde exactamente uno de: pass, fail, unknown. "
    "Usa unknown («No sé») si la conversación no te deja saberlo. No inventes criterios. "
    'Responde solo con JSON: {"dimensions": [{"key": str, "verdict": "pass"|"fail"|"unknown", '
    '"why": str}]}'
)


def judge_messages(
    *,
    criteria: Sequence[Mapping[str, Any]],
    transcript: Sequence[Mapping[str, Any]],
    actions: Sequence[str],
) -> list[dict[str, str]]:
    lines = [f"{t.get('role')}: {' / '.join(t.get('bubbles') or [])}" for t in transcript]
    crit = "\n".join(f"- {c.get('key')}: {c.get('text')}" for c in criteria)
    user = (
        "<conversacion>\n" + "\n".join(lines) + "\n</conversacion>\n"
        "<acciones>\n" + "\n".join(actions) + "\n</acciones>\n"
        "<criterios>\n" + crit + "\n</criterios>"
    )
    return [{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": user}]


def parse_judge(text: str, criteria: Sequence[Mapping[str, Any]]) -> JudgeResult:
    """Lo que dijo el juez, criterio a criterio. Lo que no se puede leer, o un
    criterio del que no dijo nada, es «No sé»: nunca un aprobado regalado."""
    wanted = [str(c.get("key")) for c in criteria]
    found: dict[str, Dimension] = {}
    try:
        raw = text.strip()
        start, end = raw.find("{"), raw.rfind("}")
        data = json.loads(raw[start : end + 1]) if start >= 0 and end > start else {}
        for dim in data.get("dimensions") or []:
            key = str(dim.get("key"))
            verdict = str(dim.get("verdict"))
            if key in wanted and verdict in {"pass", "fail", "unknown"}:
                found[key] = Dimension(key, verdict, str(dim.get("why") or "")[:300])  # type: ignore[arg-type]
    except (ValueError, AttributeError, TypeError):
        found = {}
    return JudgeResult(
        tuple(found.get(k) or Dimension(k, "unknown", "El juez no lo dijo.") for k in wanted)
    )


def attempt_passed(
    state_ok: bool | None, judge: JudgeResult | None, *, judge_blocks: bool
) -> bool | None:
    """Una pasada: falla si falla el estado; con el juez calibrado, también si
    falla una dimensión. ``None`` («No sé») si no hay nada que decida."""
    if state_ok is False:
        return False
    if judge is not None and judge_blocks:
        if judge.any_fail:
            return False
        if state_ok is None and judge.all_unknown:
            return None
        return True
    if state_ok is None:
        # Sin estado que comprobar y sin juez que bloquee, la pasada no se
        # puede dar por buena ni por mala.
        if judge is not None and judge.dimensions and not judge.any_fail and not judge.all_unknown:
            return True
        return None
    return True


# ── calibración ────────────────────────────────────────────────────────────


def calibration_set() -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = json.loads(CALIBRATION_SET.read_text(encoding="utf-8"))
    return data


def agreement(labels: Sequence[Verdict], verdicts: Sequence[Verdict]) -> float:
    """El acuerdo del juez con las etiquetas humanas. Un «No sé» del juez cuenta
    como desacuerdo salvo que la etiqueta también lo sea."""
    if not labels:
        return 0.0
    hits = sum(1 for a, b in zip(labels, verdicts, strict=True) if a == b)
    return hits / len(labels)


async def judge_calibrated(session: AsyncSession) -> bool:
    """¿Hay un despliegue del juez con su calibración vigente y aprobada?"""
    found = await session.scalar(
        sa.text(
            "SELECT 1 FROM model_task_certifications "
            "WHERE task = :t AND passed AND invalidated_at IS NULL LIMIT 1"
        ),
        {"t": JUDGE_TASK},
    )
    return found is not None


_KEY = re.compile(r"[^a-z0-9_]+")


def criterion_key(text: str, index: int) -> str:
    return _KEY.sub("_", text.lower())[:40].strip("_") or f"c{index}"


__all__ = [
    "CALIBRATION_THRESHOLD",
    "JUDGE_TASK",
    "Dimension",
    "JudgeResult",
    "agreement",
    "attempt_passed",
    "calibration_set",
    "check_state",
    "criterion_key",
    "judge_calibrated",
    "judge_messages",
    "parse_judge",
]
