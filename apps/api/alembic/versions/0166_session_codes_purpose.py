"""session_codes: purpose y codificación del challenge (spec 031, data-model §0159).

La tabla de las specs 009 y 012 pasa a servir a dos flujos que no se pueden
cruzar: la sesión del escritorio (``desktop_session``) y el teléfono de una
persona de cliente (``client_phone``). Un código de uno no se canjea en el otro.

``challenge_encoding`` existe porque el teléfono usa el S256 del RFC 7636
(base64url) y el escritorio guarda lo que guardaba (``hex``). Esta migración
**no cambia** el comportamiento del escritorio: todas las filas existentes y
todas las que emita siguen siendo ``desktop_session`` / ``hex``.

Revision ID: 0166_session_codes_purpose
Revises: 0165_client_phones
Create Date: 2026-10-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0166_session_codes_purpose"
down_revision: str | Sequence[str] | None = "0165_client_phones"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "session_codes",
        sa.Column("purpose", sa.String(20), nullable=False, server_default="desktop_session"),
        schema="console_auth",
    )
    op.add_column(
        "session_codes",
        sa.Column("challenge_encoding", sa.String(10), nullable=False, server_default="hex"),
        schema="console_auth",
    )
    op.create_check_constraint(
        "ck_session_codes_purpose",
        "session_codes",
        "purpose IN ('desktop_session', 'client_phone')",
        schema="console_auth",
    )
    op.create_check_constraint(
        "ck_session_codes_challenge_encoding",
        "session_codes",
        "challenge_encoding IN ('hex', 'base64url')",
        schema="console_auth",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_session_codes_challenge_encoding", "session_codes", schema="console_auth"
    )
    op.drop_constraint("ck_session_codes_purpose", "session_codes", schema="console_auth")
    op.drop_column("session_codes", "challenge_encoding", schema="console_auth")
    op.drop_column("session_codes", "purpose", schema="console_auth")
