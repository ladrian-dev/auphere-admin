"""qa.* operator_id: UUID → TEXT (ADR-020, Fase 6 follow-up).

Revision ID: 0026
Revises: 0025
Create Date: 2026-05-19

The operator identity in the QA Playground comes straight from Better
Auth's ``session.user.id``. Better Auth emits short, opaque ids (cuid-
style, e.g. ``7WW859bXO3U5lUEseogGUA9NNwddHgzy``) — not UUIDs. The
``apps/admin`` BFF proxy forwards that id verbatim in the
``X-Operator-Id`` header, but migration 0025 typed ``operator_id`` as
``uuid`` and the dependency parsed it with ``uuid.UUID(...)``, so every
real request from the Playground UI bounced with HTTP 400.

This migration:

  1. Drops the policies that cast the GUC to ``::uuid``.
  2. Alters the three ``qa.*.operator_id`` columns from UUID → TEXT.
  3. Recreates the policies WITHOUT the cast — pure string equality.

Why text + opaque id is safe:

  - Defense layer 1: Bearer ``NEXUS_ADMIN_TOKEN`` already gates origin
    to Auphere staff. The ``X-Operator-Id`` field identifies the actor,
    not the authorisation.
  - Defense layer 2: RLS by string equality is identical in behaviour to
    by-UUID equality — the GUC ``app.operator_id`` is a string everywhere,
    Postgres ``current_setting`` returns text, and the policy compares
    text to text. The ``::uuid`` cast added a syntactic gate, not a
    security gate.
  - Defense layer 3: ``WITH CHECK`` still enforces that an INSERT with a
    foreign operator id is rejected. The forged-INSERT isolation test
    (test_8) keeps passing because the comparison is symmetric.

When Block G (real Better Auth → operators mapping) lands, this stays:
either we keep storing the BA id directly, or we add a lookup layer in
front. Schema doesn't change.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0026"
down_revision: str | Sequence[str] | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


QA_TABLES: tuple[str, ...] = (
    "threads",
    "side_effect_audit",
    "audit_log",
)


def upgrade() -> None:
    # Drop the existing policies before changing the column type — Postgres
    # won't ALTER a column referenced by a policy expression.
    for table in QA_TABLES:
        op.execute(f"DROP POLICY IF EXISTS qa_{table}_operator_isolation ON qa.{table}")

    # Change the column type. ``USING operator_id::text`` is the explicit
    # conversion expression Postgres needs when narrowing a uuid into text;
    # the existing rows (if any survived a test reset) carry their canonical
    # 36-char representation.
    for table in QA_TABLES:
        op.execute(
            f"ALTER TABLE qa.{table} "
            f"ALTER COLUMN operator_id TYPE text USING operator_id::text"
        )

    # Recreate the policies, this time comparing text to text. The
    # NULLIF guard still fails closed: ``current_setting('app.operator_id',
    # true)`` returns '' when the GUC is unset; NULLIF makes that NULL,
    # and ``operator_id = NULL`` is unknown → policy denies.
    for table in QA_TABLES:
        op.execute(
            f"""
            CREATE POLICY qa_{table}_operator_isolation ON qa.{table}
            USING (
                operator_id = NULLIF(current_setting('app.operator_id', true), '')
            )
            WITH CHECK (
                operator_id = NULLIF(current_setting('app.operator_id', true), '')
            )
            """
        )


def downgrade() -> None:
    # Revert to UUID. Any rows whose operator_id is not a valid UUID string
    # would fail the cast — callers that relied on the looser TEXT shape
    # need to clean up first. The downgrade exists for symmetry; in
    # practice the type widening is one-way.
    for table in QA_TABLES:
        op.execute(f"DROP POLICY IF EXISTS qa_{table}_operator_isolation ON qa.{table}")

    for table in QA_TABLES:
        op.execute(
            f"ALTER TABLE qa.{table} "
            f"ALTER COLUMN operator_id TYPE uuid USING operator_id::uuid"
        )

    for table in QA_TABLES:
        op.execute(
            f"""
            CREATE POLICY qa_{table}_operator_isolation ON qa.{table}
            USING (
                operator_id = NULLIF(current_setting('app.operator_id', true), '')::uuid
            )
            WITH CHECK (
                operator_id = NULLIF(current_setting('app.operator_id', true), '')::uuid
            )
            """
        )
