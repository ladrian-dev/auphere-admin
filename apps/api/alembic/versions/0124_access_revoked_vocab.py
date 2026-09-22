"""Spec 012 — «se retiró el acceso de una persona» entra en el vocabulario.

Un acto nuevo de la auditoría necesita su frase, o la consola lo pinta con el
fallback crudo: ``actor · principal.access_revoked · principal:<uuid>``. No
miente, pero tampoco se entiende, y éste es justo el asiento que alguien va a
leer con prisa el día que pregunte «¿quién echó a quién?».

**Por qué esta migración existe y el plan decía que no habría ninguna hasta el
final.** El plan se equivocó, y conviene que quede escrito en vez de corregido
en silencio: dio por hecho que R1 no tocaba esquema porque ``revoked_at`` y el
motivo ya existían. Lo que no miró es que este repositorio tiene un **vocabulario
de auditoría sembrado por migración** —el comentario de ``api/console/support.py``
ya avisaba: «un valor nuevo obliga a tocar los dos sitios»—. Así que la spec 012
tiene dos migraciones: ésta, aditiva y con US1, y la del final, destructiva, que
retira la tabla de códigos.

Revision ID: 0124_access_revoked_vocab
Revises: 0123_local_execution_cwd
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0124_access_revoked_vocab"
down_revision: str | Sequence[str] | None = "0123_local_execution_cwd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTION = "principal.access_revoked"
CATEGORY = "team"
#: ``warning`` y no ``info``: no es una preferencia que alguien cambió, es una
#: persona que se quedó fuera. Quien repasa la auditoría tiene que verlo.
SEVERITY = "warning"
SUMMARY_ES = "{actor} retiró el acceso de una persona: sus sesiones y sus máquinas."
SUMMARY_EN = "{actor} revoked a person's access: their sessions and their machines."


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO console_audit_vocabulary
                (action, category, severity, summary_es, summary_en)
            SELECT
                CAST(:action AS VARCHAR(80)),
                CAST(:category AS VARCHAR(40)),
                CAST(:severity AS VARCHAR(10)),
                CAST(:summary_es AS TEXT),
                CAST(:summary_en AS TEXT)
            WHERE NOT EXISTS (
                SELECT 1 FROM console_audit_vocabulary
                WHERE action = CAST(:action AS VARCHAR(80))
            )
            """
        ),
        {
            "action": ACTION,
            "category": CATEGORY,
            "severity": SEVERITY,
            "summary_es": SUMMARY_ES,
            "summary_en": SUMMARY_EN,
        },
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text("DELETE FROM console_audit_vocabulary WHERE action = :action"),
        {"action": ACTION},
    )
