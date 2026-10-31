"""QA canales Meta 2026-10-31: el identificador de un mensaje de Instagram cabe.

Un DM de Instagram llegó a staging y no se guardó: su ``mid`` mide unos 230
caracteres y ``messages.provider_message_id`` era ``varchar(160)``, pensado
para los ``wamid`` de WhatsApp. El turno fallaba con
``StringDataRightTruncationError`` y el mensaje no llegaba a la bandeja.

Las tres columnas que guardan el identificador de Meta de un mensaje pasan a
512: el propio, al que reacciona y al que responde. En Postgres, ensanchar un
``varchar`` no reescribe la tabla. Bajar vuelve a 160 solo si nada lo excede.

Revision ID: 0213_message_ids_fit_instagram
Revises: 0212_customer_avatar
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0213_message_ids_fit_instagram"
down_revision: str | Sequence[str] | None = "0212_customer_avatar"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = ("provider_message_id", "reaction_target_wamid", "context_message_id")


def upgrade() -> None:
    for column in _COLUMNS:
        op.alter_column("messages", column, type_=sa.String(512), existing_type=sa.String(160))


def downgrade() -> None:
    for column in _COLUMNS:
        op.alter_column("messages", column, type_=sa.String(160), existing_type=sa.String(512))
