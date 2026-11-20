"""Spec 065 (T033; requisitos 12.1, 12.2 y 12.6): el modelo de cada cliente pasa a sus agentes.

Un solo sitio para el modelo de respuesta (decisión de Luis, research.md §D15): por cada
fila de ``tenant_model_bindings`` con ``role = 'respond'``, cada agente activo de ese
cliente que todavía no tiene elección propia pasa a tenerla con ese modelo. Al desplegar,
ningún agente cambia de modelo (CE-005): Jemma's Hair Salón sigue con Terra.

- ``respond_model_set_by = 'partner'`` si la última ``console.model.update`` del cliente
  apunta a ese mismo modelo; si no (lo puso Auphere desde el panel), ``'operator'``.
- Una línea ``model.respond_binding.migrated`` por cliente con la fila de antes (modelo,
  ``fallback_chain`` y tope, que dejan de usarse) y los agentes que la recibieron.
- ``RAISE NOTICE`` con cuántas asignaciones encontró y cuántos agentes escribió, para
  compararlo con la comprobación previa (``scripts/respond_bindings_report.py``).
- **No borra** las filas de asignación: las borra la migración de la versión siguiente.
- No falla por lo que encuentre: una migración que aborta según los datos de prod tumba el
  despliegue; lo que se pierde se ve antes, en la comprobación previa.

Corre con ``row_security = off`` dentro del bloque (patrón de la 0205 y la 0229): con el rol
de migraciones, que salta la RLS, escribe; con uno que no la saltara, falla en voz alta en
vez de no ver a nadie y escribir 0 filas.

Revision ID: 0240_respond_bindings_to_agents
Revises: 0239_cache_write_lane_default
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0240_respond_bindings_to_agents"
down_revision: str | Sequence[str] | None = "0239_cache_write_lane_default"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTOR = "migration:0240"
ACTION = "model.respond_binding.migrated"

UPGRADE = f"""
DO $$
DECLARE
    b record;
    who text;
    last_console text;
    moved uuid[];
    bindings_found integer := 0;
    agents_written integer := 0;
BEGIN
    SET LOCAL row_security = off;
    FOR b IN
        SELECT tmb.tenant_id, tmb.model_profile_id, tmb.fallback_chain,
               tmb.max_cost_per_turn_usd, mp.model_id, mp.display_name
          FROM tenant_model_bindings tmb
          JOIN model_profiles mp ON mp.id = tmb.model_profile_id
         WHERE tmb.role = 'respond'
         ORDER BY tmb.tenant_id
    LOOP
        bindings_found := bindings_found + 1;
        SELECT al.after_json ->> 'model_id' INTO last_console
          FROM audit_log al
         WHERE al.tenant_id = b.tenant_id AND al.action = 'console.model.update'
         ORDER BY al.created_at DESC
         LIMIT 1;
        who := CASE WHEN last_console = b.model_id THEN 'partner' ELSE 'operator' END;

        WITH written AS (
            UPDATE agents
               SET respond_model_profile_id = b.model_profile_id,
                   respond_model_set_by = who,
                   respond_model_set_at = now()
             WHERE tenant_id = b.tenant_id
               AND status = 'active'
               AND respond_model_profile_id IS NULL
            RETURNING id
        )
        SELECT coalesce(array_agg(id ORDER BY id), ARRAY[]::uuid[]) INTO moved FROM written;
        agents_written := agents_written + coalesce(array_length(moved, 1), 0);

        INSERT INTO audit_log (tenant_id, actor, action, target, before_json, after_json)
        VALUES (
            b.tenant_id,
            '{ACTOR}',
            '{ACTION}',
            'tenant:' || b.tenant_id::text,
            jsonb_build_object(
                'model_id', b.model_id,
                'fallback_chain', coalesce(b.fallback_chain, '[]'::jsonb),
                'max_cost_per_turn_usd', b.max_cost_per_turn_usd
            ),
            jsonb_build_object(
                'model_id', b.model_id,
                'model', b.display_name,
                'set_by', who,
                'agents', to_jsonb(moved)
            )
        );
    END LOOP;
    RAISE NOTICE '0240_respond_bindings_to_agents: % asignaciones de respuesta, % agentes escritos',
        bindings_found, agents_written;
END $$
"""

DOWNGRADE = f"""
DO $$
DECLARE
    a record;
BEGIN
    SET LOCAL row_security = off;
    FOR a IN
        SELECT al.id, al.tenant_id, al.after_json
          FROM audit_log al
         WHERE al.action = '{ACTION}' AND al.actor = '{ACTOR}'
    LOOP
        UPDATE agents
           SET respond_model_profile_id = NULL,
               respond_model_set_by = NULL,
               respond_model_set_at = NULL
         WHERE tenant_id = a.tenant_id
           AND id IN (
               SELECT (jsonb_array_elements_text(coalesce(a.after_json -> 'agents', '[]')))::uuid
           );
        DELETE FROM audit_log WHERE id = a.id;
    END LOOP;
END $$
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
