"""Spec 065 (T002; requisitos 2.1, 2.6, 10.1): el modelo que elige cada agente.

Tres columnas en ``agents``: el perfil de modelo elegido para responder, quién lo eligió
(``partner`` u ``operator``) y cuándo. Nulo = el agente sigue el modelo por defecto de
Auphere. Una elección siempre dice quién la hizo (``CHECK``). La RLS forzada de ``agents``
(0152) cubre las columnas nuevas; la FK apunta a ``model_profiles``, tabla de plataforma sin
cliente, así que no necesita clave compuesta. ``ON DELETE RESTRICT``: un perfil elegido por
un agente no se borra; retirarlo pasa por las guardas de la spec 059.

Y las frases de auditoría de las acciones nuevas de la spec, para que la consola no las
enseñe en crudo (``test_console_audit_words``).

Revision ID: 0237_agent_respond_model
Revises: 0236_context_cut_and_autoclose
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "0237_agent_respond_model"
down_revision: str | Sequence[str] | None = "0236_context_cut_and_autoclose"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VOCABULARY: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "console.agent.model.update",
        "agents",
        "info",
        "{actor} cambió el modelo de un agente de {client} a {model}.",
        "{actor} changed the model of an agent of {client} to {model}.",
    ),
    (
        "admin.agent.model.update",
        "agents",
        "info",
        "Auphere cambió el modelo de un agente de {client} a {model}.",
        "Auphere changed the model of an agent of {client} to {model}.",
    ),
    (
        "admin.model.respond_enable",
        "admin",
        "info",
        "Auphere habilitó un modelo para responder.",
        "Auphere enabled a model to answer.",
    ),
    (
        "admin.model.respond_disable",
        "admin",
        "info",
        "Auphere dejó de ofrecer un modelo para responder.",
        "Auphere stopped offering a model to answer.",
    ),
    (
        "admin.platform.agent_respond_default",
        "admin",
        "info",
        "Auphere cambió el modelo por defecto de los agentes.",
        "Auphere changed the agents' default model.",
    ),
    (
        "model.respond_binding.migrated",
        "agents",
        "info",
        "El modelo de {client} pasó a cada uno de sus agentes.",
        "{client}'s model moved to each of its agents.",
    ),
)


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "respond_model_profile_id",
            UUID(as_uuid=True),
            sa.ForeignKey("model_profiles.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.add_column("agents", sa.Column("respond_model_set_by", sa.Text(), nullable=True))
    op.add_column(
        "agents", sa.Column("respond_model_set_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_check_constraint(
        "ck_agents_respond_model_set_by",
        "agents",
        "respond_model_set_by IS NULL OR respond_model_set_by IN ('partner', 'operator')",
    )
    op.create_check_constraint(
        "ck_agents_respond_model_has_author",
        "agents",
        "(respond_model_profile_id IS NULL) = (respond_model_set_by IS NULL)",
    )
    op.create_index(
        "ix_agents_respond_model_profile_id",
        "agents",
        ["respond_model_profile_id"],
        postgresql_where=sa.text("respond_model_profile_id IS NOT NULL"),
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
    op.drop_index("ix_agents_respond_model_profile_id", table_name="agents")
    op.drop_constraint("ck_agents_respond_model_has_author", "agents", type_="check")
    op.drop_constraint("ck_agents_respond_model_set_by", "agents", type_="check")
    op.drop_column("agents", "respond_model_set_at")
    op.drop_column("agents", "respond_model_set_by")
    op.drop_column("agents", "respond_model_profile_id")
