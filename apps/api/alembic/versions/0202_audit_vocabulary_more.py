"""Las frases que faltaban en el vocabulario de Auditoría — spec 047 (requisito
49.1): el catálogo de modelos (precios, rechazos y cambios de un despliegue), las
fuentes de la ficha y la beta de «Iniciar sesión con WhatsApp». Sin ellas, la
fila se leía como código (``test_console_audit_words``).

Revision ID: 0202_audit_vocabulary_more
Revises: 0201_console_v2_reports
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0202_audit_vocabulary_more"
down_revision: str | Sequence[str] | None = "0201_console_v2_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (acción, categoría, gravedad, español, inglés)
ROWS: tuple[tuple[str, str, str, str, str], ...] = (
    # Operador: el catálogo de modelos
    ("deployment.updated", "admin", "info",
     "Auphere cambió un modelo del catálogo.", "Auphere changed a model of the catalog."),
    ("deployment.rejected", "admin", "info",
     "Auphere rechazó un modelo propuesto para el catálogo.",
     "Auphere rejected a model proposed for the catalog."),
    ("deployment.price_added", "admin", "info",
     "Auphere anotó un precio nuevo de un modelo del catálogo.",
     "Auphere recorded a new price for a model of the catalog."),
    ("deployment.price_applied", "admin", "info",
     "Entró en vigor un precio nuevo de un modelo del catálogo.",
     "A new price for a model of the catalog came into effect."),
    # Operador: la beta de «Iniciar sesión con WhatsApp», por país
    ("whatsapp.login_beta.enabled", "admin", "info",
     "Auphere abrió la beta de «Iniciar sesión con WhatsApp» en un país.",
     "Auphere opened the «Sign in with WhatsApp» beta in a country."),
    ("whatsapp.login_beta.disabled", "admin", "info",
     "Auphere cerró la beta de «Iniciar sesión con WhatsApp» en un país.",
     "Auphere closed the «Sign in with WhatsApp» beta in a country."),
    # Negocio: las fuentes de la ficha
    ("source.added", "business", "info",
     "{actor} añadió una fuente a la ficha de {client}.",
     "{actor} added a source to the business profile of {client}."),
    ("source.removed", "business", "info",
     "{actor} quitó una fuente de la ficha de {client}.",
     "{actor} removed a source from the business profile of {client}."),
    ("source.reread", "business", "info",
     "Se volvió a leer una fuente de la ficha de {client}.",
     "A source of the business profile of {client} was read again."),
)  # fmt: skip


def upgrade() -> None:
    vocabulary = sa.table(
        "console_audit_vocabulary",
        sa.column("action", sa.String),
        sa.column("category", sa.String),
        sa.column("severity", sa.String),
        sa.column("summary_es", sa.Text),
        sa.column("summary_en", sa.Text),
    )
    for action, category, severity, es, en in ROWS:
        op.execute(
            sa.dialects.postgresql.insert(vocabulary)
            .values(
                action=action, category=category, severity=severity, summary_es=es, summary_en=en
            )
            .on_conflict_do_nothing(index_elements=["action"])
        )


def downgrade() -> None:
    actions = ", ".join(f"'{row[0]}'" for row in ROWS)
    op.execute(f"DELETE FROM console_audit_vocabulary WHERE action IN ({actions})")
