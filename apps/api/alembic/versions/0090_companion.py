"""Esquema ``companion`` — cimientos del Companion de la consola (CO-01).

El Companion es el agente que vive en la consola de partners y opera la
consola por conversación. No es el agente que atiende a clientes finales y
**no tiene un camino privilegiado**: sus herramientas (CO-02) llamarán a
los mismos routers ``/console/*`` que la interfaz, con el mismo principal.

Esta migración pone los datos. Cuatro tablas bajo un esquema propio, más
tres retoques en tablas existentes.

Por qué esquema propio y no ``qa.*``
------------------------------------
El playground guarda su transcripción **en la memoria del navegador** por
la decisión C8 (ningún endpoint de ``/console/*`` devuelve el texto de un
mensaje). El Companion sí persiste la suya: es trabajo del partner, tiene
que sobrevivir a un F5 y a un reinicio de la API, y —esto es lo que lo
hace legítimo— **no contiene texto de ningún cliente final**. Mezclarla con
``qa.*`` habría atado dos retenciones, dos RLS y dos ciclos de vida
distintos a las mismas tablas.

RLS por ``principal_id``
------------------------
Mismo patrón fail-closed que ``qa.*`` por ``operator_id`` (0025/0028): la
policy compara con ``NULLIF(current_setting('app.principal_id', true), '')``
y, con el GUC ausente, no devuelve ninguna fila en vez de reventar.
``messages`` y ``actions`` no llevan la columna: se cubren por ``EXISTS``
sobre el hilo, que sí la lleva. Poner ``principal_id`` en las cuatro habría
sido más rápido de consultar y habría creado la posibilidad de que una fila
hija discrepe de su padre — un hilo que cambia de dueño dejaría mensajes
huérfanos visibles para el dueño anterior.

``principal_id`` es **TEXT** y no ``uuid``: ``partner_memberships.user_id``
es texto (la 0026 ya movió ``qa.threads.operator_id`` por lo mismo). La
seguridad viene de la simetría USING/WITH CHECK, no de la forma del id.

Las tres columnas de fuera del esquema
--------------------------------------
- ``usage_records.source`` admite ``'companion'``. Sin esto el gasto del
  Companion tendría que medirse como ``qa`` (y robarle el tope al
  playground) o como ``channel`` (**y facturárselo al cliente final**, que
  es un error de facturación, no un detalle de panel).
- ``partners.companion_monthly_token_cap`` — tope propio, en tokens como el
  del playground (C9: es la unidad que el partner ve). Defecto conservador:
  500.000 tokens/mes son del orden de 300-500 turnos del Companion, holgado
  para el piloto y acotado como pérdida. Se sube por fila.
- ``tenant_model_bindings_role_check`` admite ``'companion'``. El CHECK fija
  la lista de roles, así que tocar solo ``MODEL_ROLES`` en
  ``db/models/model_profile.py`` dejaría un rol que la base rechaza al
  escribir. El Companion es la cara de Auphere ante el partner: tiene que
  poder atarse a un modelo distinto —y más caro— que los agentes de cliente.

``companion.actions`` se crea aunque la escriba CO-04: el esquema completo
en una migración evita una segunda pasada de RLS y grants sobre las mismas
tablas.

Numeración: ``alembic heads`` da ``0088_console_identity``. PLAN-CONSOLE-V1
reserva **0089** para ``partner_billing``, que aún no existe — se deja el
hueco a propósito y esta cuelga de la 0088.

Revision ID: 0090_companion
Revises: 0088_console_identity
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0090_companion"
down_revision: str | Sequence[str] | None = "0089_operator_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "companion"

#: Tokens LLM (entrada + salida) que el Companion de un partner puede
#: consumir por mes natural UTC. Conservador a propósito.
DEFAULT_COMPANION_MONTHLY_TOKEN_CAP = 500_000

#: Tablas con ``principal_id`` propio → policy directa.
OWNED_TABLES: tuple[str, ...] = ("threads", "runs")
#: Tablas colgadas de un hilo → policy por ``EXISTS`` sobre el hilo.
CHILD_TABLES: tuple[str, ...] = ("messages", "actions")

_PRINCIPAL = "NULLIF(current_setting('app.principal_id', true), '')"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    # ── companion.threads ──────────────────────────────────────────────
    #
    # ``tenant_id`` es NULLABLE: un hilo puede empezar sin cliente ("créame
    # un agente para una clínica dental") y atarse a uno después. SET NULL
    # y no CASCADE al borrar el tenant: la conversación en la que se decidió
    # algo sobrevive al cliente: es la traza de por qué se hizo.
    op.execute(
        f"""
        CREATE TABLE {SCHEMA}.threads (
            id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
            principal_id text        NOT NULL,
            partner_id   uuid        NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
            tenant_id    uuid        NULL REFERENCES tenants(id) ON DELETE SET NULL,
            title        text        NOT NULL DEFAULT 'Nueva conversación',
            mode         text        NOT NULL DEFAULT 'consult',
            created_at   timestamptz NOT NULL DEFAULT now(),
            updated_at   timestamptz NOT NULL DEFAULT now(),
            last_run_at  timestamptz NULL,
            archived_at  timestamptz NULL,
            CONSTRAINT ck_companion_threads_mode
                CHECK (mode IN ('consult', 'build')),
            CONSTRAINT ck_companion_threads_principal_bounded
                CHECK (length(principal_id) > 0 AND length(principal_id) <= 120)
        )
        """
    )
    op.execute(
        f"CREATE INDEX ix_companion_threads_principal_updated "
        f"ON {SCHEMA}.threads (principal_id, updated_at DESC)"
    )
    op.execute(
        f"CREATE INDEX ix_companion_threads_partner ON {SCHEMA}.threads (partner_id, created_at DESC)"
    )

    # ── companion.runs ─────────────────────────────────────────────────
    #
    # ``interrupted`` es un estado de primera clase y no un ``error``: el
    # proceso de la API se reinició a mitad de run. El usuario tiene que ver
    # QUÉ pasó, no una pantalla en blanco ni un fallo que no ocurrió.
    op.execute(
        f"""
        CREATE TABLE {SCHEMA}.runs (
            id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
            thread_id     uuid        NOT NULL
                              REFERENCES {SCHEMA}.threads(id) ON DELETE CASCADE,
            principal_id  text        NOT NULL,
            status        text        NOT NULL DEFAULT 'running',
            started_at    timestamptz NOT NULL DEFAULT now(),
            ended_at      timestamptz NULL,
            input_tokens  integer     NULL,
            output_tokens integer     NULL,
            error         text        NULL,
            CONSTRAINT ck_companion_runs_status CHECK (
                status IN ('running', 'completed', 'cancelled', 'error', 'interrupted')
            ),
            CONSTRAINT ck_companion_runs_principal_bounded
                CHECK (length(principal_id) > 0 AND length(principal_id) <= 120)
        )
        """
    )
    op.execute(
        f"CREATE INDEX ix_companion_runs_thread_started "
        f"ON {SCHEMA}.runs (thread_id, started_at DESC)"
    )
    # El reaper de arranque y el tope mensual son las dos consultas que
    # justifican estos dos índices, y ninguna de las dos filtra por hilo.
    op.execute(
        f"CREATE INDEX ix_companion_runs_running ON {SCHEMA}.runs (started_at) "
        f"WHERE status = 'running'"
    )
    op.execute(
        f"CREATE INDEX ix_companion_runs_principal_started "
        f"ON {SCHEMA}.runs (principal_id, started_at DESC)"
    )

    # ── companion.messages ─────────────────────────────────────────────
    #
    # SIN razonamiento. Los bloques de pensamiento se emiten por el stream
    # y mueren con la sesión: son caros de guardar y son la parte más
    # propensa a contener divagaciones que luego se leen como compromisos.
    op.execute(
        f"""
        CREATE TABLE {SCHEMA}.messages (
            id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
            thread_id     uuid        NOT NULL
                              REFERENCES {SCHEMA}.threads(id) ON DELETE CASCADE,
            run_id        uuid        NULL
                              REFERENCES {SCHEMA}.runs(id) ON DELETE SET NULL,
            seq           integer     NOT NULL,
            role          text        NOT NULL,
            content       text        NOT NULL DEFAULT '',
            tool_calls    jsonb       NOT NULL DEFAULT '[]'::jsonb,
            input_tokens  integer     NULL,
            output_tokens integer     NULL,
            model         text        NULL,
            created_at    timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_companion_messages_role
                CHECK (role IN ('user', 'assistant', 'system', 'tool')),
            CONSTRAINT uq_companion_messages_thread_seq UNIQUE (thread_id, seq)
        )
        """
    )
    op.execute(
        f"CREATE INDEX ix_companion_messages_thread_seq ON {SCHEMA}.messages (thread_id, seq)"
    )

    # ── companion.actions ──────────────────────────────────────────────
    #
    # La escribe CO-04. ``id`` sin default: se deriva de forma determinista
    # del (run_id, índice de paso) y se escribe con UPSERT, porque
    # ``interrupt()`` re-ejecuta el nodo entero desde la primera línea y un
    # INSERT dejaría la acción duplicada en cada confirmación.
    op.execute(
        f"""
        CREATE TABLE {SCHEMA}.actions (
            id          uuid        PRIMARY KEY,
            thread_id   uuid        NOT NULL
                            REFERENCES {SCHEMA}.threads(id) ON DELETE CASCADE,
            run_id      uuid        NULL
                            REFERENCES {SCHEMA}.runs(id) ON DELETE SET NULL,
            kind        text        NOT NULL,
            payload     jsonb       NOT NULL DEFAULT '{{}}'::jsonb,
            diff        jsonb       NULL,
            state_hash  text        NULL,
            status      text        NOT NULL DEFAULT 'proposed',
            proposed_at timestamptz NOT NULL DEFAULT now(),
            decided_at  timestamptz NULL,
            decided_by  text        NULL,
            applied_at  timestamptz NULL,
            result      jsonb       NULL,
            CONSTRAINT ck_companion_actions_status CHECK (
                status IN ('proposed', 'confirmed', 'cancelled', 'expired', 'applied', 'failed')
            )
        )
        """
    )
    op.execute(
        f"CREATE INDEX ix_companion_actions_thread_proposed "
        f"ON {SCHEMA}.actions (thread_id, proposed_at DESC)"
    )

    # ── RLS por principal (fail-closed) ────────────────────────────────
    for table in (*OWNED_TABLES, *CHILD_TABLES):
        op.execute(f"ALTER TABLE {SCHEMA}.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {SCHEMA}.{table} FORCE ROW LEVEL SECURITY")

    for table in OWNED_TABLES:
        op.execute(
            f"""
            CREATE POLICY companion_{table}_principal_isolation ON {SCHEMA}.{table}
            USING (principal_id = {_PRINCIPAL})
            WITH CHECK (principal_id = {_PRINCIPAL})
            """
        )

    for table in CHILD_TABLES:
        op.execute(
            f"""
            CREATE POLICY companion_{table}_principal_isolation ON {SCHEMA}.{table}
            USING (
                EXISTS (
                    SELECT 1 FROM {SCHEMA}.threads t
                     WHERE t.id = {table}.thread_id
                       AND t.principal_id = {_PRINCIPAL}
                )
            )
            WITH CHECK (
                EXISTS (
                    SELECT 1 FROM {SCHEMA}.threads t
                     WHERE t.id = {table}.thread_id
                       AND t.principal_id = {_PRINCIPAL}
                )
            )
            """
        )

    # El rol degradado del runtime es el que corre bajo RLS; sin los grants,
    # la policy pasa y el GRANT deniega, que se ve como un 403 de Postgres
    # imposible de leer.
    op.execute(f"GRANT USAGE ON SCHEMA {SCHEMA} TO nexus_app")
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {SCHEMA} TO nexus_app"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA {SCHEMA} "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO nexus_app"
    )

    # ── usage_records.source admite 'companion' ────────────────────────
    op.execute("ALTER TABLE usage_records DROP CONSTRAINT IF EXISTS ck_usage_source")
    op.execute(
        "ALTER TABLE usage_records ADD CONSTRAINT ck_usage_source "
        "CHECK (source IN ('channel', 'qa', 'companion'))"
    )

    # ── tope propio del Companion por partner ──────────────────────────
    op.execute(
        "ALTER TABLE partners "
        "ADD COLUMN companion_monthly_token_cap bigint NOT NULL "
        f"DEFAULT {DEFAULT_COMPANION_MONTHLY_TOKEN_CAP}, "
        "ADD COLUMN companion_cap_notes text NULL"
    )
    op.execute(
        "ALTER TABLE partners ADD CONSTRAINT ck_partners_companion_monthly_token_cap "
        "CHECK (companion_monthly_token_cap >= 0)"
    )

    # ── rol de modelo 'companion' ──────────────────────────────────────
    op.execute(
        "ALTER TABLE tenant_model_bindings DROP CONSTRAINT IF EXISTS tenant_model_bindings_role_check"
    )
    op.execute(
        """
        ALTER TABLE tenant_model_bindings ADD CONSTRAINT tenant_model_bindings_role_check CHECK (
            role IN (
                'classify', 'respond', 'grade', 'improve',
                'voice_llm', 'voice_stt', 'voice_tts', 'companion'
            )
        )
        """
    )


def downgrade() -> None:
    # Un binding de rol 'companion' bloquearía el CHECK anterior. Se borra
    # antes: la fila describe una elección que, sin la columna, no se puede
    # representar; conservarla haría fallar la bajada entera.
    op.execute("ALTER TABLE tenant_model_bindings NO FORCE ROW LEVEL SECURITY")
    op.execute("DELETE FROM tenant_model_bindings WHERE role = 'companion'")
    op.execute("ALTER TABLE tenant_model_bindings FORCE ROW LEVEL SECURITY")
    op.execute(
        "ALTER TABLE tenant_model_bindings DROP CONSTRAINT IF EXISTS tenant_model_bindings_role_check"
    )
    op.execute(
        """
        ALTER TABLE tenant_model_bindings ADD CONSTRAINT tenant_model_bindings_role_check CHECK (
            role IN (
                'classify', 'respond', 'grade', 'improve',
                'voice_llm', 'voice_stt', 'voice_tts'
            )
        )
        """
    )

    op.execute(
        "ALTER TABLE partners DROP CONSTRAINT IF EXISTS ck_partners_companion_monthly_token_cap"
    )
    op.execute(
        "ALTER TABLE partners "
        "DROP COLUMN IF EXISTS companion_cap_notes, "
        "DROP COLUMN IF EXISTS companion_monthly_token_cap"
    )

    # Las filas de consumo del Companion se quedan: es gasto que ocurrió. Al
    # volver el CHECK a dos valores habría que reetiquetarlas, y llamarlas
    # 'channel' se las facturaría al cliente final — exactamente el error
    # que esta migración vino a evitar. Se borran, que es lo honesto: sin
    # columna que lo distinga, esa medición no se puede representar.
    op.execute("DELETE FROM usage_records WHERE source = 'companion'")
    op.execute("ALTER TABLE usage_records DROP CONSTRAINT IF EXISTS ck_usage_source")
    op.execute(
        "ALTER TABLE usage_records ADD CONSTRAINT ck_usage_source "
        "CHECK (source IN ('channel', 'qa'))"
    )

    for table in (*OWNED_TABLES, *CHILD_TABLES):
        op.execute(
            f"DROP POLICY IF EXISTS companion_{table}_principal_isolation ON {SCHEMA}.{table}"
        )
        op.execute(f"ALTER TABLE IF EXISTS {SCHEMA}.{table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE IF EXISTS {SCHEMA}.{table} DISABLE ROW LEVEL SECURITY")

    op.execute(f"DROP TABLE IF EXISTS {SCHEMA}.actions")
    op.execute(f"DROP TABLE IF EXISTS {SCHEMA}.messages")
    op.execute(f"DROP TABLE IF EXISTS {SCHEMA}.runs")
    op.execute(f"DROP TABLE IF EXISTS {SCHEMA}.threads")
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")
