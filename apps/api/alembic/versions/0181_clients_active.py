"""Los clientes en ``provisioning`` pasan a ``active`` — spec 047, T046 (requisito 4.7).

El ciclo de vida del cliente (activo, en pausa o archivado) se separa de su
preparación (si tiene o no agentes atendiendo): un cliente sin agentes está
activo y no queda en un «preparando» que dependa de tener agente y canal
(``services/tenant_lifecycle.py``, research D2).

**Su paso no hace contestar a nadie que hoy no contesta.** El dispatcher calla a
un cliente en ``provisioning`` (``_INACTIVE_STATUSES``); a uno ``active`` lo hace
responder si tiene una versión publicada (``agent_configs.status = 'active'``) y
le llega un mensaje. Por eso pasa **solo quien no tiene ninguna versión
publicada**: ese no responde ni hoy ni después de la migración, tenga número o
no, porque el turno se queda en ``no_agent`` o ``agent_unpublished``. Quien sí la
tiene se queda como está: es el «esperando activación» de la API de partners
(``activation_blocked_reason``, ``docs/partner-integration.md``), que se activa
por su camino de hoy (``activate_tenant_if_ready``) y cuyo contrato no cambia.

El estado se compara como texto: desde una base vacía, todas las migraciones
corren en una sola transacción y Postgres no deja **usar** un valor de enum
añadido en ella (``provisioning`` llega en la 0047); leerlo como texto, sí.

Cada cliente que pasa deja su fila de auditoría (§IV), con la acción y las
palabras que ya existen (``console.client.status``: «{actor} cambió {client} a
{status}») y el actor ``system:0181_clients_active``. Es también lo que hace
reversible la migración: bajar devuelve a ``provisioning`` justo a esos —si
siguen activos: a uno que alguien pausó o archivó después no se le toca— y
borra sus filas. Solo escribe donde hay algo que cambiar: repetirla no cambia
nada.

Revision ID: 0181_clients_active
Revises: 0180_model_catalog_and_router
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0181_clients_active"
down_revision: str | Sequence[str] | None = "0180_model_catalog_and_router"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTOR = "system:0181_clients_active"
ACTION = "console.client.status"

UPGRADE = f"""
WITH moved AS (
    UPDATE tenants AS t
       SET status = 'active', updated_at = now()
     WHERE t.status::text = 'provisioning'
       AND NOT EXISTS (
            SELECT 1
              FROM agent_configs AS c
             WHERE c.tenant_id = t.id
               AND c.status = 'active'
       )
    RETURNING t.id
)
INSERT INTO audit_log (id, tenant_id, actor, action, target, before_json, after_json)
SELECT gen_random_uuid(), moved.id, '{ACTOR}', '{ACTION}', 'tenant:' || moved.id::text,
       '{{"status": "provisioning"}}'::jsonb, '{{"status": "active"}}'::jsonb
  FROM moved
"""

DOWNGRADE = f"""
WITH marks AS (
    DELETE FROM audit_log
     WHERE actor = '{ACTOR}'
       AND action = '{ACTION}'
    RETURNING tenant_id
)
UPDATE tenants AS t
   SET status = 'provisioning', updated_at = now()
  FROM marks
 WHERE t.id = marks.tenant_id
   AND t.status = 'active'
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
