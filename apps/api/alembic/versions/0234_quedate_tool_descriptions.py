"""Las herramientas de Quédate dicen de dónde sale el id del anuncio — spec 061,
requisito 4.8 (staging, 2026-11-17).

Entre turnos, el agente no conserva lo que devolvió una herramienta. Sin el
``listing_id`` del anuncio que creó, pasaba la conversación a una persona en vez de
buscarlo. Las que lo reciben (fotos, revisión, ocultar, ver; y la cotización)
dicen ahora dónde encontrarlo: ``quedate.my_listings``, ``quedate.list_listings``
o ``quedate.search_listings``.

Actualiza la descripción y los esquemas de esas filas de ``tool_catalog`` desde
``alembic/data/0234_quedate_tool_descriptions.json``, una instantánea de los
modelos Pydantic, como hizo la 0233. Deshacerla vuelve a las de la 0233.

Revision ID: 0234_quedate_tool_descriptions
Revises: 0233_quedate_connector
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0234_quedate_tool_descriptions"
down_revision: str | Sequence[str] | None = "0233_quedate_connector"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DATA = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
NEW_PATH = os.path.join(_DATA, "0234_quedate_tool_descriptions.json")
OLD_PATH = os.path.join(_DATA, "0233_quedate_tools.json")


def _apply(catalog: dict[str, dict], names: list[str]) -> None:
    bind = op.get_bind()
    for name in names:
        spec = catalog[name]
        bind.execute(
            sa.text(
                """
                UPDATE tool_catalog
                SET description = :description,
                    input_schema = CAST(:input_schema AS jsonb),
                    output_schema = CAST(:output_schema AS jsonb)
                WHERE name = :name
                """
            ),
            {
                "name": name,
                "description": spec["description"],
                "input_schema": json.dumps(spec["input_schema"]),
                "output_schema": json.dumps(spec["output_schema"]),
            },
        )


def upgrade() -> None:
    with open(NEW_PATH, encoding="utf-8") as fh:
        new: dict[str, dict] = json.load(fh)
    _apply(new, sorted(new))


def downgrade() -> None:
    with open(NEW_PATH, encoding="utf-8") as fh:
        names = sorted(json.load(fh))
    with open(OLD_PATH, encoding="utf-8") as fh:
        old: dict[str, dict] = json.load(fh)
    _apply(old, names)
