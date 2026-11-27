"""Spec 082 (requisito 1.4) — todo lo que deja historial de una reserva avisa.

El aviso ``reservations.changed`` sale desde ``core.add_event``. Vale para la
API, las herramientas del agente y el worker solo si **nadie** escribe el
historial por otro camino. Este barrido lee el código de ``apps/`` y falla si
un ``ReservationEvent(`` se construye fuera de ``add_event``: una escritura
nueva que se lo salte no avisaría a la agenda abierta.
"""

from __future__ import annotations

import ast
from pathlib import Path

APPS = Path(__file__).resolve().parents[3]
ROOTS = [APPS / "api" / "src", APPS / "worker" / "src", APPS / "mcp" / "src"]
ALLOWED = {("nexus_api/services/reservations/core.py", "add_event")}


def _builders() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for root in ROOTS:
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            rel = path.relative_to(root).as_posix()
            for fn in ast.walk(tree):
                if not isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                for node in ast.walk(fn):
                    if (
                        isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Name | ast.Attribute)
                        and (getattr(node.func, "id", None) or getattr(node.func, "attr", None))
                        == "ReservationEvent"
                    ):
                        found.append((rel, fn.name))
    return found


def test_the_history_of_a_booking_is_written_only_by_add_event() -> None:
    builders = _builders()
    assert builders, "el barrido no encontró ni add_event: ¿se movió el código?"
    outside = sorted({b for b in builders if b not in ALLOWED})
    assert outside == [], (
        f"ReservationEvent construido fuera de core.add_event (no avisaría a la agenda): {outside}"
    )


def test_add_event_marks_the_session() -> None:
    src = (ROOTS[0] / "nexus_api/services/reservations/core.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    add_event = next(
        n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "add_event"
    )
    calls = {
        getattr(c.func, "id", None) or getattr(c.func, "attr", None)
        for c in ast.walk(add_event)
        if isinstance(c, ast.Call)
    }
    assert "mark_changed" in calls
