"""La batería común de la certificación por clase (spec 047, requisito 42.1).

En español, con variantes de España, México, Argentina, Colombia y Chile, con tú
y con usted, y de tres fuentes:

- ``driver``: los casos del driver de evaluación que ya existen (los conjuntos
  sembrados de ``nexus_api.services.evals``);
- ``tau_bench_es``: el paquete en español de τ-bench 2.0. **No viaja en el
  repositorio**: se carga desde ``NEXUS_TAU_BENCH_ES_PATH`` (su licencia se lee
  entera antes, constitución §VIII). Sin él la batería está incompleta y
  :func:`coverage_gaps` lo dice;
- ``reservas``: el dominio propio de reservas (``battery_v1/reservas.json``),
  escrito para cada país y cada trato.

Los casos sin persona escrita (el driver, τ-bench) reciben una por rotación,
determinista, para que cada fuente cubra los diez tratos: la persona es la que
el juez exige que la respuesta respete. La versión, los pesos y el umbral vienen
del manifiesto, que el admin publica con la batería (no del código).
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

COUNTRIES: tuple[str, ...] = ("ES", "MX", "AR", "CO", "CL")
REGISTERS: tuple[str, ...] = ("tu", "usted")
SOURCES_V1: tuple[str, ...] = ("driver", "tau_bench_es", "reservas")

BATTERY_V1_DIR = Path(__file__).parent / "battery_v1"
TAU_BENCH_ENV = "NEXUS_TAU_BENCH_ES_PATH"


@dataclass(frozen=True)
class Persona:
    country: str
    register: str

    @property
    def key(self) -> str:
        return f"{self.country}:{self.register}"


def personas() -> tuple[Persona, ...]:
    return tuple(Persona(c, r) for c in COUNTRIES for r in REGISTERS)


@dataclass(frozen=True)
class BatteryCase:
    id: str
    source: str
    task: str
    persona: Persona | None
    user_message: str
    history: tuple[Mapping[str, Any], ...]
    assertions: Mapping[str, Any]
    critical: bool = False


@dataclass(frozen=True)
class Battery:
    version: int
    cases: tuple[BatteryCase, ...]
    weights: Mapping[str, float]
    threshold: float

    @classmethod
    def build(
        cls,
        *,
        version: int,
        cases: Iterable[BatteryCase],
        weights: Mapping[str, float],
        threshold: float,
    ) -> Battery:
        """Reparte personas, por fuente y en rotación, a los casos que no la traen."""
        out: list[BatteryCase] = []
        turn: dict[str, int] = {}
        every = personas()
        for case in cases:
            if case.persona is None:
                n = turn.get(case.source, 0)
                turn[case.source] = n + 1
                case = replace(case, persona=every[n % len(every)])
            out.append(case)
        return cls(version=version, cases=tuple(out), weights=dict(weights), threshold=threshold)

    def for_task(self, task: str) -> tuple[BatteryCase, ...]:
        return tuple(c for c in self.cases if c.task == task)


def coverage_gaps(battery: Battery) -> list[str]:
    """Lo que le falta a la batería para certificar con ella."""
    gaps: list[str] = []
    wanted = {p.key for p in personas()}
    for source in SOURCES_V1:
        cases = [c for c in battery.cases if c.source == source]
        if not cases:
            gaps.append(f"{source}: sin casos")
            continue
        seen = {c.persona.key for c in cases if c.persona is not None}
        missing = sorted(wanted - seen)
        if missing:
            gaps.append(f"{source}: faltan {', '.join(missing)}")
    return gaps


def _task_of(assertions: Mapping[str, Any]) -> str:
    """Un caso que espera herramientas es un turno con herramientas."""
    return "tool_turn" if assertions.get("expected_tools_called") else "answer"


def driver_cases() -> list[BatteryCase]:
    """Los casos sembrados del driver de evaluación (95 en la v1)."""
    from nexus_api.services.evals.seed_loader import available_seeds, resolve_seed_payload

    out: list[BatteryCase] = []
    for seed in available_seeds():
        payload = resolve_seed_payload(seed)
        for raw in payload.get("cases") or ():
            assertions = dict(raw.get("assertions") or {})
            out.append(
                BatteryCase(
                    id=f"driver:{seed}:{raw.get('idx')}",
                    source="driver",
                    task=_task_of(assertions),
                    persona=None,
                    user_message=str(raw.get("user_message") or ""),
                    history=tuple(raw.get("history") or ()),
                    assertions=assertions,
                )
            )
    return out


def reservas_cases(path: Path | None = None) -> list[BatteryCase]:
    """El dominio propio: cada escenario, en cada país y cada trato."""
    data = json.loads((path or BATTERY_V1_DIR / "reservas.json").read_text(encoding="utf-8"))
    register_q: Mapping[str, str] = data.get("register_questions") or {}
    common_q: Sequence[str] = data.get("common_questions") or ()
    out: list[BatteryCase] = []
    for scenario in data["scenarios"]:
        for key, message in scenario["messages"].items():
            country, register = key.split(":")
            base = dict(scenario.get("assertions") or {})
            questions = [*base.get("judge_questions", ()), *common_q]
            if register in register_q:
                questions.append(register_q[register])
            out.append(
                BatteryCase(
                    id=f"reservas:{scenario['id']}:{key}",
                    source="reservas",
                    task=str(scenario.get("task") or _task_of(base)),
                    persona=Persona(country, register),
                    user_message=str(message),
                    history=(),
                    assertions={**base, "judge_questions": questions},
                    critical=bool(scenario.get("critical")),
                )
            )
    return out


def tau_bench_cases(path: Path | None) -> list[BatteryCase]:
    """El paquete ``es`` de τ-bench 2.0, ya convertido a casos (lista JSON con
    ``id``, ``user_message``, ``history``, ``assertions`` y, si la trae,
    ``country`` y ``register``). Sin ruta, ninguno."""
    if path is None or not path.is_file():
        return []
    out: list[BatteryCase] = []
    for raw in json.loads(path.read_text(encoding="utf-8")):
        assertions = dict(raw.get("assertions") or {})
        persona = (
            Persona(str(raw["country"]), str(raw["register"]))
            if raw.get("country") and raw.get("register")
            else None
        )
        out.append(
            BatteryCase(
                id=f"tau_bench_es:{raw['id']}",
                source="tau_bench_es",
                task=str(raw.get("task") or _task_of(assertions)),
                persona=persona,
                user_message=str(raw.get("user_message") or ""),
                history=tuple(raw.get("history") or ()),
                assertions=assertions,
                critical=bool(raw.get("critical")),
            )
        )
    return out


def load_battery_v1(*, tau_bench_path: Path | None = None) -> Battery:
    manifest = json.loads((BATTERY_V1_DIR / "manifest.json").read_text(encoding="utf-8"))
    if tau_bench_path is None and os.environ.get(TAU_BENCH_ENV):
        tau_bench_path = Path(os.environ[TAU_BENCH_ENV])
    cases = [*driver_cases(), *tau_bench_cases(tau_bench_path), *reservas_cases()]
    return Battery.build(
        version=int(manifest["version"]),
        cases=cases,
        weights={k: float(v) for k, v in manifest["weights"].items()},
        threshold=float(manifest["threshold"]),
    )


__all__ = [
    "BATTERY_V1_DIR",
    "COUNTRIES",
    "REGISTERS",
    "SOURCES_V1",
    "TAU_BENCH_ENV",
    "Battery",
    "BatteryCase",
    "Persona",
    "coverage_gaps",
    "driver_cases",
    "load_battery_v1",
    "personas",
    "reservas_cases",
    "tau_bench_cases",
]
