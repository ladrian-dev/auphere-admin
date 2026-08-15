#!/usr/bin/env python3
"""WP-26 · Importa en Aurora el paquete que produjo ``wp26_export.py``.

Corre DENTRO de una task efímera de ECS (Aurora no es alcanzable desde
fuera del VPC). El arranque lo hace el ``command`` de la task: baja el
paquete de S3, lo extrae y ejecuta esto.

## Lo que hace distinto a un ``psql -f dump.sql``

1. **Carga con el GUC del tenant puesto.** Las tablas con datos de cliente
   tienen RLS ``ENABLE`` + ``FORCE``, y FORCE alcanza también al dueño.
   Cada fichero entra en su propia transacción con
   ``SET LOCAL app.tenant_id``, así que el ``WITH CHECK`` de la policy
   comprueba fila a fila que la fila pertenece a ese tenant. Es la
   diferencia entre importar *con* aislamiento y importar *saltándoselo*:
   un import que "funciona" con ``app.rls_maintenance='on'`` no ha
   comprobado nada.
2. **Lista de columnas explícita.** El CSV lleva cabecera y el ``COPY``
   nombra las columnas. Casar por posición entre un origen en 0060 y un
   destino en 0079 mete valores en la columna de al lado sin dar error.
3. **Verifica contra el manifiesto** y sale distinto de cero si una sola
   tabla no cuadra. Una migración que dice "ok" sin contar es una
   migración que nadie ha comprobado.
4. **Idempotente**: ``ON CONFLICT DO NOTHING`` vía tabla temporal. Repetir
   el import tras un fallo a media carga no duplica ni revienta.

## Vuelta atrás

``--rollback`` borra exactamente lo que este script mete, en el orden
inverso y acotado a los tenants del manifiesto. No es un ``TRUNCATE``:
un entorno con otros datos (staging tiene 50 tenants sintéticos) tiene que
quedar como estaba.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

PKG = pathlib.Path(os.environ.get("WP26_PKG", "/tmp/wp26"))


def _url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("ERROR: falta DATABASE_URL (viene del secreto nexus/<ws>/app)")
    return url


def run_sql(sql: str, *, quiet: bool = False, maintenance: bool = False) -> str:
    # El GUC va por PGOPTIONS y no como ``SET ...;`` delante del SELECT: con
    # ``-c "SET x; SELECT y"`` psql imprime también la línea "SET" y el
    # recuento se lee mal — el primer intento de esta verificación reventó
    # justo así, con int('SET\n0').
    env = dict(os.environ)
    if maintenance:
        env["PGOPTIONS"] = "-c app.rls_maintenance=on"
    res = subprocess.run(
        ["psql", _url(), "-v", "ON_ERROR_STOP=1", "-At", "-c", sql],
        capture_output=True,
        text=True,
        env=env,
    )
    if res.returncode != 0:
        if quiet:
            return ""
        sys.exit(f"ERROR SQL:\n{sql[:400]}\n---\n{res.stderr}")
    return res.stdout.strip()


def run_script(body: str, label: str) -> None:
    """Ejecuta un bloque con ``\\copy`` dentro (necesita el meta-comando de
    psql, así que va por fichero y no por ``-c``)."""
    tmp = PKG / "_step.sql"
    tmp.write_text(body)
    res = subprocess.run(
        ["psql", _url(), "-v", "ON_ERROR_STOP=1", "-f", str(tmp)],
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        sys.exit(f"ERROR importando {label}:\n{res.stderr}")


def check_connector_catalog(manifest: dict) -> None:
    """El catálogo ``connectors`` NO viaja: lo siembran las migraciones y en
    AWS tiene OTROS uuid. Se comprueba ANTES de escribir nada que cada slug
    que usan los tenants existe aquí — un conector que falte es un cliente
    que pierde una integración, y descubrirlo a mitad de la carga deja la
    base a medias en plena ventana de corte."""
    faltan = []
    for _old_id, slug in (manifest.get("connector_map") or {}).items():
        if not run_sql(f"SELECT id FROM connectors WHERE slug = '{slug}'"):
            faltan.append(slug)
    if faltan:
        sys.exit(
            "ERROR: estos conectores no existen en el catálogo del destino: "
            f"{faltan}\nSiémbralos antes de importar, o quita del paquete los "
            "tenants que los usan. No se ha escrito nada."
        )


def import_all(manifest: dict) -> None:
    print(
        f"==> importando paquete '{manifest['target']}' "
        f"({', '.join(manifest['tenant_slugs'])})"
    )
    check_connector_catalog(manifest)
    for table in manifest["order"]:
        info = manifest["tables"][table]
        cols = ", ".join(f'"{c}"' for c in info["columns"])
        for f in info["files"]:
            if not f["rows"]:
                continue
            path = PKG / f["file"]
            tenant = f["tenant_id"]
            # Tabla temporal + INSERT ... ON CONFLICT DO NOTHING en vez de
            # COPY directo: COPY no admite ON CONFLICT, y sin idempotencia
            # un reintento tras un fallo parcial obliga a limpiar a mano
            # justo cuando hay prisa.
            body = "BEGIN;\n"
            if tenant:
                body += f"SET LOCAL app.tenant_id = '{tenant}';\n"
            body += (
                f"CREATE TEMP TABLE _stage (LIKE {table} INCLUDING DEFAULTS) "
                f"ON COMMIT DROP;\n"
                f"\\copy _stage ({cols}) FROM '{path}' CSV HEADER\n"
            )
            # Traducción de ids de catálogo: se hace sobre el stage, con la
            # fila ya cargada y antes de tocar la tabla real.
            if table == "public.tenant_connectors":
                for old_id, slug in (manifest.get("connector_map") or {}).items():
                    body += (
                        f"UPDATE _stage SET connector_id = "
                        f"(SELECT id FROM connectors WHERE slug = '{slug}') "
                        f"WHERE connector_id = '{old_id}';\n"
                    )
                # Si algo quedó sin traducir, se para aquí dentro de la
                # transacción: mejor un ROLLBACK que una FK rota o, peor, un
                # conector apuntando al catálogo equivocado.
                body += (
                    "DO $$ BEGIN IF EXISTS (SELECT 1 FROM _stage s WHERE NOT EXISTS "
                    "(SELECT 1 FROM connectors c WHERE c.id = s.connector_id)) THEN "
                    "RAISE EXCEPTION 'connector_id sin traducir en el paquete'; "
                    "END IF; END $$;\n"
                )
            body += (
                f"INSERT INTO {table} ({cols}) SELECT {cols} FROM _stage "
                f"ON CONFLICT DO NOTHING;\n"
                "COMMIT;\n"
            )
            run_script(body, f"{table} [{f['file']}]")
        print(f"    {table:<28} {info['rows']:>7} filas")


def verify(manifest: dict) -> int:
    """Cuenta en el destino con el MISMO criterio del origen."""
    print("\n==> verificación")
    tenants = (
        "ARRAY[" + ",".join(f"'{t}'" for t in manifest["tenant_ids"]) + "]::uuid[]"
    )
    checks = {
        "public.partners": f"SELECT count(*) FROM partners WHERE id = ANY({_arr(manifest['partner_ids'])})",
        "public.billing_plans": "SELECT count(*) FROM billing_plans WHERE id = ANY("
        f"{_arr(manifest.get('billing_plan_ids') or [])})",
        "public.tenants": f"SELECT count(*) FROM tenants WHERE id = ANY({tenants})",
        "public.partner_tenants": f"SELECT count(*) FROM partner_tenants WHERE tenant_id = ANY({tenants})",
        "public.api_keys": f"SELECT count(*) FROM api_keys WHERE partner_id = ANY({_arr(manifest['partner_ids'])})",
    }
    for t in (
        "channels",
        "customers",
        "conversations",
        "messages",
        "agent_configs",
        "tenant_connectors",
        "tenant_credentials",
    ):
        checks[f"public.{t}"] = (
            f"SELECT count(*) FROM {t} WHERE tenant_id = ANY({tenants})"
        )
    for t in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
        checks[f"public.{t}"] = (
            f"SELECT count(*) FROM {t} WHERE tenant_id = ANY({tenants})"
        )
    emails = manifest.get("auth_emails") or []
    if emails:
        e = "ARRAY[" + ",".join(f"'{x}'" for x in emails) + "]::text[]"
        checks["auth.user"] = f'SELECT count(*) FROM auth."user" WHERE email = ANY({e})'
        checks["auth.account"] = (
            f"SELECT count(*) FROM auth.account WHERE user_id IN "
            f'(SELECT id FROM auth."user" WHERE email = ANY({e}))'
        )

    # La lectura va con la RLS DESACTIVADA para el contador (maintenance):
    # aquí se cuenta, no se escribe, y sin el GUC estas tablas devolverían
    # cero y el informe diría que no se importó nada.
    bad = 0
    for table, sql in checks.items():
        expected = int(manifest["tables"].get(table, {}).get("rows", 0))
        got = int(run_sql(sql, maintenance=True) or 0)
        mark = "ok " if got == expected else "MAL"
        if got != expected:
            bad += 1
        print(f"    [{mark}] {table:<28} esperado={expected:<7} obtenido={got}")

    # Comprobación que no es de recuento: el trigger de la 0065 tiene que
    # haber derivado el tenant de CADA checkpoint. Un NULL aquí significa
    # memoria de agente invisible bajo RLS — importada y perdida a la vez.
    huerfanos = int(
        run_sql(
            "SELECT count(*) FROM checkpoints WHERE tenant_id IS NULL", maintenance=True
        )
        or 0
    )
    print(
        f"    [{'ok ' if not huerfanos else 'MAL'}] checkpoints sin tenant_id derivado: {huerfanos}"
    )
    bad += 1 if huerfanos else 0
    bad += verify_fernet()
    return bad


def verify_fernet() -> int:
    """¿Descifra este entorno las credenciales que acaban de entrar?

    Es la comprobación más importante del corte y la que NO se nota sola.
    ``tenant_credentials.encrypted_payload`` va cifrado con
    ``NEXUS_FERNET_KEY``; si la de AWS no es byte a byte la de Railway, el
    import termina en verde, los servicios arrancan sin una queja y el
    fallo aparece la primera vez que un agente intenta usar una
    integración — con el cliente delante y sin traza que apunte aquí.

    Se comprueba descifrando de verdad, no comparando claves: la clave
    correcta es la que abre el dato.

    ``convert_from(..., 'UTF8')`` y no la columna a secas: ``BYTEA`` sale
    de psql en el hexadecimal de Postgres (``\\x676141…``), y descifrar esa
    cadena falla SIEMPRE — con la clave buena y con la mala. La primera
    versión de esta función leía así y daba 0/N contra un entorno sano: una
    comprobación que sólo sabe decir "mal" no comprueba nada. El token
    Fernet es base64url ASCII, así que convertirlo a texto lo devuelve tal
    cual se escribió.
    """
    key = os.environ.get("NEXUS_FERNET_KEY")
    if not key:
        print("    [MAL] NEXUS_FERNET_KEY no está en el entorno")
        return 1
    payloads = run_sql(
        "SELECT convert_from(encrypted_payload, 'UTF8') FROM tenant_credentials "
        "WHERE encrypted_payload IS NOT NULL",
        maintenance=True,
    ).splitlines()
    if not payloads:
        print("    [ok ] no hay credenciales cifradas que comprobar")
        return 0
    try:
        from cryptography.fernet import Fernet, InvalidToken
    except ImportError:
        print("    [MAL] falta 'cryptography' para comprobar el descifrado")
        return 1
    f = Fernet(key.encode())
    ok = 0
    for raw in payloads:
        try:
            f.decrypt(raw.encode())
            ok += 1
        except (InvalidToken, ValueError):
            pass
    mark = "ok " if ok == len(payloads) else "MAL"
    print(f"    [{mark}] credenciales que descifran: {ok}/{len(payloads)}")
    if ok != len(payloads):
        print("           → NEXUS_FERNET_KEY NO es la de origen. Los conectores")
        print("             migrados quedarán ilegibles sin dar ningún error.")
        return 1
    return 0


def _arr(ids: list[str]) -> str:
    return (
        "ARRAY[" + ",".join(f"'{i}'" for i in ids) + "]::uuid[]"
        if ids
        else "ARRAY[]::uuid[]"
    )


def rollback(manifest: dict) -> None:
    """Deshace SOLO lo de este paquete. No es un TRUNCATE: staging tiene
    otros datos que deben sobrevivir."""
    print("==> ROLLBACK — borrando lo importado por este paquete")
    tenants = _arr(manifest["tenant_ids"])
    partners = _arr(manifest["partner_ids"])
    steps = [
        f"DELETE FROM checkpoint_writes WHERE tenant_id = ANY({tenants})",
        f"DELETE FROM checkpoint_blobs  WHERE tenant_id = ANY({tenants})",
        f"DELETE FROM checkpoints       WHERE tenant_id = ANY({tenants})",
        f"DELETE FROM tenant_credentials WHERE tenant_id = ANY({tenants})",
        f"DELETE FROM tenant_connectors WHERE tenant_id = ANY({tenants})",
        f"DELETE FROM agent_configs     WHERE tenant_id = ANY({tenants})",
        f"DELETE FROM messages          WHERE tenant_id = ANY({tenants})",
        f"DELETE FROM conversations     WHERE tenant_id = ANY({tenants})",
        f"DELETE FROM customers         WHERE tenant_id = ANY({tenants})",
        f"DELETE FROM channels          WHERE tenant_id = ANY({tenants})",
        f"DELETE FROM partner_tenants   WHERE tenant_id = ANY({tenants})",
        f"DELETE FROM api_keys          WHERE partner_id = ANY({partners})",
        f"DELETE FROM tenants           WHERE id = ANY({tenants})",
        f"DELETE FROM partners          WHERE id = ANY({partners})",
        # Después de ``tenants``, que es quien lo referencia.
        f"DELETE FROM billing_plans     WHERE id = ANY({_arr(manifest.get('billing_plan_ids') or [])})",
    ]
    emails = manifest.get("auth_emails") or []
    if emails:
        e = "ARRAY[" + ",".join(f"'{x}'" for x in emails) + "]::text[]"
        steps += [
            f'DELETE FROM auth.account WHERE user_id IN (SELECT id FROM auth."user" WHERE email = ANY({e}))',
            f'DELETE FROM auth."user" WHERE email = ANY({e})',
        ]
    # Un solo bloque: si el rollback se queda a medias deja un estado peor
    # que el que venía a arreglar.
    body = (
        "BEGIN;\nSET LOCAL app.rls_maintenance='on';\n"
        + ";\n".join(steps)
        + ";\nCOMMIT;\n"
    )
    run_script(body, "rollback")
    print("    hecho")


def main() -> None:
    manifest = json.loads((PKG / "manifest.json").read_text())
    if "--rollback" in sys.argv:
        rollback(manifest)
        return
    if "--verify-only" in sys.argv:
        sys.exit(1 if verify(manifest) else 0)
    import_all(manifest)
    bad = verify(manifest)
    if bad:
        print(f"\n!! {bad} comprobaciones NO cuadran — la importación NO es buena")
        sys.exit(1)
    print("\n==> todo cuadra")


if __name__ == "__main__":
    main()
