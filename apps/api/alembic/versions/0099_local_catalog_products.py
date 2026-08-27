"""local_catalog_products — catálogo importado de una hoja de cálculo

Revision ID: 0099_local_catalog_products
Revises: 0098_amigable_venta_tools
Create Date: 2026-08-25

Un catálogo de productos que vive en Nexus en vez de en un POS externo. Lo
consume el backend ``catalogo_local`` de las tools ``inventory.*`` cuando el
tenant no tiene el connector de Amigable Venta conectado.

FORCE RLS por ``app.tenant_id``, igual que el resto de tablas por tenant.

Dos decisiones que se ven en el esquema:

- **No hay columna de costo.** El catálogo de origen lo trae, pero el precio
  de costo es justo el dato que nunca debe llegar a un turno del agente. No
  guardarlo es más barato que acordarse de filtrarlo.
- **``search_text`` está desnormalizado a propósito.** Guarda el nombre y el
  SKU ya plegados (minúsculas, sin tildes) para que la búsqueda sea un LIKE
  plano y no dependa de la extensión ``unaccent``. El importador es el único
  que lo escribe, y su plegado debe coincidir con ``catalogo_local.fold``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0099_local_catalog_products"
down_revision: str | Sequence[str] | None = "0098_amigable_venta_tools"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "local_catalog_products"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sku", sa.Text(), nullable=False),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("categoria", sa.Text(), nullable=True),
        sa.Column("tipo", sa.Text(), nullable=True),
        sa.Column("precio_usd", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("stock_actual", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stock_minimo", sa.Integer(), nullable=False, server_default="0"),
        # Nombre + SKU plegados. Lo escribe solo el importador.
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("tenant_id", "sku", name="uq_local_catalog_tenant_sku"),
    )
    op.create_index(
        "ix_local_catalog_tenant_search", _TABLE, ["tenant_id", "search_text"]
    )

    op.execute(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY {_TABLE}_tenant_isolation ON {_TABLE}
        USING (tenant_id = (NULLIF(current_setting('app.tenant_id', true), ''))::uuid)
        """
    )


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS {_TABLE}_tenant_isolation ON {_TABLE}")
    op.drop_index("ix_local_catalog_tenant_search", table_name=_TABLE)
    op.drop_table(_TABLE)
