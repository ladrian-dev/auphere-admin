"""La auditoría del acceso del cliente dice quién lo cambió — spec 056, T004 (requisitos 3.8, 1.5 y 9.2).

- Las frases de ``client_access.updated``, ``client_member.invited``,
  ``client_member.resent`` y ``client_member.revoked`` (0148) decían «Auphere…»
  a fuego, porque solo las escribía el panel. Desde esta spec el partner también
  cambia el acceso de su cliente, así que pasan a «{actor}…». ``_human_actor``
  (``api/console/audit.py``) sigue pintando «Auphere» para ``operator:`` y para
  lo que hace la plataforma sola, y el correo para ``console:``.
- Siembra las acciones nuevas:
  - ``agent.booking_brake``: el freno de citas actuó (lo escribe el worker,
    ``system:worker``, sin el texto del mensaje);
  - ``correction.batch_accepted`` y ``correction.batch_discarded``: el partner
    acepta o descarta de una vez la corrección de «Todo el negocio».

La bajada devuelve las cuatro frases de la 0148 y borra las tres nuevas.

Revision ID: 0225_client_access_audit_actor
Revises: 0224_client_modules_retire
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0225_client_access_audit_actor"
down_revision: str | Sequence[str] | None = "0224_client_modules_retire"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (acción, español de la 0148, inglés de la 0148, español, inglés)
REWORDED: tuple[tuple[str, str, str, str, str], ...] = (
    ("client_access.updated",
     "Auphere cambió el acceso de {client} a su consola.",
     "Auphere changed {client}'s access to its console.",
     "{actor} cambió el acceso de {client} a su consola.",
     "{actor} changed {client}'s access to its console."),
    ("client_member.invited",
     "Auphere invitó a una persona de {client} a su consola.",
     "Auphere invited a person from {client} to its console.",
     "{actor} invitó a una persona de {client} a su consola.",
     "{actor} invited a person from {client} to its console."),
    ("client_member.resent",
     "Auphere reenvió una invitación de {client}.",
     "Auphere resent an invitation for {client}.",
     "{actor} reenvió una invitación de {client}.",
     "{actor} resent an invitation for {client}."),
    ("client_member.revoked",
     "Auphere retiró el acceso de una persona de {client}.",
     "Auphere removed a person's access for {client}.",
     "{actor} retiró el acceso de una persona de {client}.",
     "{actor} removed a person's access for {client}."),
)  # fmt: skip

#: (acción, categoría, gravedad, español, inglés)
VOCABULARY: tuple[tuple[str, str, str, str, str], ...] = (
    ("agent.booking_brake", "agents", "warning",
     "El freno de citas actuó en una conversación de {client}.",
     "The booking brake stepped in on a conversation of {client}."),
    ("correction.batch_accepted", "improvement", "info",
     "{actor} aceptó una corrección de {client} en varios agentes a la vez.",
     "{actor} accepted a correction from {client} on several agents at once."),
    ("correction.batch_discarded", "improvement", "info",
     "{actor} descartó una corrección de {client} en varios agentes a la vez.",
     "{actor} discarded a correction from {client} on several agents at once."),
)  # fmt: skip

_REWORD = sa.text(
    "UPDATE console_audit_vocabulary SET summary_es = :es, summary_en = :en WHERE action = :a"
)


def upgrade() -> None:
    bind = op.get_bind()
    for action, _old_es, _old_en, es, en in REWORDED:
        bind.execute(_REWORD, {"a": action, "es": es, "en": en})
    for action, category, severity, es, en in VOCABULARY:
        bind.execute(
            sa.text(
                """
                INSERT INTO console_audit_vocabulary
                    (action, category, severity, summary_es, summary_en)
                SELECT CAST(:a AS VARCHAR(80)), CAST(:c AS VARCHAR(40)),
                       CAST(:s AS VARCHAR(10)), CAST(:es AS TEXT), CAST(:en AS TEXT)
                WHERE NOT EXISTS (
                    SELECT 1 FROM console_audit_vocabulary WHERE action = CAST(:a AS VARCHAR(80))
                )
                """
            ),
            {"a": action, "c": category, "s": severity, "es": es, "en": en},
        )


def downgrade() -> None:
    bind = op.get_bind()
    for action, *_ in VOCABULARY:
        bind.execute(
            sa.text("DELETE FROM console_audit_vocabulary WHERE action = :a"), {"a": action}
        )
    for action, old_es, old_en, _es, _en in REWORDED:
        bind.execute(_REWORD, {"a": action, "es": old_es, "en": old_en})
