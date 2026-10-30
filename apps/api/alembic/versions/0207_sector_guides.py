"""Las guías de Auphere convertidas desde una guía generada — spec 047, enmienda del
2026-10-29 (T201; requisito 58.5; research D47, D65 y D66).

- **``sector_guides``** (de plataforma, sin ``tenant_id``): la guía del sector que
  Auphere convierte desde la guía generada de un cliente, revisada y sin datos del
  cliente («Convertir en guía de Auphere»). Su clave es la de ``promoted_to`` en
  ``generated_guides`` y la de sus 12 pruebas en ``sector_test_catalog``. Nada en
  la fila apunta al cliente del que salió: eso queda en la auditoría del cliente.
  Desde entonces, un cliente de «otro» con la misma etiqueta normalizada
  (``label_key``) recibe esta guía en lugar de generar la suya (D66).

Las guías salidas de las plantillas viven en el código
(``services/builder/guides/``), no aquí: esta tabla solo tiene las convertidas.

La lee el constructor dentro del contexto de un cliente (``nexus_app``: solo
``SELECT``); la escribe el panel de operador, con el rol de la plataforma.

Revision ID: 0207_sector_guides
Revises: 0206_sector_guides_builder
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0207_sector_guides"
down_revision: str | Sequence[str] | None = "0206_sector_guides_builder"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = """
CREATE TABLE sector_guides (
    key varchar(40) PRIMARY KEY,
    label varchar(40) NOT NULL,
    label_key varchar(60) NOT NULL,
    guide jsonb NOT NULL,
    version integer NOT NULL DEFAULT 1,
    published_by varchar(160) NOT NULL,
    published_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_sector_guides_label_key UNIQUE (label_key),
    CONSTRAINT ck_sector_guides_key CHECK (key ~ '^[a-z_]{2,40}$'),
    CONSTRAINT ck_sector_guides_label CHECK (char_length(label) BETWEEN 1 AND 40),
    CONSTRAINT ck_sector_guides_label_key CHECK (label_key ~ '^[a-z0-9_ ]{1,60}$'),
    CONSTRAINT ck_sector_guides_guide CHECK (jsonb_typeof(guide) = 'object'),
    CONSTRAINT ck_sector_guides_version CHECK (version >= 1)
)
"""


def upgrade() -> None:
    op.execute(TABLE)
    # El constructor la lee con el cliente puesto; solo el panel la escribe. Los
    # privilegios por defecto del esquema le darían todo a ``nexus_app``.
    op.execute("REVOKE ALL ON sector_guides FROM nexus_app")
    op.execute("GRANT SELECT ON sector_guides TO nexus_app")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sector_guides")
