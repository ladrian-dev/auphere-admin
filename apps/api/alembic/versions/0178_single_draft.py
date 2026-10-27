"""Un solo borrador por agente — spec 047, T039 (ola 1, historia 2).

- ``agent_configs.agent_version_number``: «v{n} de {agente}». Numera por agente
  sin tocar el ``version`` de cada cliente (``UNIQUE (tenant_id, version)`` se
  queda). Se rellena por agente en el orden de ``version`` y, desde aquí, lo pone
  un disparador al insertar: ningún escritor de hoy (admin, API de partners,
  semillas) tiene que saber que existe.
- Como mucho un ``staged`` por agente (índice único parcial). Si hoy hay agentes
  con varios, se queda el más reciente y los demás pasan a ``archived``: no se
  borra nada (§IV).
- ``agents.draft_revision``: la revisión del borrador para ``If-Match``; el 412
  enseña los cambios del otro (requisito 3.3).
- ``agent_configs.note`` y ``base_version_id`` (la versión de la que partió el
  borrador), con FK **compuesta**: para eso ``agent_configs`` gana
  ``UNIQUE (tenant_id, id)``.

Revision ID: 0178_single_draft
Revises: 0177_usage_task_and_line
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0178_single_draft"
down_revision: str | Sequence[str] | None = "0177_usage_task_and_line"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE agent_configs ADD CONSTRAINT uq_agent_configs_tenant_id UNIQUE (tenant_id, id)"
    )

    # A staged row older than its agent's active version was an ignored
    # leftover; as «the draft» it would publish old content over the active
    # one. Archive it first.
    op.execute(
        """
        UPDATE agent_configs s SET status = 'archived', updated_at = now()
        FROM agent_configs a
        WHERE s.status = 'staged' AND a.status = 'active'
          AND a.tenant_id = s.tenant_id AND a.agent_id = s.agent_id
          AND s.version < a.version
        """
    )
    # One draft per agent. Keep the newest staged row, archive the rest.
    op.execute(
        """
        UPDATE agent_configs ac SET status = 'archived', updated_at = now()
        FROM (
            SELECT id, row_number() OVER (
                PARTITION BY tenant_id, agent_id ORDER BY version DESC
            ) AS rn
            FROM agent_configs WHERE status = 'staged'
        ) dup
        WHERE ac.id = dup.id AND dup.rn > 1
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_agent_configs_one_draft ON agent_configs (tenant_id, agent_id) "
        "WHERE status = 'staged'"
    )

    op.execute("ALTER TABLE agent_configs ADD COLUMN agent_version_number integer")
    op.execute(
        """
        UPDATE agent_configs ac SET agent_version_number = n.rn
        FROM (
            SELECT id, row_number() OVER (
                PARTITION BY tenant_id, agent_id ORDER BY version
            ) AS rn
            FROM agent_configs
        ) n
        WHERE ac.id = n.id
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION agent_configs_number_per_agent()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.agent_version_number IS NULL THEN
                SELECT coalesce(max(agent_version_number), 0) + 1
                  INTO NEW.agent_version_number
                  FROM agent_configs
                 WHERE tenant_id = NEW.tenant_id AND agent_id = NEW.agent_id;
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        "CREATE TRIGGER trg_agent_configs_number BEFORE INSERT ON agent_configs "
        "FOR EACH ROW EXECUTE FUNCTION agent_configs_number_per_agent()"
    )
    op.execute("ALTER TABLE agent_configs ALTER COLUMN agent_version_number SET NOT NULL")
    op.execute(
        "ALTER TABLE agent_configs ADD CONSTRAINT uq_agent_configs_agent_number "
        "UNIQUE (tenant_id, agent_id, agent_version_number)"
    )

    op.execute("ALTER TABLE agent_configs ADD COLUMN note varchar(500)")
    op.execute("ALTER TABLE agent_configs ADD COLUMN base_version_id uuid")
    op.execute(
        "ALTER TABLE agent_configs ADD CONSTRAINT fk_agent_configs_base_version "
        "FOREIGN KEY (tenant_id, base_version_id) REFERENCES agent_configs (tenant_id, id) "
        "ON DELETE SET NULL (base_version_id)"
    )

    op.execute("ALTER TABLE agents ADD COLUMN draft_revision integer NOT NULL DEFAULT 0")
    op.execute(
        """
        INSERT INTO console_audit_vocabulary (action, category, severity, summary_es, summary_en)
        VALUES ('agent_config.discard', 'agents', 'info',
                '{actor} descartó el borrador (versión {v}) del agente de {client}',
                '{actor} discarded the draft (version {v}) of {client}''s agent')
        ON CONFLICT (action) DO NOTHING
        """
    )
    op.execute(
        "ALTER TABLE agents ADD CONSTRAINT ck_agents_draft_revision CHECK (draft_revision >= 0)"
    )


def downgrade() -> None:
    op.execute("DELETE FROM console_audit_vocabulary WHERE action = 'agent_config.discard'")
    op.execute("ALTER TABLE agents DROP CONSTRAINT IF EXISTS ck_agents_draft_revision")
    op.execute("ALTER TABLE agents DROP COLUMN IF EXISTS draft_revision")
    op.execute("ALTER TABLE agent_configs DROP CONSTRAINT IF EXISTS fk_agent_configs_base_version")
    op.execute("ALTER TABLE agent_configs DROP COLUMN IF EXISTS base_version_id")
    op.execute("ALTER TABLE agent_configs DROP COLUMN IF EXISTS note")
    op.execute("ALTER TABLE agent_configs DROP CONSTRAINT IF EXISTS uq_agent_configs_agent_number")
    op.execute("DROP TRIGGER IF EXISTS trg_agent_configs_number ON agent_configs")
    op.execute("DROP FUNCTION IF EXISTS agent_configs_number_per_agent()")
    op.execute("ALTER TABLE agent_configs DROP COLUMN IF EXISTS agent_version_number")
    # The archived duplicates stay archived: there is no telling which were drafts.
    op.execute("DROP INDEX IF EXISTS uq_agent_configs_one_draft")
    op.execute("ALTER TABLE agent_configs DROP CONSTRAINT IF EXISTS uq_agent_configs_tenant_id")
