"""RLS también en cada partición, no solo en el padre (WP-16, aislamiento).

Hallazgo del 2026-08-09 al crear ``usage_records``: ``messages`` tiene
``ENABLE + FORCE ROW LEVEL SECURITY`` en el padre, pero **ninguna de sus
particiones la tiene**::

    SELECT relname, relrowsecurity FROM pg_class WHERE relname LIKE 'messages%';
    messages            | t
    messages_y2026m08   | f      ← 200k filas de todos los tenants, sin policy

El camino del runtime está a salvo: la app consulta siempre el padre y
Postgres aplica ahí las policies. El agujero es la consulta DIRECTA a una
partición — un job de retención, un script de ops, un backfill — que hoy
ve todos los tenants sin que nada falle ni avise. Es exactamente el modelo
de amenaza que el repo declara: el bug accidental de scoping, no el
atacante con SQL arbitrario.

Se arregla en el sitio donde nacen las particiones, no fila por fila:
``ensure_month_partition()`` (0064) pasa a propagar RLS del padre a la
partición recién creada. Y se hace el backfill de las que ya existen.

Nota sobre las policies: NO se duplican por partición. Una policy en el
padre no cubre el acceso directo a la partición, así que la partición se
queda con RLS activa y CERO policies, que en Postgres significa "no se ve
ninguna fila" — fail-closed. Cualquier acceso directo legítimo (el cron
de retención) debe ir por el padre, que es lo que hace hoy.

Revision ID: 0069_partition_rls_inherit
Revises: 0068_usage_records
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0069_partition_rls_inherit"
down_revision: str | Sequence[str] | None = "0068_usage_records"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_FUNCTION_V2 = """
CREATE OR REPLACE FUNCTION ensure_month_partition(parent text, month date)
RETURNS text AS $$
DECLARE
    start_d date := date_trunc('month', month)::date;
    end_d   date := (date_trunc('month', month) + interval '1 month')::date;
    part_name text := format(
        '%s_y%sm%s', parent, to_char(start_d, 'YYYY'), to_char(start_d, 'MM')
    );
    parent_rls boolean;
    parent_force boolean;
BEGIN
    IF NOT EXISTS (
        SELECT FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = part_name AND n.nspname = 'public'
    ) THEN
        EXECUTE format(
            'CREATE TABLE %I PARTITION OF %I FOR VALUES FROM (%L) TO (%L)',
            part_name, parent, start_d, end_d
        );
    END IF;

    -- La partición hereda columnas e índices del padre, pero NO su RLS:
    -- sin esto, un SELECT directo a la partición ve todos los tenants.
    SELECT relrowsecurity, relforcerowsecurity INTO parent_rls, parent_force
    FROM pg_class WHERE oid = format('public.%I', parent)::regclass;

    IF parent_rls THEN
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', part_name);
    END IF;
    IF parent_force THEN
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', part_name);
    END IF;

    RETURN part_name;
END;
$$ LANGUAGE plpgsql;
"""

_FUNCTION_V1 = """
CREATE OR REPLACE FUNCTION ensure_month_partition(parent text, month date)
RETURNS text AS $$
DECLARE
    start_d date := date_trunc('month', month)::date;
    end_d   date := (date_trunc('month', month) + interval '1 month')::date;
    part_name text := format(
        '%s_y%sm%s', parent, to_char(start_d, 'YYYY'), to_char(start_d, 'MM')
    );
BEGIN
    IF NOT EXISTS (
        SELECT FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = part_name AND n.nspname = 'public'
    ) THEN
        EXECUTE format(
            'CREATE TABLE %I PARTITION OF %I FOR VALUES FROM (%L) TO (%L)',
            part_name, parent, start_d, end_d
        );
    END IF;
    RETURN part_name;
END;
$$ LANGUAGE plpgsql;
"""

# Backfill: toda partición cuyo padre tenga RLS, la hereda ahora.
_BACKFILL = """
DO $$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT child.relname AS child_name,
               parent.relrowsecurity AS p_rls,
               parent.relforcerowsecurity AS p_force
        FROM pg_inherits i
        JOIN pg_class child  ON child.oid  = i.inhrelid
        JOIN pg_class parent ON parent.oid = i.inhparent
        JOIN pg_namespace n  ON n.oid = child.relnamespace
        WHERE n.nspname = 'public'
          AND parent.relkind = 'p'
          AND parent.relrowsecurity
    LOOP
        IF r.p_rls THEN
            EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', r.child_name);
        END IF;
        IF r.p_force THEN
            EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', r.child_name);
        END IF;
    END LOOP;
END $$;
"""

_UNDO_BACKFILL = """
DO $$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT child.relname AS child_name
        FROM pg_inherits i
        JOIN pg_class child  ON child.oid  = i.inhrelid
        JOIN pg_class parent ON parent.oid = i.inhparent
        JOIN pg_namespace n  ON n.oid = child.relnamespace
        WHERE n.nspname = 'public' AND parent.relkind = 'p'
    LOOP
        EXECUTE format('ALTER TABLE %I NO FORCE ROW LEVEL SECURITY', r.child_name);
        EXECUTE format('ALTER TABLE %I DISABLE ROW LEVEL SECURITY', r.child_name);
    END LOOP;
END $$;
"""


def upgrade() -> None:
    op.execute(_FUNCTION_V2)
    op.execute(_BACKFILL)


def downgrade() -> None:
    op.execute(_UNDO_BACKFILL)
    op.execute(_FUNCTION_V1)
