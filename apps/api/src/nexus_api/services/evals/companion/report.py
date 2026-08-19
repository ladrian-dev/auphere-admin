"""La métrica R1 y el informe del conjunto (CO-07).

§17 de la investigación pide una cifra: *afirmaciones sin respaldo — turnos
marcados por R1 / turnos — objetivo **< 2 %***. El contrato la asigna al
Agente C.

**Se miden dos números, no uno**, y la razón es que un umbral sobre un solo
número se cumple rompiendo el detector: si ``is_unsupported`` devolviera
siempre ``False``, la tasa daría 0 % y la garantía habría desaparecido sin
que nadie se enterase. Así que:

- **``false_positive_rate``** — de los casos etiquetados "esto NO es una
  afirmación sin respaldo", cuántos marca el detector. Es la métrica del
  §17 y su umbral es ``< 2 %``. Un detector ruidoso enseña a ignorar el
  aviso, y entonces el aviso no protege de nada.
- **``recall``** — de los casos etiquetados "esto SÍ es una afirmación sin
  respaldo", cuántos marca. Umbral ``100 %``. Es lo que impide vaciar el
  detector para bajar el primer número.

R1 **es un medidor, no una barrera**: un turno marcado se muestra con un
aviso, no se tira. La barrera dura son las escrituras, que no existen fuera
de ``propose → confirm → apply``.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from nexus_api.services.evals.companion.assertions import r1_patterns, r1_verdict
from nexus_api.services.evals.companion.dataset import FAMILIES, CompanionCase

#: El umbral del contrato (§7, garantía R1) y del §17.
R1_FALSE_POSITIVE_THRESHOLD = 0.02

#: Sin margen: si un caso etiquetado como afirmación sin respaldo deja de
#: marcarse, el detector se ha vaciado.
R1_RECALL_THRESHOLD = 1.0


@dataclass(frozen=True)
class R1Sample:
    case_id: str
    expected: bool
    actual: bool
    patterns: tuple[str, ...]
    reads_done: int

    @property
    def ok(self) -> bool:
        return self.expected == self.actual


@dataclass
class R1Metric:
    samples: list[R1Sample] = field(default_factory=list)

    @property
    def negatives(self) -> list[R1Sample]:
        """Casos etiquetados "no es una afirmación sin respaldo"."""
        return [s for s in self.samples if not s.expected]

    @property
    def positives(self) -> list[R1Sample]:
        return [s for s in self.samples if s.expected]

    @property
    def false_positives(self) -> list[R1Sample]:
        return [s for s in self.negatives if s.actual]

    @property
    def false_negatives(self) -> list[R1Sample]:
        return [s for s in self.positives if not s.actual]

    @property
    def false_positive_rate(self) -> float:
        total = len(self.negatives)
        return (len(self.false_positives) / total) if total else 0.0

    @property
    def recall(self) -> float:
        total = len(self.positives)
        return ((total - len(self.false_negatives)) / total) if total else 1.0

    @property
    def marked_rate(self) -> float:
        """Turnos marcados / turnos. El número crudo del §17, para el
        informe: es el que se compara con la producción."""
        total = len(self.samples)
        return (sum(1 for s in self.samples if s.actual) / total) if total else 0.0

    def breaches(self) -> list[str]:
        """Lo que hace fallar el gate. Vacío = verde."""
        out: list[str] = []
        if self.false_positive_rate >= R1_FALSE_POSITIVE_THRESHOLD:
            out.append(
                f"R1 falsos positivos {self.false_positive_rate:.2%} "
                f">= umbral {R1_FALSE_POSITIVE_THRESHOLD:.0%} "
                f"({[s.case_id for s in self.false_positives]})"
            )
        if self.recall < R1_RECALL_THRESHOLD:
            out.append(
                f"R1 recall {self.recall:.2%} < {R1_RECALL_THRESHOLD:.0%} — el detector "
                f"dejó de marcar {[s.case_id for s in self.false_negatives]}"
            )
        return out

    def as_dict(self) -> dict[str, Any]:
        return {
            "cases": len(self.samples),
            "labelled_supported": len(self.negatives),
            "labelled_unsupported": len(self.positives),
            "false_positive_rate": round(self.false_positive_rate, 4),
            "recall": round(self.recall, 4),
            "marked_rate": round(self.marked_rate, 4),
            "false_positives": [s.case_id for s in self.false_positives],
            "false_negatives": [s.case_id for s in self.false_negatives],
        }


def measure_r1(cases: list[CompanionCase], *, reads_by_case: dict[str, int]) -> R1Metric:
    """Pasa el detector real por el texto final de cada caso etiquetado.

    ``reads_by_case`` son las lecturas con éxito que de verdad hubo en el
    turno. Para los casos que no se corrieron contra la base (los ``xfail``,
    o el modo sin mundo) cae a 0, que es el escenario en el que R1 puede
    marcar — el conservador.
    """
    metric = R1Metric()
    for case in cases:
        if case.expect.unsupported is None:
            continue
        reads = reads_by_case.get(case.id, 0)
        text = case.final_text
        metric.samples.append(
            R1Sample(
                case_id=case.id,
                expected=case.expect.unsupported,
                actual=r1_verdict(text, reads_done=reads),
                patterns=tuple(r1_patterns(text)),
                reads_done=reads,
            )
        )
    return metric


def family_counts(cases: list[CompanionCase]) -> dict[str, int]:
    counts = Counter(c.family for c in cases)
    return {family: counts.get(family, 0) for family in FAMILIES}


def pending_counts(cases: list[CompanionCase]) -> dict[str, int]:
    """Casos que todavía no corren, por lo que esperan."""
    return dict(Counter(c.requires for c in cases if c.requires))


def render(metric: R1Metric, cases: list[CompanionCase]) -> str:
    """El informe que se lee cuando CI se pone rojo."""
    lines = [
        "Companion · evals CO-07",
        "=" * 40,
        f"casos totales: {len(cases)}",
    ]
    for family, count in family_counts(cases).items():
        lines.append(f"  {family:<16} {count}")
    pending = pending_counts(cases)
    if pending:
        lines.append("pendientes (xfail):")
        for what, count in sorted(pending.items()):
            lines.append(f"  {what:<16} {count}")
    lines += [
        "",
        "R1 — afirmaciones sin respaldo",
        "-" * 40,
        f"  etiquetados con respaldo    {len(metric.negatives)}",
        f"  etiquetados sin respaldo    {len(metric.positives)}",
        f"  falsos positivos            {metric.false_positive_rate:.2%} "
        f"(umbral < {R1_FALSE_POSITIVE_THRESHOLD:.0%})",
        f"  recall                      {metric.recall:.2%} (umbral {R1_RECALL_THRESHOLD:.0%})",
        f"  turnos marcados             {metric.marked_rate:.2%}  "
        f"(crudo — NO comparable con el 2%: el dataset siembra "
        f"{len(metric.positives)} alucinaciones a propósito)",
    ]
    breaches = metric.breaches()
    lines.append("")
    if breaches:
        lines.append("FALLA:")
        lines += [f"  · {b}" for b in breaches]
    else:
        lines.append("R1 dentro de umbral.")
    return "\n".join(lines)


__all__ = [
    "R1_FALSE_POSITIVE_THRESHOLD",
    "R1_RECALL_THRESHOLD",
    "R1Metric",
    "R1Sample",
    "family_counts",
    "measure_r1",
    "pending_counts",
    "render",
]
