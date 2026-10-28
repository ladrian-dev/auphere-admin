"""El catálogo de pruebas del sector, versión 1 — spec 047, T090 (requisitos 21.1 y 54.10).

12 pruebas por cada uno de los 6 sectores del constructor (barbería y
peluquería; clínica dental y estética; restaurante y cafetería; tienda y comercio
online; servicios profesionales; mayorista). Las escribió Auphere y viven en
``alembic/data/0188_sector_tests_v1.json``; desde aquí se editan en el panel de
operador, publicando versiones nuevas (``sector@versión``).

Tabla de plataforma: sin datos de ningún cliente.

Revision ID: 0188_sector_tests_v1
Revises: 0187_agent_spec_and_testing
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa

from alembic import op

revision: str = "0188_sector_tests_v1"
down_revision: str | Sequence[str] | None = "0187_agent_spec_and_testing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DATA = Path(__file__).resolve().parent.parent / "data" / "0188_sector_tests_v1.json"


def upgrade() -> None:
    catalog: dict[str, list[dict[str, object]]] = json.loads(DATA.read_text(encoding="utf-8"))
    bind = op.get_bind()
    for sector, tests in catalog.items():
        bind.execute(
            sa.text(
                "INSERT INTO sector_test_catalog (sector_key, version, tests, published_by) "
                "VALUES (:k, 1, CAST(:t AS jsonb), 'auphere:spec-047') "
                "ON CONFLICT (sector_key, version) DO NOTHING"
            ),
            {"k": sector, "t": json.dumps(tests, ensure_ascii=False)},
        )


def downgrade() -> None:
    op.execute("DELETE FROM sector_test_catalog WHERE version = 1")
