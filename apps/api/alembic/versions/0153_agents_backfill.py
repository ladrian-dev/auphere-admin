"""El agente principal de cada cliente — spec 030, iteración 3 (relleno).

1. Un ``agents`` «Agente principal» (``active``) por cada tenant con alguna
   versión, con la fecha de su primera versión (así sigue siendo el principal
   cuando el cliente cree otros).
2. Todas sus versiones pasan a ser de ese agente.
3. Los números que **contestan** (no los solo de envío, ``agent_enabled =
   false``, ni el canal del Playground) se asignan a ese agente.
4. **Comprobación**: ninguna versión sin agente y ningún agente con dos
   versiones activas. Si falla, la migración aborta y no se despliega nada.
5. ``agent_configs.agent_id`` pasa a obligatorio y un índice único parcial fija
   **una versión activa por agente** — lo que hasta hoy solo decía el código.
6. Un *trigger* ``BEFORE INSERT``: una versión que llega **sin** agente —todos
   los escritores de antes de la spec 030: el aprovisionamiento, los scripts de
   siembra, los tests— cae en el agente principal del tenant, que se crea si no
   existe. Con un bloqueo consultivo por tenant, para que dos altas a la vez no
   creen dos principales. Así ninguna versión queda nunca sin agente sin tener
   que cambiar a la vez cada sitio que escribe una.

Revision ID: 0153_agents_backfill
Revises: 0152_agents
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0153_agents_backfill"
down_revision: str | Sequence[str] | None = "0152_agents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRINCIPAL = "Agente principal"


def upgrade() -> None:
    op.execute(
        f"""
        INSERT INTO agents (tenant_id, name, status, created_at, updated_at)
        SELECT tenant_id, '{PRINCIPAL}', 'active', min(created_at), now()
          FROM agent_configs
         GROUP BY tenant_id
        """
    )
    op.execute(
        """
        UPDATE agent_configs ac
           SET agent_id = a.id
          FROM agents a
         WHERE a.tenant_id = ac.tenant_id
           AND ac.agent_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE channels c
           SET agent_id = a.id
          FROM agents a
         WHERE a.tenant_id = c.tenant_id
           AND c.agent_id IS NULL
           AND c.provider <> 'qa_playground'
           AND COALESCE(c.config ->> 'agent_enabled', 'true') <> 'false'
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM agent_configs WHERE agent_id IS NULL) THEN
            RAISE EXCEPTION 'spec 030: agent_configs left without an agent';
          END IF;
          IF EXISTS (
            SELECT agent_id FROM agent_configs WHERE status = 'active'
             GROUP BY agent_id HAVING count(*) > 1
          ) THEN
            RAISE EXCEPTION 'spec 030: an agent ended up with two active versions';
          END IF;
        END
        $$;
        """
    )
    op.execute("ALTER TABLE agent_configs ALTER COLUMN agent_id SET NOT NULL")
    op.execute(
        "CREATE UNIQUE INDEX uq_agent_configs_agent_active ON agent_configs (agent_id) "
        "WHERE status = 'active'"
    )
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION agent_configs_default_agent() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.agent_id IS NULL THEN
            PERFORM pg_advisory_xact_lock(hashtextextended('agents:' || NEW.tenant_id::text, 0));
            SELECT id INTO NEW.agent_id
              FROM agents
             WHERE tenant_id = NEW.tenant_id AND status = 'active'
             ORDER BY created_at, id
             LIMIT 1;
            IF NEW.agent_id IS NULL THEN
              INSERT INTO agents (tenant_id, name) VALUES (NEW.tenant_id, '{PRINCIPAL}')
              RETURNING id INTO NEW.agent_id;
            END IF;
          END IF;
          RETURN NEW;
        END
        $$;
        """
    )
    op.execute(
        "CREATE TRIGGER trg_agent_configs_default_agent BEFORE INSERT ON agent_configs "
        "FOR EACH ROW EXECUTE FUNCTION agent_configs_default_agent()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_agent_configs_default_agent ON agent_configs")
    op.execute("DROP FUNCTION IF EXISTS agent_configs_default_agent()")
    op.execute("DROP INDEX IF EXISTS uq_agent_configs_agent_active")
    op.execute("ALTER TABLE agent_configs ALTER COLUMN agent_id DROP NOT NULL")
    op.execute("UPDATE channels SET agent_id = NULL")
    op.execute("UPDATE agent_configs SET agent_id = NULL")
    op.execute("DELETE FROM agents")
