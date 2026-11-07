"""Une las dos ramas que salieron de la 0219, sin tocar nada.

``0220_service_category`` (spec 055) y ``0220_tests_on_the_clients_bag`` → ``0221_classifier_on_haiku``
(spec 047, requisitos 68 y 69) se escribieron a la vez y llegaron a ``develop`` el mismo día. Son
independientes: una añade la categoría de los servicios; la otra, quién paga las pruebas y el
modelo del clasificador. Con dos cabezas, ``alembic upgrade head`` no sabe a cuál subir y el
despliegue se para en la migración.

Revision ID: 0222_merge_0220_heads
Revises: 0220_service_category, 0221_classifier_on_haiku
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0222_merge_0220_heads"
down_revision: str | Sequence[str] | None = ("0220_service_category", "0221_classifier_on_haiku")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
