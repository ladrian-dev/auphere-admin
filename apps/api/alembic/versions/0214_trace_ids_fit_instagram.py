"""QA canales Meta 2026-10-31: el identificador de una respuesta por Instagram cabe.

Tras 0213, la primera respuesta de Ava por Instagram salió, pero el despachador
no pudo marcarla como enviada: guarda el ``mid`` (unos 230 caracteres) también
en ``messages.trace_id``, que era ``varchar(120)``. La transacción se deshacía,
el mensaje seguía pendiente y se volvía a mandar cada 30 segundos.

Pasan a 512 ``messages.trace_id`` y ``whatsapp_opt_outs.source_wamid`` (el
mensaje con el que alguien se dio de baja, que también puede venir de
Instagram o Messenger). Ensanchar un ``varchar`` no reescribe la tabla ni su
índice.

Revision ID: 0214_trace_ids_fit_instagram
Revises: 0213_message_ids_fit_instagram
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0214_trace_ids_fit_instagram"
down_revision: str | Sequence[str] | None = "0213_message_ids_fit_instagram"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = (("messages", "trace_id", 120), ("whatsapp_opt_outs", "source_wamid", 160))


def upgrade() -> None:
    for table, column, before in _COLUMNS:
        op.alter_column(table, column, type_=sa.String(512), existing_type=sa.String(before))


def downgrade() -> None:
    for table, column, before in _COLUMNS:
        op.alter_column(table, column, type_=sa.String(before), existing_type=sa.String(512))
