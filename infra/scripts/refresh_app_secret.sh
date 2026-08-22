#!/usr/bin/env bash
# Refresca ``nexus/<ws>/app`` tras una rotación de Aurora, SIN perder claves.
#
# Por qué existe, aparte de populate_app_secret.sh: ese compone el JSON
# **desde cero** con una lista fija. Sirve para el primer llenado, pero en
# un refresco borra en silencio cualquier clave que se haya añadido a las
# definiciones de tarea después — y una task cuya definición pide una clave
# que no está en el secreto **no arranca**:
#
#   ResourceInitializationError: ... did not contain json key
#   NEXUS_CONSOLE_ENABLED
#
# Pasó de verdad el 2026-08-19: la rotación de Aurora obligó a repoblar y
# el repoblado se llevó las 3 claves de la consola. Aurora rota cada 7
# días, así que esto vuelve solo.
#
# Qué hace distinto:
#   1. PARTE del secreto que ya hay — nunca borra una clave.
#   2. Reescribe SOLO la contraseña dentro de las 4 URLs de base de datos.
#      Los hosts los saca de las propias URLs, así que **no necesita
#      Terraform**: ni workspace correcto, ni nombres de output, que es
#      justo donde se rompen estas cosas cuando corren con prisa.
#   3. Antes de escribir comprueba que están TODAS las claves que piden
#      las definiciones de tarea del clúster. Las que falten las arrastra
#      de la versión AWSPREVIOUS del propio secreto.
#   4. Si aun así falta alguna, ABORTA nombrándola sin escribir nada.
#
# No imprime ningún valor: sólo nombres de claves.
#
# Uso:  AWS_PROFILE=nexus ./infra/scripts/refresh_app_secret.sh prod

set -euo pipefail

WS="${1:-}"
if [[ "$WS" != "staging" && "$WS" != "prod" ]]; then
  echo "uso: $0 staging|prod" >&2
  exit 2
fi
REGION="${AWS_REGION:-eu-south-2}"

echo "==> claves que exigen las definiciones de tarea de nexus-$WS"
REQ=$(mktemp); trap 'rm -f "$REQ"' EXIT
for td in api runner egress metering scheduler migrate; do
  aws ecs describe-task-definition --task-definition "nexus-$WS-$td" --region "$REGION" \
    --query 'taskDefinition.containerDefinitions[].secrets[].name' --output text 2>/dev/null \
    | tr '\t' '\n' || true
done | sed '/^$/d' | sort -u > "$REQ"
echo "    $(wc -l < "$REQ" | tr -d ' ') claves requeridas"

python3 - "$REGION" "nexus/$WS/app" "$REQ" <<'PY'
import json, re, subprocess, sys, urllib.parse

region, secret_id, req_file = sys.argv[1:4]
DB_KEYS = ("NEXUS_DATABASE_URL", "NEXUS_DATABASE_URL_DIRECT",
           "NEXUS_DATABASE_URL_RO", "DATABASE_URL")


def aws(*a):
    return subprocess.run(["aws", *a, "--region", region],
                          capture_output=True, text=True, check=True).stdout


def read(stage):
    try:
        return json.loads(aws("secretsmanager", "get-secret-value", "--secret-id", secret_id,
                              "--version-stage", stage, "--query", "SecretString",
                              "--output", "text"))
    except subprocess.CalledProcessError:
        return {}


cur, prev = read("AWSCURRENT"), read("AWSPREVIOUS")
if not cur:
    sys.exit("ERROR: el secreto está vacío. Para el primer llenado usa "
             "populate_app_secret.sh")

# El ARN del secreto que gestiona RDS se descubre solo. Así el script no
# depende de Terraform, que es donde falló el primer intento (el nombre del
# output no era el que yo creía).
secs = json.loads(aws("secretsmanager", "list-secrets",
                      "--filters", "Key=name,Values=rds!cluster",
                      "--query", "SecretList[].{n:Name,a:ARN,r:RotationEnabled}",
                      "--output", "json"))
