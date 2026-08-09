"""RLS en las tablas de checkpoint de LangGraph (WP-14b, plataforma v2).

Cierra el aplazamiento consciente de 0065: la columna ``tenant_id`` +
trigger ya garantizaban la INTEGRIDAD del dato; esto añade el AISLAMIENTO
de lectura/escritura. ENABLE + FORCE (el usuario de la app es el owner en
AWS — sin FORCE la RLS sería decorativa) con dos policies por tabla:

- ``<t>_tenant``: ``tenant_id = app.tenant_id`` (GUC) — el camino del
  runtime. La activa el ``TenantScopedPostgresSaver`` del worker, que
  deriva el tenant del prefijo del thread_id y hace ``SET ROLE nexus_app``
  por operación.
- ``<t>_maintenance``: gated por ``app.rls_maintenance = 'on'`` — SOLO
  para los barridos globales del scheduler (checkpoint_retention_cron).
  El modelo de amenaza de esta RLS es el bug accidental de scoping, no un
  atacante con SQL arbitrario (cualquier conexión es el mismo usuario de
  BD y podría setear el GUC igual que hace ``SET LOCAL ROLE`` hoy).

Como en 0065, la lógica vive en ``harden_checkpoint_tables()`` (CREATE OR
REPLACE aquí) y se re-aplica tras ``saver.setup()`` en el boot del worker:
un DB fresco donde LangGraph crea las tablas DESPUÉS de migrar queda
igualmente protegido. Las filas con ``tenant_id`` NULL (threads legacy sin
prefijo) solo son visibles por el camino de mantenimiento — el cron de
retención acaba purgándolas por edad.

La tabla ``checkpoint_migrations`` queda fuera a propósito (metadata del
saver, sin datos de tenant; ``setup()`` la lee como owner sin GUC).

Revision ID: 0066_checkpoint_rls
Revises: 0065_checkpoint_tenant_id
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0066_checkpoint_rls"
down_revision: str | Sequence[str] | None = "0065_checkpoint_tenant_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_THREAD_PATTERN = "^tenant:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}:"

# La función completa: TODO lo de 0065 (columna+backfill+índice+trigger)
# más el bloque RLS nuevo. CREATE OR REPLACE para que el boot del worker
# (que llama a esta función tras setup()) aplique siempre la última versión.
_HARDEN_V2 = f"""
CREATE OR REPLACE FUNCTION harden_checkpoint_tables() RETURNS void AS $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY
        ARRAY['checkpoints', 'checkpoint_blobs', 'checkpoint_writes']
    LOOP
        IF to_regclass('public.' || t) IS NULL THEN
            CONTINUE;  -- LangGraph has not created this table yet
        END IF;
        EXECUTE format(
            'ALTER TABLE %I ADD COLUMN IF NOT EXISTS tenant_id uuid', t
        );
        EXECUTE format(
            'UPDATE %I SET tenant_id = substring(thread_id from 8 for 36)::uuid '
            'WHERE tenant_id IS NULL AND thread_id ~ %L',
            t, '{_THREAD_PATTERN}'
        );
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS ix_%s_tenant_thread '
            'ON %I (tenant_id, thread_id)',
            t, t
        );
        EXECUTE format('DROP TRIGGER IF EXISTS trg_%s_tenant ON %I', t, t);
        EXECUTE format(
            'CREATE TRIGGER trg_%s_tenant BEFORE INSERT OR UPDATE ON %I '
            'FOR EACH ROW EXECUTE FUNCTION checkpoint_derive_tenant()',
            t, t
        );

        -- WP-14b: RLS ------------------------------------------------------
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
        EXECUTE format('DROP POLICY IF EXISTS %s_tenant ON %I', t, t);
        EXECUTE format(
            'CREATE POLICY %s_tenant ON %I '
            'USING (tenant_id = NULLIF(current_setting(''app.tenant_id'', true), '''')::uuid) '
            'WITH CHECK (tenant_id = NULLIF(current_setting(''app.tenant_id'', true), '''')::uuid)',
            t, t
        );
        EXECUTE format('DROP POLICY IF EXISTS %s_maintenance ON %I', t, t);
        EXECUTE format(
            'CREATE POLICY %s_maintenance ON %I '
            'USING (current_setting(''app.rls_maintenance'', true) = ''on'') '
            'WITH CHECK (current_setting(''app.rls_maintenance'', true) = ''on'')',
            t, t
        );
        -- El wrapper opera como nexus_app (mismo patrón que el resto de la
        -- app): necesita DML sobre las tablas del saver.
        EXECUTE format(
            'GRANT SELECT, INSERT, UPDATE, DELETE ON %I TO nexus_app', t
        );
    END LOOP;
END;
$$ LANGUAGE plpgsql;
"""

# La versión 0065 de la función, para el downgrade (sin el bloque RLS).
_HARDEN_V1 = f"""
CREATE OR REPLACE FUNCTION harden_checkpoint_tables() RETURNS void AS $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY
        ARRAY['checkpoints', 'checkpoint_blobs', 'checkpoint_writes']
    LOOP
        IF to_regclass('public.' || t) IS NULL THEN
            CONTINUE;
        END IF;
        EXECUTE format(
            'ALTER TABLE %I ADD COLUMN IF NOT EXISTS tenant_id uuid', t
        );
        EXECUTE format(
            'UPDATE %I SET tenant_id = substring(thread_id from 8 for 36)::uuid '
            'WHERE tenant_id IS NULL AND thread_id ~ %L',
            t, '{_THREAD_PATTERN}'
        );
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS ix_%s_tenant_thread '
            'ON %I (tenant_id, thread_id)',
            t, t
        );
        EXECUTE format('DROP TRIGGER IF EXISTS trg_%s_tenant ON %I', t, t);
        EXECUTE format(
            'CREATE TRIGGER trg_%s_tenant BEFORE INSERT OR UPDATE ON %I '
            'FOR EACH ROW EXECUTE FUNCTION checkpoint_derive_tenant()',
            t, t
        );
    END LOOP;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.execute(_HARDEN_V2)
    op.execute("SELECT harden_checkpoint_tables()")


def downgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE
            t text;
        BEGIN
            FOREACH t IN ARRAY
                ARRAY['checkpoints', 'checkpoint_blobs', 'checkpoint_writes']
            LOOP
                IF to_regclass('public.' || t) IS NULL THEN
                    CONTINUE;
                END IF;
                EXECUTE format('DROP POLICY IF EXISTS %s_tenant ON %I', t, t);
                EXECUTE format('DROP POLICY IF EXISTS %s_maintenance ON %I', t, t);
                EXECUTE format('ALTER TABLE %I NO FORCE ROW LEVEL SECURITY', t);
                EXECUTE format('ALTER TABLE %I DISABLE ROW LEVEL SECURITY', t);
                EXECUTE format(
                    'REVOKE SELECT, INSERT, UPDATE, DELETE ON %I FROM nexus_app', t
                );
            END LOOP;
        END;
        $$;
        """
    )
    op.execute(_HARDEN_V1)
