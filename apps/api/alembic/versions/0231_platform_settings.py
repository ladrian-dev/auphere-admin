"""Los ajustes de la plataforma y el estado previo de un modelo «No disponible».

Spec 059 (T001, requisitos 1.7 y 3.6):

- ``platform_settings``: ajustes de Auphere sin cliente, clave → valor JSON. El
  primero es ``sale_multiplier``, el múltiplo del coste con el que se proponen y se
  comprueban los pesos de venta de cada modelo. Hasta hoy era la constante
  ``QUOTA_TARGET_MULTIPLIER`` (2,2, spec 007); desde aquí lo cambia Auphere desde el
  panel. El suelo (1,5) sigue siendo una constante del código: no es un ajuste. Sin
  RLS, como ``model_profiles``: es un dato de plataforma, no de un cliente.
- ``model_profiles.status_before_unavailable``: el estado que tenía un modelo al
  marcarlo «No disponible», para que «Volver a disponible» lo devuelva ahí sin pasar
  por la puerta de activación.
- Las frases de ``console_audit_vocabulary`` de las cinco acciones nuevas de la
  auditoría de plataforma (``tests/unit/test_console_audit_words.py``).

Revision ID: 0231_platform_settings
Revises: 0230_audit_words_agenda
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0231_platform_settings"
down_revision: str | Sequence[str] | None = "0230_audit_words_agenda"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Los estados de ``model_profiles`` (0180). Un modelo «No disponible» vuelve a uno
#: de estos, nunca a ``unavailable``.
_RESTORABLE = ("draft", "certifying", "active", "retiring", "retired", "deprecated")

VOCABULARY: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "deployment.retirement_cancelled",
        "admin",
        "info",
        "Auphere canceló la retirada de un modelo del catálogo.",
        "Auphere cancelled the retirement of a model of the catalog.",
    ),
    (
        "deployment.restored",
        "admin",
        "info",
        "Un modelo del catálogo volvió a estar disponible.",
        "A model of the catalog became available again.",
    ),
    (
        "deployment.retirement_blocked",
        "admin",
        "warning",
        "La retirada de un modelo se detuvo: aún hay agentes que responden con él.",
        "A model's retirement was held: some agents still answer with it.",
    ),
    (
        "deployment.weights_changed",
        "admin",
        "info",
        "Auphere cambió el precio de venta de un modelo del catálogo.",
        "Auphere changed the sale price of a model of the catalog.",
    ),
    (
        "platform.sale_multiplier_changed",
        "admin",
        "info",
        "Auphere cambió el multiplicador de venta de la plataforma.",
        "Auphere changed the platform's sale multiplier.",
    ),
)


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE platform_settings (
            key text PRIMARY KEY,
            value jsonb NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            updated_by text
        )
        """
    )
    op.execute(
        "INSERT INTO platform_settings (key, value, updated_by) "
        "VALUES ('sale_multiplier', '2.2'::jsonb, 'migration:0231')"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON platform_settings TO nexus_app")

    values = ", ".join(f"'{s}'" for s in _RESTORABLE)
    op.execute("ALTER TABLE model_profiles ADD COLUMN status_before_unavailable text")
    op.execute(
        "ALTER TABLE model_profiles ADD CONSTRAINT model_profiles_status_before_unavailable_check "
        f"CHECK (status_before_unavailable IS NULL OR status_before_unavailable IN ({values}))"
    )

    bind = op.get_bind()
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
    op.execute(
        "ALTER TABLE model_profiles DROP CONSTRAINT IF EXISTS "
        "model_profiles_status_before_unavailable_check"
    )
    op.execute("ALTER TABLE model_profiles DROP COLUMN IF EXISTS status_before_unavailable")
    op.execute("DROP TABLE IF EXISTS platform_settings")
