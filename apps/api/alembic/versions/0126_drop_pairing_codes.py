"""Spec 012 — se retira la tabla del código de emparejamiento (R6.3).

**La única migración destructiva de la spec, y va la última a propósito**:
cuando ya nadie escribe en esa tabla porque el registro por sesión está
entregado y rodado. Al revés dejaría a la gente sin ningún camino.

Con ella desaparece **el único secreto de registro que quedaba en reposo**. El
código se guardaba hasheado, que estaba bien; ahora no hay nada que guardar,
que está mejor — R7.4 pasa de ser una promesa a ser cierta por construcción.

**El `downgrade` recrea la tabla vacía, con su índice y su política.** No
restaura códigos, y eso es deliberado: eran secretos de diez minutos, y bajar
una versión no debe resucitar credenciales. Lo que sí restaura es **la forma**,
para que bajar no deje el esquema roto — y la política de RLS con ella, porque
una tabla con `partner_id` y sin política es exactamente lo que el censo de
`test_21` existe para impedir.

Revision ID: 0126_drop_pairing_codes
Revises: 0125_device_install_id
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0126_drop_pairing_codes"
down_revision: str | Sequence[str] | None = "0125_device_install_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: El mismo GUC que usa el resto del puesto de trabajo.
_PARTNER = "current_setting('app.partner_id', true)::uuid"


def upgrade() -> None:
    # La política cae con la tabla, pero se nombra para que el `DROP` no
    # dependa de un efecto colateral.
    op.execute(
        "DROP POLICY IF EXISTS device_pairing_codes_partner_isolation ON device_pairing_codes"
    )
    op.execute("DROP INDEX IF EXISTS ix_device_pairing_codes_partner")
    op.drop_table("device_pairing_codes")


def downgrade() -> None:
    op.create_table(
        "device_pairing_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "partner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("partners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("principal_id", sa.Text(), nullable=False),
        # sha256 del código normalizado. Nunca el código.
        sa.Column("code_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "consumed_device_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("partner_devices.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_device_pairing_codes_partner", "device_pairing_codes", ["partner_id"])
    op.execute("ALTER TABLE device_pairing_codes ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE device_pairing_codes FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY device_pairing_codes_partner_isolation ON device_pairing_codes
        USING (partner_id = {_PARTNER})
        WITH CHECK (partner_id = {_PARTNER})
        """
    )
