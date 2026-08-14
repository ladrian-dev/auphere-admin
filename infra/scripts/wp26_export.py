#!/usr/bin/env python3
"""WP-26 · Exporta de Railway el subconjunto que se migra a AWS.

Railway sigue siendo producción mientras esto corre: **todo lo que hace
este script es leer**. No abre transacción de escritura, no bloquea nada y
no toca una sola fila.

Se ejecuta a través del CLI de Railway, que inyecta las variables del
servicio en el proceso LOCAL:

    railway run --service Postgres -- python3 infra/scripts/wp26_export.py prod

Por eso los ``\\copy`` escriben en el disco de aquí y no en el contenedor.

## Por qué se exporta por columnas y no con ``pg_dump``

Railway va por ``0060`` y AWS por ``0079``: 19 migraciones de diferencia.
Un ``pg_dump --data-only`` emite ``COPY tabla FROM stdin`` **sin lista de
columnas**, que casa por posición — con una columna nueva en medio del
destino, los valores se desplazan y entran en la columna equivocada sin
error. Aquí la lista de columnas es explícita y es la INTERSECCIÓN
origen ∩ destino, calculada contra la base local (que ya está en 0079 y
es el mismo esquema que tendrá AWS tras alembic).

Las columnas que sólo existen en el destino se dejan a su default a
propósito, y son inofensivas — se comprobó una a una: ``tenants.tier``,
``agent_configs.grader_mode`` / ``grader_sample_rate`` y el
``tenant_id`` de las tres tablas de checkpoints. Ninguna es NOT NULL sin
default, y el ``tenant_id`` **lo rellena el trigger
``checkpoint_derive_tenant()`` de la 0065** derivándolo del ``thread_id``,
que además valida el formato: un hilo que no empiece por
``tenant:<uuid>:`` se rechaza en la base en vez de entrar sin dueño.

## Los dos destinos no llevan lo mismo

- ``prod``    — los clientes reales y el usuario del panel de Auphere.
- ``staging`` — el usuario revisor de Meta y dos tenants de datos
  ficticios. Sirve para ensayar el procedimiento y para las revisiones de
  la Meta App **sin meter datos personales de clientes reales** en un
  entorno que no los necesita.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

# ── qué va a cada entorno ────────────────────────────────────────────────────

PLANS: dict[str, dict[str, object]] = {
    "prod": {
        "tenants": ["barbersupply", "mouna", "newair"],
        "auth_emails": ["contacto@auphere.com"],
        "note": "clientes reales de los partners",
    },
    "staging": {
        # Ficticios los dos: el piloto Clínica Boreal y la demo que se
        # enseña en las revisiones de la Meta App.
        "tenants": ["clinica-boreal", "meta-review-demo"],
        "auth_emails": ["meta-reviewer@auphere.com"],
        "note": "datos NO reales + el usuario revisor de Meta",
        # ``googlecalendar`` existe en el catálogo de Railway pero NINGUNA
        # migración lo siembra: se creó a mano para el piloto. En AWS no
        # está, así que su conexión no puede viajar. Se declara aquí en vez
        # de dejar que el importador la salte en silencio — un conector que
        # desaparece sin avisar es una integración rota que nadie busca.
        # No afecta a prod: allí sólo se usan whatsapp_meta, woocommerce y
        # amigable_cobro, y los tres están en el catálogo del destino.
        "skip_connector_slugs": ["googlecalendar"],
    },
}

# Orden de exportación = orden de importación. Lo imponen las FKs que la
# 0077 puso en CASCADE: un hijo antes que su padre falla, y peor, un
# padre borrado después se lleva al hijo por delante.
# (tabla, WHERE, scope)
#
# ``scope='tenant'`` genera **un fichero por tenant**. No es manía: esas
# tablas tienen RLS ENABLE + FORCE, y el importador las carga dentro de una
# transacción con ``SET LOCAL app.tenant_id``. Así el ``WITH CHECK`` de la
# policy comprueba fila a fila que cada una cae en el tenant que dice — si
# un thread_id perteneciera a otro cliente, la carga FALLA en vez de
# colarse. La alternativa cómoda es ``app.rls_maintenance='on'``, que la
# base acepta pero desactiva justo esa comprobación en la única operación
# de la vida del sistema que mezcla datos de varios clientes a la vez.
TABLES: list[tuple[str, str, str]] = [
    ("partners", "id = ANY(:partners)", "global"),
    # ANTES que ``tenants``: ``tenants.billing_plan_id`` apunta aquí y en
    # AWS la tabla está VACÍA (ningún seed la puebla). No es catálogo
    # generado, son los planes comerciales pactados con cada partner —
    # mouna y newair, los dos tenants con más tráfico, los referencian.
    # Sin esta línea el import de ``tenants`` falla por FK... o peor, pasa
    # con el plan a NULL y el cliente queda sin plan de cobro.
    (
        "billing_plans",
        "id IN (SELECT billing_plan_id FROM tenants WHERE id = ANY(:tenants))",
        "global",
    ),
    ("tenants", "id = ANY(:tenants)", "global"),
    ("partner_tenants", "tenant_id = :tenant", "tenant"),
    ("api_keys", "partner_id = ANY(:partners)", "global"),
    ("channels", "tenant_id = :tenant", "tenant"),
    ("customers", "tenant_id = :tenant", "tenant"),
    ("conversations", "tenant_id = :tenant", "tenant"),
    ("messages", "tenant_id = :tenant", "tenant"),
    ("agent_configs", "tenant_id = :tenant", "tenant"),
    ("tenant_connectors", "tenant_id = :tenant AND :skip_connectors", "tenant"),
    ("tenant_credentials", "tenant_id = :tenant", "tenant"),
    # Los checkpoints se filtran por el prefijo del thread_id, que es donde
    # vive el tenant en estas tablas de LangGraph (formato de la 0065).
    ("checkpoints", "substring(thread_id from 8 for 36)::uuid = :tenant", "tenant"),
    (
        "checkpoint_blobs",
        "substring(thread_id from 8 for 36)::uuid = :tenant",
        "tenant",
    ),
    (
        "checkpoint_writes",
        "substring(thread_id from 8 for 36)::uuid = :tenant",
        "tenant",
    ),
]

# El panel de operador. Sin esto nadie puede entrar en el AWS nuevo: no
# hay alta de usuarios por fuera de better-auth.
AUTH_TABLES: list[tuple[str, str, str]] = [
    ('auth."user"', "email = ANY(:emails)", "global"),
    (
        "auth.account",
        'user_id IN (SELECT id FROM auth."user" WHERE email = ANY(:emails))',
        "global",
    ),
    # ``auth.session`` NO se exporta: las cookies están atadas al dominio
    # viejo y caducan solas. Arrastrarlas sólo mueve sesiones muertas.
]

# Fuera del repo por defecto: esto lleva datos personales de clientes y no
# puede acabar en git ni por accidente.
DEST = pathlib.Path(os.environ.get("WP26_OUT", "/tmp/wp26-export"))


def psql(sql: str, *, tuples_only: bool = True) -> str:
    url = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
    if not url:
        sys.exit(
            "ERROR: sin DATABASE_PUBLIC_URL. Ejecuta con `railway run --service Postgres --`"
        )
    cmd = ["psql", url, "-v", "ON_ERROR_STOP=1", "-c", sql]
    if tuples_only:
        cmd.insert(2, "-At")
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(f"ERROR psql:\n{out.stderr}")
    return out.stdout


def local_columns() -> dict[str, list[str]]:
    """Columnas del DESTINO, leídas de la base local en 0079."""
    env = {**os.environ, "PGPASSWORD": os.environ.get("LOCAL_PGPASSWORD", "nexus")}
    sql = """
        SELECT table_schema||'.'||table_name||':'||column_name
          FROM information_schema.columns
         WHERE table_schema IN ('public','auth')
         ORDER BY table_schema, table_name, ordinal_position
    """
    out = subprocess.run(
        [
            "psql",
            "-h",
            os.environ.get("LOCAL_PGHOST", "localhost"),
            "-p",
            os.environ.get("LOCAL_PGPORT", "5433"),
            "-U",
            "nexus",
            "-d",
            "nexus",
            "-At",
            "-c",
            sql,
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    if out.returncode != 0:
        sys.exit(
            "ERROR: no se pudo leer el esquema DESTINO de la base local.\n"
            "Levanta `docker compose up -d postgres` y aplica `alembic upgrade head`.\n"
            + out.stderr
        )
    cols: dict[str, list[str]] = {}
    for line in out.stdout.splitlines():
        if ":" not in line:
            continue
        table, col = line.rsplit(":", 1)
        cols.setdefault(table, []).append(col)
    return cols


def source_columns(table: str) -> list[str]:
    schema, _, name = table.replace('"', "").rpartition(".")
    schema = schema or "public"
    rows = psql(
        f"SELECT column_name FROM information_schema.columns "
        f"WHERE table_schema='{schema}' AND table_name='{name}' ORDER BY ordinal_position"
    )
    return [r for r in rows.splitlines() if r]


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else ""
    if target not in PLANS:
        sys.exit(f"uso: {sys.argv[0]} prod|staging")
    plan = PLANS[target]
    slugs: list[str] = plan["tenants"]  # type: ignore[assignment]
    emails: list[str] = plan["auth_emails"]  # type: ignore[assignment]

    print(f"==> destino {target}: {plan['note']}")
    print(f"    tenants: {', '.join(slugs)}")

    # Los ids salen de los slugs: un uuid copiado a mano es un error que no
    # se ve hasta que el import deja una tabla vacía sin fallar.
    slug_list = ",".join(f"'{s}'" for s in slugs)
    rows = psql(
        f"SELECT id, slug FROM tenants WHERE slug IN ({slug_list}) ORDER BY slug"
    )
    found = dict(line.split("|") for line in rows.splitlines() if "|" in line)
    if len(found) != len(slugs):
        sys.exit(
            f"ERROR: esperaba {len(slugs)} tenants y encontré {len(found)}: {list(found.values())}"
        )
    tenant_ids = list(found.keys())

    partner_rows = psql(
        f"SELECT DISTINCT partner_id FROM partner_tenants "
        f"WHERE tenant_id = ANY(ARRAY[{','.join(repr(t) for t in tenant_ids)}]::uuid[])"
    )
    partner_ids = [r for r in partner_rows.splitlines() if r]
    print(f"    partners implicados: {len(partner_ids)}")

    DEST.mkdir(parents=True, exist_ok=True)
    dst_cols = local_columns()
    manifest: dict[str, dict[str, object]] = {}

    def arr(ids: list[str]) -> str:
        return "ARRAY[" + ",".join(f"'{i}'" for i in ids) + "]::uuid[]"

    def emails_arr() -> str:
        return "ARRAY[" + ",".join(f"'{e}'" for e in emails) + "]::text[]"

    # ``connectors`` NO se migra —lo siembran las migraciones en AWS— pero
    # los UUID son OTROS allí, así que ``tenant_connectors.connector_id``
    # apunta a filas que no existen. Se exporta el mapa id→slug para que el
    # importador lo traduzca. Se descubrió porque el import falló con
    # "violates foreign key constraint fk_tc_connector"; sin el mapa, la
    # única salida habría sido migrar el catálogo entero y pisar en AWS
    # entradas más nuevas que las de Railway.
    skip_slugs: list[str] = plan.get("skip_connector_slugs") or []  # type: ignore[assignment]
    skip_sql = (
        "connector_id NOT IN (SELECT id FROM connectors WHERE slug = ANY(ARRAY["
        + ",".join(f"'{s}'" for s in skip_slugs)
        + "]::text[]))"
        if skip_slugs
        else "true"
    )

    conn_rows = psql(
        "SELECT c.id, c.slug FROM connectors c WHERE c.id IN "
        f"(SELECT connector_id FROM tenant_connectors WHERE tenant_id = ANY({arr(tenant_ids)}))"
        + (
            f" AND c.slug <> ALL(ARRAY[{','.join(repr(s) for s in skip_slugs)}]::text[])"
            if skip_slugs
            else ""
        )
    )
    connector_map = dict(
        line.split("|") for line in conn_rows.splitlines() if "|" in line
    )
    print(f"    conectores a remapear por slug: {sorted(connector_map.values())}")
    if skip_slugs:
        omitidas = psql(
            f"SELECT count(*) FROM tenant_connectors WHERE tenant_id = ANY({arr(tenant_ids)}) "
            f"AND NOT ({skip_sql})"
        ).strip()
        print(
            f"    OMITIDAS a propósito: {omitidas} conexiones de {skip_slugs} "
            f"(no existen en el catálogo del destino)"
        )

    plan_rows = psql(
        f"SELECT DISTINCT billing_plan_id FROM tenants "
        f"WHERE id = ANY({arr(tenant_ids)}) AND billing_plan_id IS NOT NULL"
    )
    billing_plan_ids = [r for r in plan_rows.splitlines() if r]

    url = os.environ.get("DATABASE_PUBLIC_URL") or os.environ["DATABASE_URL"]

    for table, where, scope in TABLES + AUTH_TABLES:
        key = (table if "." in table else f"public.{table}").replace('"', "")
        src = source_columns(table)
        dst = dst_cols.get(key, [])
        if not dst:
            sys.exit(f"ERROR: la tabla {key} no existe en el destino")
        common = [c for c in src if c in dst]
        dropped = [c for c in src if c not in dst]
        added = [c for c in dst if c not in src]
        quoted = ", ".join(f'"{c}"' for c in common)

        # ``global`` → un fichero; ``tenant`` → uno por cliente, que es lo
        # que permite importar con el GUC puesto y la RLS comprobando.
        segments = [(None, "")] if scope == "global" else [(t, t) for t in tenant_ids]
        files: list[dict[str, object]] = []
        total = 0
        for tenant, suffix in segments:
            clause = (
                where.replace(":tenants", arr(tenant_ids))
                .replace(":partners", arr(partner_ids))
                .replace(":emails", emails_arr())
                .replace(":tenant", f"'{tenant}'::uuid" if tenant else "NULL")
                .replace(":skip_connectors", skip_sql)
            )
            name = (
                f"{key.replace('.', '__')}" + (f"__{suffix}" if suffix else "") + ".csv"
            )
            out_file = DEST / name
            sql = f"\\copy (SELECT {quoted} FROM {table} WHERE {clause}) TO '{out_file}' CSV HEADER"
            res = subprocess.run(
                ["psql", url, "-v", "ON_ERROR_STOP=1", "-c", sql],
                capture_output=True,
                text=True,
            )
            if res.returncode != 0:
                sys.exit(f"ERROR exportando {table}:\n{res.stderr}")
            # El recuento se pide a la base, NO se cuentan líneas del CSV: un
            # ``system_prompt_rendered`` con saltos de línea ocupa varias
            # líneas de fichero, y con ese número la verificación posterior
            # daría por buena una importación incompleta.
            n = int(psql(f"SELECT count(*) FROM {table} WHERE {clause}").strip() or 0)
            files.append({"file": name, "tenant_id": tenant, "rows": n})
            total += n

        manifest[key] = {
            "scope": scope,
            "rows": total,
            "columns": common,
            "dropped": dropped,
            "only_in_dest": added,
            "files": files,
        }
        extra = f"  (-{len(dropped)} cols del origen)" if dropped else ""
        print(f"    {key:<28} {total:>7} filas{extra}")

    (DEST / "manifest.json").write_text(
        json.dumps(
            {
                "target": target,
                "tenant_ids": tenant_ids,
                "tenant_slugs": slugs,
                "partner_ids": partner_ids,
                "auth_emails": emails,
                # id_de_Railway → slug. El importador lo traduce al id que
                # tenga el catálogo en AWS.
                "connector_map": connector_map,
                "billing_plan_ids": billing_plan_ids,
                "order": [
                    (t if "." in t else f"public.{t}").replace('"', "")
                    for t, _, _ in TABLES + AUTH_TABLES
                ],
                "tables": manifest,
            },
            indent=2,
        )
    )
    total = sum(int(v["rows"]) for v in manifest.values())  # type: ignore[arg-type]
    print(f"==> {total} filas en {DEST}/  ·  manifiesto escrito")
    print("    Railway no ha sido modificado: sólo se han hecho SELECTs.")


if __name__ == "__main__":
    main()
