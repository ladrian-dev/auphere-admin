"""Lo que necesita cada prueba del sector — spec 047, enmienda del 2026-10-30
(requisito 65.8; research D74).

Cada prueba del catálogo del sector declara las acciones que tiene que poder hacer
el agente para que aplique (``needs``, las de ``capability_names``). Al añadir las
pruebas a un agente, la que necesita una acción que sus herramientas no hacen
queda «No aplica», con su razón, sin que nadie la marque.

Escribe ``needs`` en la versión 1 que sembró la 0188 (``auphere:spec-047``): las
de pedir cita necesitan reservar; las demás, nada. Es un dato de cómo se aplica
la prueba, no de lo que comprueba: la versión no cambia. Una versión publicada
desde el panel no se toca. Bajar quita ``needs`` de esa versión y nada más.

Tabla de plataforma: sin datos de ningún cliente.

Revision ID: 0208_sector_test_needs
Revises: 0207_sector_guides
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "0208_sector_test_needs"
down_revision: str | Sequence[str] | None = "0207_sector_guides"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEEDED_BY = "auphere:spec-047"
#: ``sector#prueba`` → lo que necesita. Las que no están aquí, nada.
NEEDS: dict[str, list[str]] = {
    "barberia_peluqueria#book": ["book"],
    "barberia_peluqueria#closed_day": ["book"],
    "clinica#book": ["book"],
    "restaurante#book_table": ["book"],
}


def _rows() -> list[Any]:
    return list(
        op.get_bind()
        .execute(
            sa.text(
                "SELECT sector_key, tests FROM sector_test_catalog "
                "WHERE version = 1 AND published_by = :by"
            ),
            {"by": SEEDED_BY},
        )
        .all()
    )


def _write(sector: str, tests: list[dict[str, Any]]) -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE sector_test_catalog SET tests = CAST(:t AS jsonb) "
            "WHERE sector_key = :k AND version = 1 AND published_by = :by"
        ),
        {"t": json.dumps(tests, ensure_ascii=False), "k": sector, "by": SEEDED_BY},
    )


def _tests(raw: Any) -> list[dict[str, Any]]:
    value = json.loads(raw) if isinstance(raw, str) else raw
    return [dict(t) for t in value or []]


def upgrade() -> None:
    for sector, raw in _rows():
        tests = _tests(raw)
        for test in tests:
            test.setdefault("needs", NEEDS.get(f"{sector}#{test.get('key')}", []))
        _write(sector, tests)


def downgrade() -> None:
    for sector, raw in _rows():
        tests = _tests(raw)
        for test in tests:
            test.pop("needs", None)
        _write(sector, tests)
