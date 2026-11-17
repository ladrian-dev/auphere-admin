"""Crear un anuncio de Quédate pide los ids del catálogo en el mismo turno — spec 061,
requisito 4.9 (staging, 2026-11-17).

El agente consultó el catálogo en un turno y creó el anuncio en el siguiente. Entre
turnos no conserva lo que devolvió una herramienta, así que el tipo de propiedad que
mandó no existía y Quédate lo rechazó. ``quedate.create_my_listing`` y
``quedate.create_listing`` dicen ahora que ``property_type_id`` y ``sector_id`` se
buscan en el mismo turno con ``quedate.listing_options`` y ``quedate.list_locations``.

Actualiza la descripción y los esquemas de esas dos filas de ``tool_catalog`` desde
``alembic/data/0235_quedate_listing_catalog_ids.json``, una instantánea de los modelos
Pydantic, como hicieron la 0233 y la 0234. Deshacerla vuelve a las de la 0233, que la
0234 no tocó.

Revision ID: 0235_quedate_listing_catalog_ids
Revises: 0234_quedate_tool_descriptions
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0235_quedate_listing_catalog_ids"
down_revision: str | Sequence[str] | None = "0234_quedate_tool_descriptions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DATA = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
NEW_PATH = os.path.join(_DATA, "0235_quedate_listing_catalog_ids.json")
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
