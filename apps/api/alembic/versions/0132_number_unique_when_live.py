"""Un número desvinculado no ocupa sitio (spec 021, Historia 1).

La unicidad del número era una restricción sin condición: un número existía
una vez en toda la plataforma, para siempre. Desvincular (spec 019) conserva
la fila —historial, reconectar— y por eso el número quedaba **ocupado** por un
canal que ya no atendía: el mismo cliente podía reactivarlo, pero ningún otro,
ni de otro partner, podía conectarlo. Recibía «este número está en uso», que
era verdad para un número vivo en otro sitio y falso para uno que su dueño
había soltado.

El índice parcial es lo único que cumple las dos cosas a la vez: dos canales
**vivos** no comparten número; uno vivo y uno desvinculado sí. La fila se
queda, el número se libera.

**La bajada se niega si ya hay dos filas con el mismo número** (una viva y una
desvinculada): recrear la restricción vieja fallaría con ellas, y es mejor un
``downgrade`` que no corre que uno que borra historial para poder correr.

Revision ID: 0132_number_unique_when_live
Revises: 0131_audit_vocab_disconnect
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0132_number_unique_when_live"
down_revision: str | Sequence[str] | None = "0131_audit_vocab_disconnect"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE channels DROP CONSTRAINT uq_channels_type_provider_id")
    op.execute(
        "CREATE UNIQUE INDEX uq_channels_live_number "
        "ON channels (type, provider_identifier) "
        "WHERE status <> 'disconnected'"
    )


def downgrade() -> None:
    # Si hay un número repetido entre una fila viva y una desvinculada, el
    # ADD CONSTRAINT falla solo, y con el motivo. No se borra nada para que
    # pase.
    op.execute("DROP INDEX uq_channels_live_number")
    op.execute(
        "ALTER TABLE channels ADD CONSTRAINT uq_channels_type_provider_id "
        "UNIQUE (type, provider_identifier)"
    )
