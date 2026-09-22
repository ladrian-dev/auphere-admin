"""Spec 012 — qué instalación es una máquina (R3.7).

Hasta ahora una máquina se identificaba por su ``hostname``, y no sirve: cambia
cuando alguien renombra su ordenador, y dos «MacBook-Pro» en el mismo partner son
perfectamente normales. Con el código de emparejamiento eso apenas se notaba,
porque registrar costaba un trámite y nadie lo repetía por error. Con el registro
silencioso pasa a notarse: dos filas donde hay un ordenador, consumiendo el tope
de cinco.

``install_id`` lo genera la aplicación la primera vez y lo guarda **aparte de la
credencial**, para que sobreviva a desemparejar.

**Nullable a propósito.** Las filas de antes no lo tienen y no se les inventa
uno: una máquina registrada con el código viejo sigue valiendo (R6.2) y
simplemente no participa de la deduplicación hasta que vuelva a registrarse. Un
``install_id`` inventado para una fila vieja sería peor que ninguno — diría que
sabemos qué ordenador es cuando no lo sabemos.

**El índice es parcial**: solo las activas. Las archivadas no deduplican, porque
archivar es terminal y volver a registrar crea fila nueva. Sin el `WHERE`, una
máquina archivada bloquearía para siempre el registro de la misma instalación.

Revision ID: 0125_device_install_id
Revises: 0124_access_revoked_vocab
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0125_device_install_id"
down_revision: str | Sequence[str] | None = "0124_access_revoked_vocab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX = "ix_partner_devices_install_active"


def upgrade() -> None:
    op.add_column("partner_devices", sa.Column("install_id", sa.Text(), nullable=True))
    op.execute(
        f"""
        CREATE INDEX {INDEX}
            ON partner_devices (principal_id, install_id)
         WHERE install_id IS NOT NULL AND revoked_at IS NULL
        """
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {INDEX}")
    op.drop_column("partner_devices", "install_id")
