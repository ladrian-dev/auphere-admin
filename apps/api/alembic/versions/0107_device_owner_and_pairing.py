"""Spec 002 — la máquina es del partner; vínculos por cliente; códigos de emparejamiento.

Enmienda el Requisito 6.3 de la 001: la credencial de dispositivo deja de ir
«acotada a su tenant» y pasa a ir acotada **al partner y a sus tenants**, con el
tenant fijado por trabajo y no por la firma. Tres cambios en el esquema:

* ``partner_devices`` cambia de dueño: gana ``partner_id`` (y ``hostname``, la
  generación de la credencial y el motivo de archivado) y pierde ``tenant_id`` y
  ``workdir``. Su RLS pasa a **dos políticas OR**: la dueña (partner + persona) y
  el gestor (partner + ``app.workstation_manager``). Sin GUC, cero filas.
* ``device_client_links`` nace: a qué clientes sirve una máquina y en qué
  directorio. Es dato de tenant (RLS por tenant, FORCE) y además **legible** por
  quien ve la máquina —a través de la RLS de ``partner_devices``, no de otra
  copia de la regla—, para que el sondeo del puente sepa qué directorios faltan.
* ``device_pairing_codes`` nace: hash del código, partner y persona que lo pidió,
  caducidad y consumo. RLS por partner, FORCE.

Las filas existentes (piloto) se llevan al partner de su tenant y su directorio
pasa a ser un vínculo. Una máquina cuyo tenant no cuelga de ningún partner no
puede tener dueño y se elimina — no hay ninguna en producción.

Revision ID: 0107_device_owner_and_pairing
Revises: 0106_local_workstation
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0107_device_owner_and_pairing"
down_revision: str | Sequence[str] | None = "0106_local_workstation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"
_PARTNER = "NULLIF(current_setting('app.partner_id', true), '')::uuid"
_PRINCIPAL = "NULLIF(current_setting('app.principal_id', true), '')"
_MANAGER = "current_setting('app.workstation_manager', true) = 'true'"

REVOKED_REASONS = ("desemparejada", "archivada_consola", "pertenencia_retirada")


def upgrade() -> None:
    # ── 1. partner_devices: el dueño cambia ────────────────────────────────
    op.add_column(
        "partner_devices",
        sa.Column(
            "partner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("partners.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.add_column(
        "partner_devices",
        sa.Column("hostname", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "partner_devices",
        sa.Column(
            "credential_generation", sa.Integer(), nullable=False, server_default=sa.text("1")
        ),
    )
    op.add_column(
        "partner_devices",
        sa.Column("credential_rotated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("partner_devices", sa.Column("revoked_reason", sa.Text(), nullable=True))
    op.create_check_constraint(
        "partner_devices_revoked_reason_check",
        "partner_devices",
        "revoked_reason IS NULL OR revoked_reason IN ("
        + ", ".join(f"'{r}'" for r in REVOKED_REASONS)
        + ")",
    )

    # Backfill: el partner de la máquina es el partner de su tenant.
    op.execute(
        """
        UPDATE partner_devices d
           SET partner_id = t.partner_id
          FROM tenants t
         WHERE t.id = d.tenant_id
        """
    )
    op.execute("DELETE FROM partner_devices WHERE partner_id IS NULL")
    op.alter_column("partner_devices", "partner_id", nullable=False)

    # ── 2. device_client_links ─────────────────────────────────────────────
    op.create_table(
        "device_client_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "device_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("partner_devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # NULL hasta que la máquina lo declare (Requisito 7). La consola no teclea rutas.
        sa.Column("workdir", sa.Text(), nullable=True),
        sa.Column("declared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "declared_by_device", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "uq_device_client_links_active",
        "device_client_links",
        ["device_id", "tenant_id"],
        unique=True,
        postgresql_where=sa.text("removed_at IS NULL"),
    )
    op.create_index("ix_device_client_links_tenant", "device_client_links", ["tenant_id"])

    # El directorio que la 001 guardaba en la máquina pasa a ser un vínculo.
    op.execute(
        """
        INSERT INTO device_client_links
            (id, tenant_id, device_id, workdir, declared_at, declared_by_device, created_by)
        SELECT gen_random_uuid(), tenant_id, id, workdir, enrolled_at, false, principal_id
          FROM partner_devices
        """
    )

    # ── 3. partner_devices pierde lo que ya no es suyo ─────────────────────
    op.execute("DROP POLICY IF EXISTS partner_devices_tenant_isolation ON partner_devices")
    op.drop_index("ix_partner_devices_tenant", table_name="partner_devices")
    op.drop_column("partner_devices", "workdir")
    op.drop_column("partner_devices", "tenant_id")
    op.create_index(
        "ix_partner_devices_partner_enrolled", "partner_devices", ["partner_id", "enrolled_at"]
    )
    op.create_index("ix_partner_devices_principal", "partner_devices", ["principal_id"])

    # ── 4. device_pairing_codes ────────────────────────────────────────────
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

    # ── 5. RLS ─────────────────────────────────────────────────────────────
    # partner_devices: dos políticas OR, ambas fail-closed. La RLS ya estaba
    # ENABLE + FORCE desde 0106; solo cambian las políticas.
    op.execute(
        f"""
        CREATE POLICY partner_devices_owner ON partner_devices
        USING (partner_id = {_PARTNER} AND principal_id = {_PRINCIPAL})
        WITH CHECK (partner_id = {_PARTNER} AND principal_id = {_PRINCIPAL})
        """
    )
    op.execute(
        f"""
        CREATE POLICY partner_devices_manager ON partner_devices
        USING (partner_id = {_PARTNER} AND {_MANAGER})
        WITH CHECK (partner_id = {_PARTNER} AND {_MANAGER})
        """
    )

    # device_client_links: dato de tenant (escribe y lee por tenant) y además
    # legible por quien ve la máquina — el sondeo del puente y la consola de
    # partner —, apoyándose en la RLS de partner_devices y no en otra copia.
    op.execute("ALTER TABLE device_client_links ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE device_client_links FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY device_client_links_tenant_isolation ON device_client_links
        USING (tenant_id = {_TENANT})
        WITH CHECK (tenant_id = {_TENANT})
        """
    )
    op.execute(
        """
        CREATE POLICY device_client_links_machine_read ON device_client_links
        FOR SELECT
        USING (device_id IN (SELECT id FROM partner_devices))
        """
    )

    op.execute("ALTER TABLE device_pairing_codes ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE device_pairing_codes FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY device_pairing_codes_partner_isolation ON device_pairing_codes
        USING (partner_id = {_PARTNER})
        WITH CHECK (partner_id = {_PARTNER})
        """
    )


def downgrade() -> None:
    # Vuelve al modelo por tenant de la 001 con los vínculos como fuente.
    op.execute(
        "DROP POLICY IF EXISTS device_pairing_codes_partner_isolation ON device_pairing_codes"
    )
    op.drop_table("device_pairing_codes")
    op.execute("DROP POLICY IF EXISTS device_client_links_machine_read ON device_client_links")
    op.execute("DROP POLICY IF EXISTS device_client_links_tenant_isolation ON device_client_links")
    op.execute("DROP POLICY IF EXISTS partner_devices_manager ON partner_devices")
    op.execute("DROP POLICY IF EXISTS partner_devices_owner ON partner_devices")

    op.add_column(
        "partner_devices",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("partner_devices", sa.Column("workdir", sa.Text(), nullable=True))
    op.execute(
        """
        UPDATE partner_devices d
           SET tenant_id = l.tenant_id, workdir = l.workdir
          FROM (
            SELECT DISTINCT ON (device_id) device_id, tenant_id, workdir
              FROM device_client_links
             WHERE removed_at IS NULL
             ORDER BY device_id, created_at
          ) l
         WHERE l.device_id = d.id
        """
    )
    op.execute("DELETE FROM partner_devices WHERE tenant_id IS NULL")
    op.execute("UPDATE partner_devices SET workdir = '' WHERE workdir IS NULL")
    op.alter_column("partner_devices", "tenant_id", nullable=False)
    op.alter_column("partner_devices", "workdir", nullable=False)
    op.create_foreign_key(
        None, "partner_devices", "tenants", ["tenant_id"], ["id"], ondelete="CASCADE"
    )
    op.drop_table("device_client_links")
    op.drop_index("ix_partner_devices_principal", table_name="partner_devices")
    op.drop_index("ix_partner_devices_partner_enrolled", table_name="partner_devices")
    op.create_index("ix_partner_devices_tenant", "partner_devices", ["tenant_id"])
    op.drop_constraint("partner_devices_revoked_reason_check", "partner_devices", type_="check")
    op.drop_column("partner_devices", "revoked_reason")
    op.drop_column("partner_devices", "credential_rotated_at")
    op.drop_column("partner_devices", "credential_generation")
    op.drop_column("partner_devices", "hostname")
    op.drop_column("partner_devices", "partner_id")
    op.execute(
        f"""
        CREATE POLICY partner_devices_tenant_isolation ON partner_devices
        USING (tenant_id = {_TENANT})
        WITH CHECK (tenant_id = {_TENANT})
        """
    )
