"""Rol de sólo lectura para el panel de margen, con alcance escrito (WP-30b).

El spec de WP-30b justifica Grafana con una frase: "coste por tenant es
una consulta SQL contra Aurora". **Esa consulta devuelve cero filas.**
``usage_records`` tiene ``ENABLE`` + ``FORCE`` row security (0068), y
``FORCE`` alcanza también al dueño de la tabla: cualquiera que conecte
sin ``app.tenant_id`` ve la tabla vacía — sin error, sin aviso, que es la
peor forma de estar equivocado en un panel de dinero.

Así que el panel no es un problema de dibujo: exige decidir **quién lee
por encima del tenant**, que es exactamente la decisión que el código ha
esquivado dos veces (``invoices`` en la 0073, y
``GET /admin/tenants/{id}/cost``, que se hizo por-tenant para no tomarla).
Esta migración la toma, y la toma estrecha.

Forma elegida, y por qué no las otras:

- **Ni ``BYPASSRLS`` ni superusuario.** Un rol que salta la RLS lee
  *todo*: mensajes, credenciales cifradas, memorias del agente. El panel
  necesita cifras de coste. El radio de explosión de un Grafana
  comprometido debe parecerse a lo que el panel enseña, no a la base
  entera.
- **Ni ``NO FORCE`` sobre la tabla.** Aflojar la tabla para todos con tal
  de que la lea uno es cambiar un problema puntual por uno permanente.
- **Sí policies permisivas nominales, ``FOR SELECT TO nexus_reporting``.**
  Es el mecanismo que Postgres tiene para esto: quedan en
  ``pg_policies``, se leen con un ``\\d``, y un auditor ve el permiso sin
  tener que reconstruirlo desde el código de la aplicación. Una policy
  permisiva se suma (OR) a la existente, así que la de aislamiento por
  tenant sigue intacta para ``nexus_app``.
- **Y permisos por COLUMNA, no por tabla.** Ahí está la mitad del valor:
  ``agent_configs`` guarda ``system_prompt_rendered`` —el prompt a medida
  de cada cliente, que es su producto— y ``tenants`` guarda
  ``owner_phone`` y ``owner_email``. El panel quiere la *versión* del
  agente y el *nombre* del cliente. Se conceden esas columnas y nada más:
  aunque alguien apunte el datasource a la tabla cruda en vez de a la
  vista, el prompt no sale.

El rol se crea **LOGIN pero sin contraseña**, que en SCRAM significa que
no puede autenticar. La contraseña se pone fuera de banda y vive en
Secrets Manager, igual que ``NEXUS_DATABASE_URL``: una credencial en un
fichero de migración es una credencial publicada en el repositorio y en
el historial de git para siempre.

Nota sobre la tabla particionada: ``ensure_month_partition`` propaga
``ENABLE``/``FORCE`` a cada partición nueva pero **no copia las
policies**, así que una partición leída directamente niega todo. Es la
dirección correcta del error y aquí no se cambia: la vista consulta el
padre, que es donde viven las policies.

Revision ID: 0078_reporting_role
Revises: 0077_tenant_delete_cascade
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0078_reporting_role"
down_revision: str | Sequence[str] | None = "0077_tenant_delete_cascade"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ROLE = "nexus_reporting"

# Columnas concedidas por tabla. La lista es la política de privacidad del
# panel escrita en SQL: lo que no está aquí, el rol no puede leer ni
# equivocándose de tabla.
_COLUMN_GRANTS: dict[str, tuple[str, ...]] = {
    # Contadores de facturación. Se dejan fuera ``conversation_id``,
    # ``workflow_run_id`` e ``idempotency_key``: identifican turnos
    # concretos y el panel agrega, nunca señala una conversación.
    "usage_records": (
        "tenant_id",
        "partner_id",
        "occurred_at",
        "meter",
        "quantity",
        "cost_usd",
        "billable_qty",
        "provider",
        "model",
        "agent_config_id",
    ),
    # Sólo para poner nombre a la versión del agente en el eje del panel.
    "agent_configs": ("id", "tenant_id", "version", "status"),
    # Nombre y plan para etiquetar. NADA de owner_phone / owner_email.
    "tenants": ("id", "name", "slug", "plan", "status", "tier", "partner_id"),
}

# Tablas con RLS que además necesitan policy nominal. ``tenants`` no
# aparece porque no tiene row security (es la tabla raíz); le basta el
# permiso por columna.
_NEEDS_POLICY = ("usage_records", "agent_configs")


def upgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE}') THEN
                -- LOGIN sin contraseña: existe, pero no autentica hasta que
                -- alguien le ponga una fuera de banda.
                CREATE ROLE {ROLE} LOGIN NOSUPERUSER NOBYPASSRLS
                                   NOCREATEDB NOCREATEROLE NOINHERIT;
            END IF;
        END
        $$;
        """
    )

    # Membresía para el usuario que conecta, igual que 0004 hace con
    # ``nexus_app`` y por el mismo motivo poco obvio: en local el usuario de
    # migración es superusuario y puede ``SET ROLE`` a cualquier cosa, pero
    # el usuario maestro de Aurora **no lo es** — RDS no lo concede. Sin
    # esto, el test de alcance pasaría en CI y fallaría contra Aurora, que
    # es el único sitio donde importa.
    op.execute(
        f"""
        DO $$
        BEGIN
            EXECUTE format('GRANT {ROLE} TO %I', current_user);
        END
        $$;
        """
    )

    op.execute(f"GRANT USAGE ON SCHEMA public TO {ROLE}")

    for table, columns in _COLUMN_GRANTS.items():
        op.execute(f"GRANT SELECT ({', '.join(columns)}) ON {table} TO {ROLE}")

    for table in _NEEDS_POLICY:
        op.execute(
            f"CREATE POLICY {table}_reporting_read ON {table} "
            f"AS PERMISSIVE FOR SELECT TO {ROLE} USING (true)"
        )

    # La vista es lo que consulta Grafana. ``security_invoker`` la hace
    # correr con los permisos de quien pregunta y no con los del dueño:
    # sin eso se ejecutaría como ``nexus``, que por FORCE también está
    # sujeto a la RLS, y volveríamos a cero filas.
    #
    # ``unpriced_records`` NO es decoración. ``SUM`` ignora los NULL, y
    # NULL es justo lo que WP-19 escribe cuando algo se mide y no se
    # puede valorar: un mes a medio tarifar devolvería una cifra pequeña
    # y creíble. Quien pinte ``cost_usd_total`` sin mirar esta columna
    # está enseñando un número que no es el coste.
    op.execute(
        """
        CREATE VIEW reporting_tenant_cost_monthly
        WITH (security_invoker = true) AS
        SELECT u.tenant_id,
               t.name                                   AS tenant_name,
               t.plan,
               t.tier,
               u.partner_id,
               u.agent_config_id,
               ac.version                               AS agent_version,
               date_trunc('month', u.occurred_at)       AS month,
               u.meter,
               u.provider,
               u.model,
               sum(u.cost_usd)                          AS cost_usd_total,
               sum(u.billable_qty)                      AS billable_qty_total,
               count(*)                                 AS records,
               count(*) FILTER (WHERE u.cost_usd IS NULL) AS unpriced_records
          FROM usage_records u
          LEFT JOIN tenants t       ON t.id = u.tenant_id
          LEFT JOIN agent_configs ac ON ac.id = u.agent_config_id
         GROUP BY u.tenant_id, t.name, t.plan, t.tier, u.partner_id,
                  u.agent_config_id, ac.version,
                  date_trunc('month', u.occurred_at),
                  u.meter, u.provider, u.model
        """
    )
    op.execute(f"GRANT SELECT ON reporting_tenant_cost_monthly TO {ROLE}")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS reporting_tenant_cost_monthly")

    for table in _NEEDS_POLICY:
        op.execute(f"DROP POLICY IF EXISTS {table}_reporting_read ON {table}")

    for table, columns in _COLUMN_GRANTS.items():
        op.execute(f"REVOKE SELECT ({', '.join(columns)}) ON {table} FROM {ROLE}")

    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {ROLE}")
    op.execute(
        f"""
        DO $$
        BEGIN
            EXECUTE format('REVOKE {ROLE} FROM %I', current_user);
        END
        $$;
        """
    )
    op.execute(f"DROP ROLE IF EXISTS {ROLE}")
