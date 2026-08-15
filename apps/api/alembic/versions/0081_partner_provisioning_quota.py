"""Cuota de aprovisionamiento por partner — ``max_clients``,
``max_channels_per_client``, ``quota_notes``.

PLAN-CONSOLE-V1, CP-06. Hoy una clave de partner (y mañana la consola)
puede crear clientes sin techo. Mientras aprovisiona el equipo de Auphere
a mano es una deuda; en el momento en que el partner se autoabastece es
una vía de pérdida: cada cliente arrastra coste real (LLM, Meta, media) y
nadie ha acordado quién lo paga.

- ``max_clients``: cuántos clientes (filas en ``partner_tenants`` cuyo
  tenant no está archivado) puede tener el partner. Se comprueba **antes**
  de crear nada, con la fila del partner bloqueada (``FOR UPDATE``) para
  que dos altas concurrentes no la salten. El cliente ``max_clients + 1``
  recibe un 409 con la cifra y qué hacer.
- ``max_channels_per_client``: techo de canales por cliente. La columna
  nace aquí; el punto de aplicación es la conexión de canal (CP-17), que
  es donde se crea el canal.
- ``quota_notes``: texto libre para el operador ("ampliado a 30 el
  2026-09-01 por contrato X"). No se enseña al partner.

**Siembra**: los partners que ya existen reciben ``max_clients`` igual a
su número real de clientes +50 % (redondeado arriba), con un suelo de 5.
El plan lo pide para Facelad y Amacrux; se hace para todos con la misma
regla porque el número real está en la tabla y una lista de slugs en una
migración es lo que se olvida actualizar. Los partners nuevos nacen con el
default conservador (5) y Auphere lo sube desde el backoffice.

Revision ID: 0081_partner_provisioning_quota
Revises: 0080_console_principals
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0081_partner_provisioning_quota"
down_revision: str | Sequence[str] | None = "0080_console_principals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_MAX_CLIENTS = 5
DEFAULT_MAX_CHANNELS_PER_CLIENT = 2


def upgrade() -> None:
    op.execute(
        "ALTER TABLE partners "
        f"ADD COLUMN max_clients integer NOT NULL DEFAULT {DEFAULT_MAX_CLIENTS}, "
        "ADD COLUMN max_channels_per_client integer NOT NULL "
        f"DEFAULT {DEFAULT_MAX_CHANNELS_PER_CLIENT}, "
        "ADD COLUMN quota_notes text NULL"
    )
    op.execute(
        "ALTER TABLE partners ADD CONSTRAINT ck_partners_max_clients CHECK (max_clients >= 0)"
    )
    op.execute(
        "ALTER TABLE partners ADD CONSTRAINT ck_partners_max_channels_per_client "
        "CHECK (max_channels_per_client >= 0)"
    )
    # Siembra: real +50 %, suelo 5. Solo sube, nunca baja: un partner con
    # 0 clientes se queda en el default.
    op.execute(
        f"""
        UPDATE partners p
           SET max_clients = GREATEST({DEFAULT_MAX_CLIENTS}, CEIL(c.n * 1.5)::int),
               quota_notes = 'seed 0081: real ' || c.n || ' +50%'
          FROM (
                SELECT pt.partner_id, count(*) AS n
                  FROM partner_tenants pt
                  JOIN tenants t ON t.id = pt.tenant_id
                 WHERE t.status <> 'archived'
                 GROUP BY pt.partner_id
               ) c
         WHERE c.partner_id = p.id
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE partners DROP CONSTRAINT IF EXISTS ck_partners_max_channels_per_client")
    op.execute("ALTER TABLE partners DROP CONSTRAINT IF EXISTS ck_partners_max_clients")
    op.execute(
        "ALTER TABLE partners "
        "DROP COLUMN IF EXISTS quota_notes, "
        "DROP COLUMN IF EXISTS max_channels_per_client, "
        "DROP COLUMN IF EXISTS max_clients"
    )
