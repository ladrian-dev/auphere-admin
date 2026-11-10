"""Spec 049 y QA 2026-10-30: la foto de quien escribe por Instagram o Messenger.

Decisión del owner (2026-10-30): la bandeja enseña el nombre **y la foto** de
quien escribe (función «Business Asset User Profile Access» de Meta). Meta da
la foto como un enlace a su CDN que caduca, así que el worker la copia a
nuestro almacenamiento y aquí solo se guarda la clave. Nula hasta entonces y
en WhatsApp, que no da foto. Se borra con los demás datos de la persona.

``customers`` ya está bajo RLS por ``tenant_id``: la columna nueva hereda la
política.

Revision ID: 0212_customer_avatar
Revises: 0211_audit_words_meta_fixes
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0212_customer_avatar"
down_revision: str | Sequence[str] | None = "0211_audit_words_meta_fixes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("avatar_s3_key", sa.String(512), nullable=True))


def downgrade() -> None:
    op.drop_column("customers", "avatar_s3_key")
