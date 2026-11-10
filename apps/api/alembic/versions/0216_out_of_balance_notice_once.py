"""«Sin saldo» se dice una sola vez (spec 047, enmienda de 44.5; owner, 2026-11-03).

Las claves de ``client.out_of_quota`` y ``client.balance_out`` dejan de llevar
fecha. El último aviso de cada cliente pasa a la clave sin fecha para que el
despliegue no mande otra tanda a quien ya lo sabe; a quien ya recuperó saldo, el
primer tick del cron le suelta la clave.

Revision ID: 0216_out_of_balance_notice_once
Revises: 0215_inbox_clear_archive_vocab
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0216_out_of_balance_notice_once"
down_revision: str | Sequence[str] | None = "0215_inbox_clear_archive_vocab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CARRY_LATEST_NOTICE = r"""
UPDATE console_notifications AS notice
SET dedupe_key = regexp_replace(notice.dedupe_key, ':\d{4}-\d{2}-\d{2}$', '')
FROM (
    SELECT DISTINCT ON (regexp_replace(dedupe_key, ':\d{4}-\d{2}-\d{2}$', '')) id
    FROM console_notifications
    WHERE kind IN ('client.out_of_quota', 'client.balance_out')
      AND dedupe_key ~ ':\d{4}-\d{2}-\d{2}$'
    ORDER BY regexp_replace(dedupe_key, ':\d{4}-\d{2}-\d{2}$', ''), created_at DESC
) AS latest
WHERE notice.id = latest.id
"""


def upgrade() -> None:
    op.execute(CARRY_LATEST_NOTICE)


def downgrade() -> None:
    # Las claves con fecha son de ayer: volver atrás solo permite un aviso más.
    pass
