"""Spec 002 — vocabulario de auditoría de la identidad de una máquina (Requisito 13).

Siete actos. El actor es la persona salvo en la renovación, que la firma la máquina.

Revision ID: 0108_device_audit_vocab
Revises: 0107_device_owner_and_pairing
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0108_device_audit_vocab"
down_revision: str | Sequence[str] | None = "0107_device_owner_and_pairing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROWS = (
    (
        "device.pair_code_issued",
        "workstation",
        "info",
        "{actor} pidió un código para emparejar una máquina.",
        "{actor} requested a code to pair a machine.",
    ),
    (
        "device.paired",
        "workstation",
        "info",
        "{actor} emparejó la máquina {machine}.",
        "{actor} paired the machine {machine}.",
    ),
    (
        "device.pair_denied",
        "workstation",
        "warning",
        "Un intento de emparejar una máquina fue denegado ({reason}).",
        "An attempt to pair a machine was denied ({reason}).",
    ),
    (
        "device.renewed",
        "workstation",
        "info",
        "La máquina {machine} renovó su credencial.",
        "The machine {machine} renewed its credential.",
    ),
    (
        "device.link_declared",
        "workstation",
        "info",
        "La máquina {machine} declaró el directorio de {client}.",
        "The machine {machine} declared the directory for {client}.",
    ),
    (
        "device.link_denied",
        "workstation",
        "warning",
        "La máquina {machine} intentó declarar un cliente que no es de este partner.",
        "The machine {machine} tried to declare a client that is not this partner's.",
    ),
    (
        "device.unpaired",
        "workstation",
        "info",
        "{actor} desemparejó la máquina {machine}.",
        "{actor} unpaired the machine {machine}.",
    ),
    (
        "device.archived",
        "workstation",
        "info",
        "{actor} archivó la máquina {machine} ({reason}).",
        "{actor} archived the machine {machine} ({reason}).",
    ),
)


def upgrade() -> None:
    bind = op.get_bind()
    for action, category, severity, summary_es, summary_en in ROWS:
        bind.execute(
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
                "action": action,
                "category": category,
                "severity": severity,
                "summary_es": summary_es,
                "summary_en": summary_en,
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    for action, *_ in ROWS:
        bind.execute(
            sa.text("DELETE FROM console_audit_vocabulary WHERE action = :action"),
            {"action": action},
        )
