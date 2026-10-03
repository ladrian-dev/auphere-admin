"""Spec 029: three audit sentences that read well with words, not codes.

Status values arrive translated now («activo», «suspendido»), and «cambió
test a activo» or «puso a ana@x.com en suspendido» do not read as Spanish.
The alerts row said «(tope {cap})» with a raw number or ``None``; the value
now carries its own words («tope de 1000 mensajes», «sin tope»).

Revision ID: 0139_audit_vocab_words
Revises: 0138_audit_vocab_money
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0139_audit_vocab_words"
down_revision: str | Sequence[str] | None = "0138_audit_vocab_money"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW: dict[str, tuple[str, str]] = {
    "console.client.status": (
        "{actor} cambió el estado de {client} a {status}.",
        "{actor} changed the status of {client} to {status}.",
    ),
    "console.member.status": (
        "{actor} cambió el estado de {email} a {status}.",
        "{actor} changed the status of {email} to {status}.",
    ),
    "console.usage.alerts_update": (
        "{actor} cambió las alertas de consumo ({cap}).",
        "{actor} changed the usage alerts ({cap}).",
    ),
}
OLD: dict[str, tuple[str, str]] = {
    "console.client.status": (
        "{actor} cambió {client} a {status}",
        "{actor} changed {client} to {status}",
    ),
    "console.member.status": (
        "{actor} puso a {email} en {status}",
        "{actor} set {email} to {status}",
    ),
    "console.usage.alerts_update": (
        "{actor} cambió las alertas de consumo (tope {cap})",
        "{actor} changed the usage alerts (cap {cap})",
    ),
}


def _set(texts: dict[str, tuple[str, str]]) -> None:
    for action, (es, en) in texts.items():
        op.get_bind().execute(
            sa.text(
                "UPDATE console_audit_vocabulary SET summary_es = :es, summary_en = :en "
                "WHERE action = :action"
            ),
            {"es": es, "en": en, "action": action},
        )


def upgrade() -> None:
    _set(NEW)


def downgrade() -> None:
    _set(OLD)
