"""Garantía 1, barrida (spec 047, T012 · requisitos 56.1, 8.6 y 1.1).

``test_21`` pregunta si cada tabla con ``tenant_id`` tiene RLS; acepta ENABLE
sin FORCE y cualquier política. ``test_22`` pregunta si se va con el cliente. Ni
uno ni otro mira lo que ``data-model.md`` exige a toda tabla de cliente:

1. **RLS ENABLE y FORCE**: ni siquiera el dueño de la tabla la lee por encima
   del cliente.
2. **La política de cliente canónica**, para todos los comandos, con ``USING`` y
   ``WITH CHECK`` explícitos sobre ``current_setting('app.tenant_id')``.
3. **Ninguna otra política permisiva** que abra la tabla por otro lado.
4. **Toda FK hacia otra tabla de cliente es compuesta** ``(tenant_id, x)``: la
   comprobación de una FK no pasa por la RLS, así que una de una sola columna
   deja que una fila del cliente A apunte a una del B (memoria «una FK no pasa
   por la RLS»).

El barrido recorre ``pg_class``, ``pg_policy`` y ``pg_constraint`` en todos los
esquemas de la aplicación, no una lista: una tabla nueva entra el día que se
crea. Lo de antes que no cumple está en un **inventario cerrado**, entrada a
entrada y con su razón; el inventario no puede crecer (techo), no puede
excusar ninguna tabla que cree una migración de la spec 047 en adelante, y una
entrada que ya cumple o cuya tabla ya no existe lo pone en rojo (no se pudre).

Bloqueante como el resto de la suite.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import sqlalchemy as sa

from nexus_api.db.base import get_sessionmaker

from ._tenant_catalog import CANONICAL_TENANT_EXPR, ClientTable, client_tables, normalise
from .test_21_rls_covers_every_tenant_table import ENABLE_ONLY_TABLES, PRE_TENANT_TABLES

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]

VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
#: La primera migración de la spec 047 (``0175_fabrica_base``). Ninguna tabla
#: creada desde aquí puede aparecer en el inventario.
FIRST_SPEC_047_MIGRATION = 175

# ── El inventario de lo de antes ────────────────────────────────────────────
#
# Cada entrada es ``(tabla, regla)`` y su razón. Las reglas:
#
#   "rls"            sin RLS, o ENABLE sin FORCE;
#   "policy"         ninguna política es la canónica de cliente;
#   "with_check"     la canónica existe pero sin WITH CHECK explícito;
#   "policy:<name>"  otra política permisiva, además de la canónica;
#   "fk:<name>"      FK de una sola columna hacia otra tabla de cliente.
#
# El inventario está CERRADO: solo puede encoger. Arreglar una tabla obliga a
# quitar su entrada (``test_the_inventory_does_not_rot``) y bajar el techo.

_SIN_RLS = "Sin RLS a propósito; es la razón de test_21 (PRE_TENANT_TABLES): {why}"
_SIN_FORCE = (
    "ENABLE sin FORCE a propósito: nexus_app sigue filtrado, y el rol dueño la "
    "lee por encima del cliente en un camino de plataforma (test_21, "
    "ENABLE_ONLY_TABLES: «{why}»). Con FORCE ese camino vería cero filas sin "
    "dar un error."
)
_CHECK_IMPLICITO = (
    "Política ALL con solo USING. Postgres usa el USING también como WITH CHECK "
    "en una política ALL, así que escribir una fila de otro cliente falla igual "
    "que con el WITH CHECK explícito: el riesgo es nulo y la entrada existe "
    "porque data-model.md pide la forma explícita. Anterior a la regla."
)
_FK_DE_UNA_COLUMNA = (
    "FK de una columna, anterior a la regla de FK compuestas (que estrenó la "
    "spec 043 con ``_tenant_fk``). Riesgo residual: un escritor con el GUC del "
    "cliente A puede apuntar a una fila del B conociendo su UUID, porque la "
    "comprobación de la FK no pasa por la RLS, y el ON DELETE de la FK sí toca "
    "la fila de A cuando B borra la suya. Mitigación de hoy: los ids son UUID "
    "aleatorios que no salen de su cliente, y la lectura posterior pasa por la "
    "RLS (la fila ajena no se ve). Pasarla a compuesta pide "
    "``UNIQUE (tenant_id, id)`` en el destino y validar la tabla: fuera de la 047."
)


def _fk(*pairs: tuple[str, str, str]) -> dict[tuple[str, str], str]:
    """``(tabla, constraint, nota)`` → entradas ``fk:<constraint>``."""
    return {
        (table, f"fk:{name}"): f"{_FK_DE_UNA_COLUMNA} {note}".strip() for table, name, note in pairs
    }


LEGACY_EXCEPTIONS: dict[tuple[str, str], str] = {
    # ── sin RLS ──────────────────────────────────────────────────────────
    **{
        (table, "rls"): _SIN_RLS.format(why=PRE_TENANT_TABLES[table])
        for table in (
            "api_keys",
            "channel_signup_links",
            "client_invitations",
            "client_memberships",
            "owner_phone_index",
            "partner_tenants",
            "whatsapp_template_status",
        )
    },
    # ── ENABLE sin FORCE ─────────────────────────────────────────────────
    **{
        (table, "rls"): _SIN_FORCE.format(why=ENABLE_ONLY_TABLES[table])
        for table in ("embed_audit_log", "invoice_lines", "invoices", "tenant_payments")
    },
    # ── la política no es la de cliente ──────────────────────────────────
    ("audit_log", "policy"): (
        "La política de cliente lleva un OR: sin GUC se ven las filas con "
        "``tenant_id`` NULL, que son acciones de plataforma y las que quedan "
        "anonimizadas tras un borrado RGPD (test_22, KEEP_ON_DELETE). Además, "
        "``audit_log_reporting_read`` deja leer al rol de informes (test_23)."
    ),
    ("partner_allocations", "policy"): (
        "Es del partner, no del cliente: RLS FORCE por ``partner_id`` (test_21, "
        "PARTNER_FORCE_TABLES). ``tenant_id`` dice a qué cliente va el tope."
    ),
    ("usage_ledger", "policy"): (
        "Libro del partner: RLS FORCE por ``partner_id`` (test_21, "
        "PARTNER_FORCE_TABLES). ``tenant_id`` dice qué cliente gastó el asiento."
    ),
    ("companion.threads", "policy"): (
        "Hilo del Companion de una persona del partner: RLS FORCE por "
        "``principal_id`` (0090). ``tenant_id`` es el cliente del que se habla, "
        "nullable, y nunca un ámbito de lectura."
    ),
    ("qa.threads", "policy"): (
        "QA Playground de los operadores de Auphere (ADR-020): RLS FORCE por "
        "``operator_id``; ``tenant_id`` es el cliente probado."
    ),
    ("qa.audit_log", "policy"): "Auditoría del QA Playground: RLS FORCE por ``operator_id``.",
    ("qa.side_effect_audit", "policy"): (
        "Efectos bloqueados del QA Playground: RLS FORCE por ``operator_id``."
    ),
    # ── otra política permisiva además de la de cliente ──────────────────
    ("agent_configs", "policy:agent_configs_reporting_read"): (
        "Solo para ``nexus_reporting`` y solo SELECT: el rol de informes de "
        "Auphere (test_23). nexus_app no la tiene."
    ),
    ("usage_records", "policy:usage_records_reporting_read"): (
        "Solo para ``nexus_reporting`` y solo SELECT (test_23)."
    ),
    ("device_client_links", "policy:device_client_links_machine_read"): (
        "Spec 002: la máquina del partner lee sus enlaces. La subconsulta lee "
        "``partner_devices``, que tiene RLS FORCE por partner y persona, así que "
        "no ve enlaces de máquinas ajenas (test_30)."
    ),
    # ── WITH CHECK implícito ─────────────────────────────────────────────
    **{
        (table, "with_check"): _CHECK_IMPLICITO
        for table in (
            "agents",
            "client_access",
            "client_phones",
            "client_push_deliveries",
            "client_push_events",
            "contact_notes",
            "conversation_events",
            "conversation_tags",
            "embed_audit_log",
            "inbox_reads",
            "invoice_lines",
            "invoices",
            "local_catalog_products",
            "messages",
            "payment_review_notices",
            "payment_reviews",
            "saved_replies",
            "tenant_model_bindings",
            "tenant_payments",
            "usage_records",
        )
    },
    # ── FK de una columna ────────────────────────────────────────────────
    **_fk(
        ("agent_memories", "agent_memories_customer_id_fkey", ""),
        ("agent_sales", "agent_sales_conversation_id_fkey", ""),
        ("agent_sales", "agent_sales_customer_id_fkey", ""),
        (
            "agent_sales",
            "agent_sales_invoice_line_id_fkey",
            "El destino es de facturación (ENABLE sin FORCE).",
        ),
        ("appointments", "appointments_customer_id_fkey", ""),
        (
            "appointments",
            "appointments_barber_id_fkey",
            "Apunta a un nodo del grafo, y el id lo escribe el MODELO (``barber_id`` de "
            "``booking.create_appointment``), sin comprobarlo antes: defecto abierto "
            "(informe A3 de la 047).",
        ),
        ("broadcast_recipients", "broadcast_recipients_broadcast_id_fkey", ""),
        ("broadcasts", "broadcasts_channel_id_fkey", ""),
        (
            "client_invitations",
            "client_invitations_accepted_membership_id_fkey",
            "Las dos tablas son de identidad, sin RLS (arriba).",
        ),
        ("contact_notes", "contact_notes_customer_id_fkey", ""),
        ("conversation_events", "conversation_events_conversation_id_fkey", ""),
        ("conversation_tags", "conversation_tags_conversation_id_fkey", ""),
        ("conversations", "conversations_channel_id_fkey", ""),
        ("conversations", "conversations_customer_id_fkey", ""),
        ("customers", "customers_kg_node_id_fkey", "Apunta a un nodo del grafo."),
        ("eval_cases", "eval_cases_dataset_id_fkey", ""),
        ("eval_run_results", "eval_run_results_run_id_fkey", ""),
        ("eval_run_results", "eval_run_results_case_id_fkey", ""),
        ("eval_runs", "eval_runs_dataset_id_fkey", ""),
        ("inbox_reads", "inbox_reads_conversation_id_fkey", ""),
        ("invoice_lines", "invoice_lines_invoice_id_fkey", "Facturación (ENABLE sin FORCE)."),
        ("kg_edges", "kg_edges_source_id_fkey", "Aristas del grafo (garantía 3)."),
        ("kg_edges", "kg_edges_target_id_fkey", "Aristas del grafo (garantía 3)."),
        ("local_argument_grants", "local_argument_grants_executable_id_fkey", ""),
        (
            "messages",
            "messages_conversation_id_fkey",
            "Tabla particionada: añadir la compuesta valida todas las particiones "
            "bajo ACCESS EXCLUSIVE (test_22, CASCADES_VIA_PARENT).",
        ),
        ("operator_notifications", "operator_notifications_audit_log_id_fkey", ""),
        ("owner_consultations", "owner_consultations_conversation_id_fkey", ""),
        ("payment_review_notices", "payment_review_notices_review_id_fkey", ""),
        (
            "payment_review_notices",
            "payment_review_notices_reviewer_conversation_id_fkey",
            "",
        ),
        ("payment_reviews", "payment_reviews_conversation_id_fkey", ""),
        ("payment_reviews", "payment_reviews_channel_id_fkey", ""),
        (
            "qa.side_effect_audit",
            "side_effect_audit_thread_id_fkey",
            "Las dos tablas son del QA Playground, por operador.",
        ),
        (
            "qa.threads",
            "threads_conversation_id_fkey",
            "El hilo del operador apunta a la conversación probada.",
        ),
        ("queue_entries", "queue_entries_customer_id_fkey", ""),
        (
            "queue_entries",
            "queue_entries_barber_id_fkey",
            "Apunta a un nodo del grafo, y el id lo escribe el MODELO (``barber_id`` de "
            "``queue.join_queue``), sin comprobarlo antes: defecto abierto (informe A3 "
            "de la 047).",
        ),
        ("whatsapp_opt_outs", "fk_optout_channel", ""),
    ),
}

#: Cuántas entradas tenía el inventario al escribirse (2026-10-26). Solo puede
#: bajar: quien arregla una tabla quita su entrada y baja este número; quien
#: quiera AÑADIR una tiene que subirlo, y eso se ve en la revisión.
INVENTORY_CEILING = 77

#: Las tablas del saver de LangGraph no las crea ninguna migración: aparecen al
#: arrancar el worker (o cuando un test de checkpoint las crea). Llevan la
#: política canónica y, además, la de mantenimiento del barrido de retención
#: (0066, test_19). Se excusan aparte porque en una base recién migrada no
#: existen y el detector de entradas podridas no puede exigirlas.
RUNTIME_CREATED_EXCEPTIONS: dict[tuple[str, str], str] = {
    (table, f"policy:{table}_maintenance"): (
        "GUC ``app.rls_maintenance``: solo el barrido de retención del scheduler "
        "(checkpoint_retention_cron) lo enciende; ninguna ruta de la API ni el "
        "runtime lo ponen (test_19)."
    )
    for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes")
}


# ── el barrido ──────────────────────────────────────────────────────────────


def violations(tables: dict[str, ClientTable]) -> dict[tuple[str, str], str]:
    """Todo lo que incumple la garantía 1, por ``(tabla, regla)``.

    Función pura sobre el catálogo leído: los tests de control de abajo la
    ejercen con tablas de prueba reales, así que es ESTE código el que se ve en
    rojo, no una copia."""
    out: dict[tuple[str, str], str] = {}
    for name, table in tables.items():
        if not table.rls_enabled:
            out[(name, "rls")] = f"{name}: sin RLS"
        elif not table.rls_forced:
            out[(name, "rls")] = f"{name}: RLS ENABLE sin FORCE"

        if table.rls_enabled:
            tenant_policies = [
                p
                for p in table.policies
                if p.command == "*"
                and p.permissive
                and normalise(p.using) == CANONICAL_TENANT_EXPR
                and p.roles & {"public", "nexus_app"}
            ]
            if not tenant_policies:
                found = ", ".join(f"{p.name}({p.command})" for p in table.policies) or "ninguna"
                out[(name, "policy")] = (
                    f"{name}: ninguna política es la de cliente canónica (hay: {found})"
                )
            else:
                if not any(p.is_canonical_tenant_policy for p in tenant_policies):
                    out[(name, "with_check")] = (
                        f"{name}: la política de cliente no lleva WITH CHECK explícito"
                    )
                for p in table.policies:
                    if p.permissive and p not in tenant_policies:
                        out[(name, f"policy:{p.name}")] = (
                            f"{name}: política permisiva «{p.name}» ({p.command}, "
                            f"{sorted(p.roles)}) además de la de cliente: abre la "
                            f"tabla por otro lado (USING {p.using!r})"
                        )

        for fk in table.foreign_keys:
            if fk.target in tables and not fk.is_composite_by_tenant:
                out[(name, f"fk:{fk.name}")] = (
                    f"{name}{list(fk.columns)} → {fk.target}{list(fk.target_columns)}: "
                    "FK de una columna entre tablas de cliente; tiene que ser "
                    "(tenant_id, x) → (tenant_id, id)"
                )
    return out


async def _sweep(session=None) -> dict[tuple[str, str], str]:
    if session is not None:
        return violations(await client_tables(session))
    async with get_sessionmaker()() as s:
        return violations(await client_tables(s))


def _offenders(found: dict[tuple[str, str], str]) -> list[str]:
    excused = LEGACY_EXCEPTIONS.keys() | RUNTIME_CREATED_EXCEPTIONS.keys()
    return sorted(msg for key, msg in found.items() if key not in excused)


def spec_047_tables() -> set[str]:
    """Las tablas que crea cualquier migración de la spec 047 en adelante.

    Se leen del código de la migración, no de la base: así una tabla nueva no
    puede colarse en el inventario aunque alguien la añada en el mismo cambio
    que la crea."""
    created: set[str] = set()
    sql = re.compile(
        r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:"?(\w+)"?\.)?"?(\w+)"?', re.IGNORECASE
    )
    orm = re.compile(r"""op\.create_table\(\s*["'](\w+)["']""")
    for path in VERSIONS.glob("*.py"):
        number = re.match(r"(\d{4})_", path.name)
        if number is None or int(number.group(1)) < FIRST_SPEC_047_MIGRATION:
            continue
        source = path.read_text(encoding="utf-8")
        for schema, table in sql.findall(source):
            created.add(table if schema in ("", "public") else f"{schema}.{table}")
        created.update(orm.findall(source))
    return created


# ── los tests ───────────────────────────────────────────────────────────────


async def test_every_client_table_is_forced_canonical_and_composite() -> None:
    found = await _sweep()
    assert found, "el barrido no encontró ni una de las excepciones conocidas — consulta rota"
    offenders = _offenders(found)
    assert not offenders, (
        "tablas de cliente que incumplen la garantía 1 (data-model.md):\n"
        + "\n".join(f"  - {o}" for o in offenders)
        + "\nUna tabla nueva se arregla; no entra en el inventario."
    )


async def test_no_spec_047_table_is_in_the_inventory() -> None:
    """Las tablas de la 047 cumplen; no se excusan."""
    created = spec_047_tables()
    # Control: el lector de migraciones ve la primera tabla de la 047.
    assert "jobs" in created, f"el lector de migraciones no ve ``jobs``: {sorted(created)}"
    excused = {table for table, _rule in LEGACY_EXCEPTIONS} | {
        table for table, _rule in RUNTIME_CREATED_EXCEPTIONS
    }
    smuggled = sorted(created & excused)
    assert not smuggled, f"tablas de la spec 047 en el inventario de excepciones: {smuggled}"


async def test_spec_047_tables_are_swept_and_clean() -> None:
    """Cada tabla de la 047 con ``tenant_id`` está en el barrido y sin nada."""
    async with get_sessionmaker()() as session:
        tables = await client_tables(session)
    found = violations(tables)
    created = spec_047_tables()
    swept = created & tables.keys()
    assert "jobs" in swept, "``jobs`` no aparece entre las tablas de cliente del barrido"
    dirty = sorted(msg for (table, _rule), msg in found.items() if table in swept)
    assert not dirty, f"tablas de la 047 que incumplen: {dirty}"
    # La FK de ``jobs`` al agente es la compuesta, y el barrido la ve.
    fks = {fk.name: fk for fk in tables["jobs"].foreign_keys}
    assert fks["fk_jobs_agent"].is_composite_by_tenant


async def test_the_inventory_only_shrinks() -> None:
    assert len(LEGACY_EXCEPTIONS) <= INVENTORY_CEILING, (
        f"el inventario tiene {len(LEGACY_EXCEPTIONS)} entradas y el techo es "
        f"{INVENTORY_CEILING}: el inventario no crece. Arregla la tabla."
    )


async def test_the_inventory_does_not_rot() -> None:
    """Una entrada que ya cumple —o cuya tabla ya no existe— se quita."""
    found = await _sweep()
    stale = sorted(f"{t} [{r}]" for t, r in LEGACY_EXCEPTIONS if (t, r) not in found)
    assert not stale, (
        "excepciones que ya no hacen falta (la tabla cumple o no existe): "
        f"{stale}. Quita la entrada y baja INVENTORY_CEILING."
    )
    async with get_sessionmaker()() as session:
        present = (await client_tables(session)).keys()
    stale_runtime = sorted(
        f"{t} [{r}]" for t, r in RUNTIME_CREATED_EXCEPTIONS if t in present and (t, r) not in found
    )
    assert not stale_runtime, f"excepciones de runtime que ya no hacen falta: {stale_runtime}"


async def test_the_inventory_agrees_with_test_21() -> None:
    """Lo que aquí se excusa por RLS es lo mismo que ``test_21`` justifica."""
    rls_excused = {t for t, r in LEGACY_EXCEPTIONS if r == "rls"}
    assert rls_excused <= set(PRE_TENANT_TABLES) | set(ENABLE_ONLY_TABLES)


# ── control del control: el barrido ve lo que dice ver ─────────────────────


_PROBES = (
    # ENABLE sin FORCE.
    "CREATE TABLE _g1_no_force (id uuid PRIMARY KEY, tenant_id uuid NOT NULL)",
    "ALTER TABLE _g1_no_force ENABLE ROW LEVEL SECURITY",
    "CREATE POLICY _g1_no_force_p ON _g1_no_force USING {p} WITH CHECK {p}",
    # FORCE, pero una política que no es la de cliente.
    "CREATE TABLE _g1_open (id uuid PRIMARY KEY, tenant_id uuid NOT NULL)",
    "ALTER TABLE _g1_open ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE _g1_open FORCE ROW LEVEL SECURITY",
    "CREATE POLICY _g1_open_p ON _g1_open USING (true) WITH CHECK (true)",
    # Correcta salvo por una FK de una columna hacia ``jobs``.
    "CREATE TABLE _g1_fk (id uuid PRIMARY KEY, tenant_id uuid NOT NULL, "
    " job_id uuid REFERENCES jobs (id))",
    "ALTER TABLE _g1_fk ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE _g1_fk FORCE ROW LEVEL SECURITY",
    "CREATE POLICY _g1_fk_p ON _g1_fk USING {p} WITH CHECK {p}",
    # Correcta salvo por una segunda política permisiva.
    "CREATE TABLE _g1_extra (id uuid PRIMARY KEY, tenant_id uuid NOT NULL)",
    "ALTER TABLE _g1_extra ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE _g1_extra FORCE ROW LEVEL SECURITY",
    "CREATE POLICY _g1_extra_p ON _g1_extra USING {p} WITH CHECK {p}",
    "CREATE POLICY _g1_extra_peek ON _g1_extra FOR SELECT USING (true)",
    # La forma correcta: FORCE, la canónica y la FK compuesta a ``jobs``.
    "CREATE TABLE _g1_ok (id uuid PRIMARY KEY, tenant_id uuid NOT NULL, job_id uuid, "
    " CONSTRAINT _g1_ok_job FOREIGN KEY (tenant_id, job_id) REFERENCES jobs (tenant_id, id))",
    "ALTER TABLE _g1_ok ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE _g1_ok FORCE ROW LEVEL SECURITY",
    "CREATE POLICY _g1_ok_p ON _g1_ok USING {p} WITH CHECK {p}",
)
_POLICY_SQL = "(tenant_id = (NULLIF(current_setting('app.tenant_id', true), ''))::uuid)"


async def probe_violations() -> dict[tuple[str, str], str]:
    """Crea las tablas de prueba en una transacción que se deshace y devuelve lo
    que el barrido dice de ellas (solo de ellas)."""
    async with get_sessionmaker()() as session:
        for statement in _PROBES:
            await session.execute(sa.text(statement.replace("{p}", _POLICY_SQL)))
        found = await _sweep(session)
        await session.rollback()
    return {key: msg for key, msg in found.items() if key[0].startswith("_g1_")}


async def test_the_sweep_catches_each_kind_of_violation() -> None:
    """Un guardián que nunca falla no protege nada.

    Cuatro tablas reales, cada una con un solo defecto, y una correcta. El
    barrido tiene que señalar exactamente los cuatro defectos y nada de la
    correcta: lo primero prueba que mira donde debe; lo segundo, que no
    exige algo que la forma de ``data-model.md`` no cumple."""
    found = await probe_violations()
    assert set(found) == {
        ("_g1_no_force", "rls"),
        ("_g1_open", "policy"),
        ("_g1_fk", "fk:_g1_fk_job_id_fkey"),
        ("_g1_extra", "policy:_g1_extra_peek"),
    }, found
    assert not _offenders({k: v for k, v in found.items() if k[0] == "_g1_ok"})