cands = [s for s in secs if s["r"]]
if len(cands) != 1:
    # Con varios clústeres se desempata por el host de la URL actual: el
    # secreto de RDS lleva el id del clúster en su nombre.
    host = re.search(r"@([^:/]+)", cur["DATABASE_URL"]).group(1)
    ident = host.split(".")[0]
    arns = json.loads(aws("rds", "describe-db-clusters",
                          "--query", "DBClusters[].{id:DBClusterIdentifier,"
                          "sec:MasterUserSecret.SecretArn}", "--output", "json"))
    match = [c["sec"] for c in arns if c["id"] == ident and c.get("sec")]
    if len(match) != 1:
        sys.exit("ERROR: no puedo decidir qué secreto de RDS corresponde a "
                 f"'{ident}'. Candidatos: {[s['n'] for s in cands]}. Nada escrito.")
    cands = [{"a": match[0], "n": ident}]
pw = json.loads(aws("secretsmanager", "get-secret-value", "--secret-id", cands[0]["a"],
                    "--query", "SecretString", "--output", "text"))["password"]
pw_enc = urllib.parse.quote(pw, safe="")

# 1 · sólo la contraseña cambia; host, puerto y base se conservan tal cual
#     están, que es precisamente lo que los hace correctos.
patron = re.compile(r"^(?P<pre>[a-z+]+://[^:/@]+:)(?P<pw>[^@]*)(?P<post>@.+)$")
cambiadas = []
for k in DB_KEYS:
    if k not in cur:
        sys.exit(f"ERROR: el secreto no tiene {k}. Esto no es un refresco: "
                 "usa populate_app_secret.sh. Nada escrito.")
    m = patron.match(cur[k])
    if not m:
        sys.exit(f"ERROR: no reconozco la forma de {k} — no la toco. Nada escrito.")
    nueva = m.group("pre") + pw_enc + m.group("post")
    if nueva != cur[k]:
        cur[k] = nueva
        cambiadas.append(k)

# 2 · ninguna clave que pidan las tasks puede faltar.
#
# El criterio es la PRESENCIA de la clave, no que tenga valor: ECS falla
# por "did not contain json key", y hay claves que están vacías **a
# propósito** y deben seguir estándolo —
#   NEXUS_MEDIA_S3_ACCESS_KEY_ID / _SECRET_ACCESS_KEY  el acceso a S3 va
#       por el ROL de la task; poner claves de larga duración aquí
#       reintroduce lo que WP-27 quiere quitar.
#   NEXUS_LANGFUSE_PUBLIC_KEY / _SECRET_KEY            WP-30b pospuesto;
#       el cliente tolera vacío.
# Tratarlas como "faltan" fue el primer bug de este script: abortaba
# pidiendo que se rellenaran cuatro claves que no deben rellenarse.
req = [line.strip() for line in open(req_file) if line.strip()]
recuperadas, faltan, vacias = [], [], []
for k in req:
    if k not in cur:
        if k in prev:
            cur[k] = prev[k]
            recuperadas.append(k)
        else:
            faltan.append(k)
    elif cur[k] == "":
        vacias.append(k)
if faltan:
    sys.exit("ERROR: estas claves las piden las tasks y no están ni en AWSCURRENT "
             "ni en AWSPREVIOUS:\n" + "".join(f"  - {k}\n" for k in faltan) +
             "Expórtalas y usa populate_app_secret.sh. NO se ha escrito nada.")

print(f"    URLs de BD con contraseña nueva: {len(cambiadas)}"
      + (f" ({', '.join(cambiadas)})" if cambiadas else " — ya estaban al día"))
if recuperadas:
    print("    claves recuperadas de AWSPREVIOUS: " + ", ".join(recuperadas))
if vacias:
    # Visibles, no silenciosas: si alguna de éstas NO debiera estar vacía,
    # esta línea es donde se ve.
    print("    presentes y vacías (esperado, ver comentario): " + ", ".join(vacias))
print(f"    total de claves a escribir: {len(cur)}")

ver = aws("secretsmanager", "put-secret-value", "--secret-id", secret_id,
          "--secret-string", json.dumps(cur), "--query", "VersionId",
          "--output", "text").strip()
print(f"==> escrito. Versión nueva: {ver}")
print("    Las tasks EN MARCHA siguen con la contraseña vieja: hay que rodarlas")
print("    con `aws ecs update-service --force-new-deployment` para que la tomen.")
PY
