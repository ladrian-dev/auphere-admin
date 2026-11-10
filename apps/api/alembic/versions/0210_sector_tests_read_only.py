"""``sector_test_catalog``, solo de lectura para ``nexus_app`` — spec 047, T217
(revisión de seguridad del 2026-10-30).

Las pruebas del sector son de plataforma: entran en la suite de cada cliente del
sector (``testing/sector_catalog.add_sector_tests``). La 0187 le dio a
``nexus_app`` ``SELECT, INSERT, UPDATE, DELETE``; con eso, cualquier camino que
corra con el contexto de un cliente podría cambiar las pruebas de todos.

Desde aquí, como ``sector_guides`` (0207): ``nexus_app`` solo la lee. Las escriben
el panel de operador (``api/admin/sector_tests.py``) y la conversión de una guía
(``services/builder/guides/promotion.py``, que declara el cliente sin bajar de
rol), las dos con el rol de la plataforma; ninguna pasa por ``nexus_app``.

Revision ID: 0210_sector_tests_read_only
Revises: 0209_audit_words_sector_guides
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0210_sector_tests_read_only"
down_revision: str | Sequence[str] | None = "0209_audit_words_sector_guides"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # REVOKE ALL y no solo la escritura: los privilegios por defecto del esquema
    # pueden haberle dado también TRUNCATE, REFERENCES o TRIGGER.
    op.execute("REVOKE ALL ON sector_test_catalog FROM nexus_app")
    op.execute("GRANT SELECT ON sector_test_catalog TO nexus_app")


def downgrade() -> None:
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON sector_test_catalog TO nexus_app")
