#!/usr/bin/env bash
#
# Migra a AWS las credenciales de aplicación que se quedaron en Doppler.
#
# ── Por qué existe ──────────────────────────────────────────────────────────
#
# El corte del 2026-08-19 movió producción de Railway a AWS. En Railway el
# contenedor recibía las ~42 variables del config ``prd`` de Doppler; en AWS
# sólo llegan las que estén en ``app_secret_keys`` (20-services/variables.tf),
# que eran 21. Las que faltaban no dieron ningún error: ``config.py`` tiene
# defaults para todas, así que la API arrancó tan tranquila y se rompieron
# cosas en silencio —
#
#   NEXUS_COMPOSIO_API_KEY=""            → cliente Composio FALSO: el catálogo
#                                          se queda sin un solo conector OAuth
#   NEXUS_PUBLIC_API_BASE_URL=localhost  → el callback de consentimiento OAuth
#                                          vuelve a localhost: nunca cierra
#   NEXUS_COMPOSIO_WEBHOOK_SECRET=…change-me
#   NEXUS_ADMIN_PANEL_BASE_URL=localhost
#
# Este script lee Doppler, que es donde siguen viviendo los valores buenos, y
# los deja en ``nexus/<ws>/app``. Se corre UNA vez por entorno; después es
# idempotente (segunda pasada = "sin cambios").
#
# ── Lo que NO toca, y por qué ───────────────────────────────────────────────
#
# Doppler es el config de RAILWAY. Sus URLs de base de datos, Redis y S3
# apuntan a la infraestructura vieja: copiarlas encima de las de AWS sería
# devolver producción a una base apagada. La lista de abajo es explícita y
# cerrada precisamente para que nadie tenga que acordarse de eso:
#
#   NEXUS_DATABASE_URL* · DATABASE_URL · NEXUS_REDIS_URL   → los pone Terraform
#   NEXUS_MEDIA_S3_*                                        → bucket de AWS +
#       rol de la task (WP-27); las claves van vacías A PROPÓSITO
#   NEXUS_LANGFUSE_PUBLIC_KEY / _SECRET_KEY                 → vacías A PROPÓSITO
#       mientras WP-30b siga pospuesto
#   NEXUS_CONSOLE_*                                         → los genera la consola
#   NEXUS_YCLOUD_*                                          → proveedor eliminado
#       en junio de 2026; no se migra basura
#   NEXUS_ADMIN_DATABASE_URL · BETTER_AUTH_* · DOPPLER_*    → son del panel en
#       Vercel, no de la API
#
# ── Orden de ejecución (importa) ────────────────────────────────────────────
#
#   1. Este script con --apply, en los DOS entornos.
#   2. Sólo entonces, añadir las claves a ``app_secret_keys`` y aplicar
#      Terraform. Al revés no: una task que pide una clave que el secreto no
#      tiene NO ARRANCA ("did not contain json key").
#
# No imprime ningún valor: sólo nombres de claves.
#
# Uso:
#   AWS_PROFILE=nexus ./infra/scripts/migrate_doppler_secrets.sh prod
#   AWS_PROFILE=nexus ./infra/scripts/migrate_doppler_secrets.sh prod --apply
#   AWS_PROFILE=nexus ./infra/scripts/migrate_doppler_secrets.sh all --apply

set -euo pipefail

WS="${1:-}"
APPLY="${2:-}"
if [[ "$WS" != "staging" && "$WS" != "prod" && "$WS" != "all" ]]; then
  echo "uso: $0 staging|prod|all [--apply]" >&2
  exit 2
fi
if [[ -n "$APPLY" && "$APPLY" != "--apply" ]]; then
  echo "segundo argumento sólo puede ser --apply" >&2
  exit 2
fi

REGION="${AWS_REGION:-eu-south-2}"
DOPPLER_PROJECT="${DOPPLER_PROJECT:-nexus}"
DOPPLER_CONFIG="${DOPPLER_CONFIG:-prd}"

command -v doppler >/dev/null || { echo "falta el CLI de doppler" >&2; exit 1; }
command -v aws >/dev/null || { echo "falta el CLI de aws" >&2; exit 1; }

SRC="$(mktemp)"; trap 'rm -f "$SRC"' EXIT
chmod 600 "$SRC"
doppler secrets download --no-file --format json \
  --project "$DOPPLER_PROJECT" --config "$DOPPLER_CONFIG" > "$SRC"

run_one() {
  local ws="$1"

  echo
  echo "═══ nexus/$ws/app ═══"
  echo "==> claves que exigen las definiciones de tarea de nexus-$ws"
  local req; req="$(mktemp)"
  for td in api runner egress metering scheduler migrate; do
    aws ecs describe-task-definition --task-definition "nexus-$ws-$td" --region "$REGION" \
      --query 'taskDefinition.containerDefinitions[].secrets[].name' --output text 2>/dev/null \
      | tr '\t' '\n' || true
  done | sed '/^$/d' | sort -u > "$req"
  echo "    $(wc -l < "$req" | tr -d ' ') claves requeridas hoy"

  python3 - "$REGION" "nexus/$ws/app" "$SRC" "$req" "$ws" "${APPLY:-}" <<'PY'
import json, subprocess, sys

region, secret_id, src_file, req_file, ws, apply_flag = sys.argv[1:7]
apply = apply_flag == "--apply"

# Lista CERRADA. Añadir aquí es una decisión consciente; heredar "todo lo que
# haya en Doppler" es como volvieron las URLs de Railway a un entorno de AWS
# en el primer intento.
COPY = [
    # Conectores — el agujero que dejó el corte sin un solo conector OAuth.
    "NEXUS_COMPOSIO_API_KEY",
    "NEXUS_COMPOSIO_WEBHOOK_SECRET",
    # WhatsApp / Meta. ``config.py`` ya trae estos ids como default, así que
    # copiarlos no cambia comportamiento: los hace EXPLÍCITOS, que es lo que
    # permite que un cambio de app de Meta no exija un despliegue de código.
    "NEXUS_META_APP_ID",
    "NEXUS_META_BUSINESS_MANAGER_ID",
    "NEXUS_META_CONFIG_ID_WA_CLOUD_API",
    "NEXUS_META_CONFIG_ID_WA_COEXISTENCE",
    "NEXUS_META_WEBHOOK_CALLBACK_URL",
    # Widget embebido (ADR-028).
    "NEXUS_EMBED_JWT_SECRET",
    # URLs públicas — sin ellas el consentimiento OAuth vuelve a localhost.
    "NEXUS_PUBLIC_API_BASE_URL",
    "NEXUS_ADMIN_PANEL_BASE_URL",
    # Observabilidad: el HOST sí, las claves NO (siguen vacías a propósito).
    "NEXUS_LANGFUSE_HOST",
    # Transcripción de notas de voz (whisper vía LiteLLM) y fallback del router.
    "OPENAI_API_KEY",
    # MCP público de AgendaPro (Stagehand/Browserbase).
    "BROWSERBASE_API_KEY",
    "BROWSERBASE_PROJECT_ID",
]

# Lo que NO puede salir de Doppler tal cual, porque Doppler describe Railway.
OVERRIDES = {
    "prod": {
        "NEXUS_PUBLIC_API_BASE_URL": "https://api.auphere.com",
        "NEXUS_META_WEBHOOK_CALLBACK_URL": "https://webhooks.auphere.com/webhook/meta",
        "NEXUS_ADMIN_PANEL_BASE_URL": "https://admin.auphere.com",
    },
    "staging": {
        "NEXUS_PUBLIC_API_BASE_URL": "https://api.staging.auphere.com",
        "NEXUS_META_WEBHOOK_CALLBACK_URL": "https://api.staging.auphere.com/webhook/meta",
        "NEXUS_ADMIN_PANEL_BASE_URL": "https://console.staging.auphere.com",
    },
}


def aws(*a):
    return subprocess.run(["aws", *a, "--region", region],
                          capture_output=True, text=True, check=True).stdout


src = json.loads(open(src_file).read())
try:
    cur = json.loads(aws("secretsmanager", "get-secret-value", "--secret-id", secret_id,
                         "--version-stage", "AWSCURRENT", "--query", "SecretString",
                         "--output", "text"))
except subprocess.CalledProcessError:
    sys.exit(f"ERROR: no puedo leer {secret_id}. Nada escrito.")
if not cur:
    sys.exit("ERROR: el secreto está vacío. Para el primer llenado usa "
             "populate_app_secret.sh. Nada escrito.")

nuevas, actualizadas, iguales, sin_origen = [], [], [], []
for k in COPY:
    valor = OVERRIDES.get(ws, {}).get(k, src.get(k))
    if valor is None or valor == "":
        # Sin valor de origen no se inventa nada — y sobre todo no se escribe
        # una clave vacía que luego Terraform exigiría.
        sin_origen.append(k)
        continue
    if k not in cur:
        cur[k] = valor
        nuevas.append(k)
    elif cur[k] != valor:
        cur[k] = valor
        actualizadas.append(k)
    else:
        iguales.append(k)

def linea(t, ks):
    print(f"    {t}: {len(ks)}" + (f" → {', '.join(sorted(ks))}" if ks else ""))

linea("nuevas", nuevas)
linea("actualizadas", actualizadas)
linea("ya correctas", iguales)
if sin_origen:
    linea("SIN VALOR en Doppler (no se escriben)", sin_origen)

# Red de seguridad: nada de lo que hoy exigen las tasks puede desaparecer.
req = [l.strip() for l in open(req_file) if l.strip()]
perdidas = [k for k in req if k not in cur]
if perdidas:
    sys.exit("ERROR: el resultado deja fuera claves que las tasks exigen: "
             + ", ".join(perdidas) + ". Nada escrito.")

if not (nuevas or actualizadas):
    print("    sin cambios")
    sys.exit(0)

if not apply:
    print("    [dry-run] no se ha escrito nada. Repite con --apply.")
    sys.exit(0)

aws("secretsmanager", "put-secret-value", "--secret-id", secret_id,
    "--secret-string", json.dumps(cur))
print(f"    escrito. {len(cur)} claves en {secret_id}")
PY
  rm -f "$req"
}

# ── Fase 2 · la consola en Vercel ───────────────────────────────────────────
#
# El botón "Conectar WhatsApp" de ``apps/console`` se apaga solo cuando le
# falta la configuración del Embedded Signup:
#
#   const configured = !!meta.appId && !!(meta.configIdCloudApi || meta.configIdCoexistence)
#
# Los proyectos de Vercel de la consola se crearon con cinco variables (BFF y
# claves del JWT) y sin ninguna de Meta, así que el botón nace deshabilitado
# con "no configurado" — en staging y también en producción. Del lado de la
# API no se nota porque ``config.py`` trae los ids como default.
#
# Sólo se AÑADEN las que falten: si alguien ya puso un valor a mano, se
# respeta y se dice.
run_vercel() {
  local proj="$1"; shift
  local envs=("$@")

  command -v vercel >/dev/null || { echo "    (sin CLI de vercel, me salto $proj)"; return 0; }

  echo
  echo "═══ vercel · $proj ═══"
  local dir; dir="$(mktemp -d)"
  if ! (cd "$dir" && vercel link --yes --project "$proj" >/dev/null 2>&1); then
    echo "    no puedo enlazar el proyecto — ¿existe y tengo acceso?"
    rm -rf "$dir"; return 0
  fi

  local existentes; existentes="$(cd "$dir" && vercel env ls 2>/dev/null || true)"

  for k in NEXUS_META_APP_ID NEXUS_META_CONFIG_ID_WA_CLOUD_API NEXUS_META_CONFIG_ID_WA_COEXISTENCE; do
    local v; v="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get(sys.argv[2],""))' "$SRC" "$k")"
    if [[ -z "$v" ]]; then
      echo "    $k — sin valor en Doppler, no se escribe"
      continue
    fi
    for e in "${envs[@]}"; do
      if grep -q "^ *$k .*$e" <<<"$existentes"; then
        echo "    $k / $e — ya existe, no se toca"
        continue
      fi
      if printf '%s' "$v" | (cd "$dir" && vercel env add "$k" "$e" >/dev/null 2>&1); then
        echo "    $k / $e — añadida"
      else
        echo "    $k / $e — ERROR al añadir"
      fi
    done
  done
  rm -rf "$dir"
  echo "    recuerda: Vercel sólo lee env nuevas en el SIGUIENTE despliegue"
  echo "    → vercel redeploy --prod   (o un push)"
}

if [[ "$WS" == "all" ]]; then
  run_one staging
  run_one prod
else
  run_one "$WS"
fi

if [[ "$APPLY" == "--apply" ]]; then
  case "$WS" in
    staging) run_vercel auphere-console-staging production preview ;;
    prod)    run_vercel auphere-console production ;;
    all)     run_vercel auphere-console-staging production preview
             run_vercel auphere-console production ;;
  esac
else
  echo
  echo "(la fase de Vercel sólo corre con --apply)"
fi

echo
if [[ "$APPLY" == "--apply" ]]; then
  cat <<'TXT'
─────────────────────────────────────────────────────────────────────────────
Siguiente paso, y en este orden:

  1. Añadir las claves nuevas a ``app_secret_keys`` en
     infra/terraform/20-services/variables.tf
  2. terraform apply en los dos workspaces → registra task definitions nuevas
  3. aws ecs update-service --force-new-deployment (o el deploy del workflow)

Hasta el paso 2 el contenedor NO ve las claves nuevas: estar en el secreto no
basta, tiene que estar en la lista que las task definitions inyectan.
─────────────────────────────────────────────────────────────────────────────
TXT
else
  echo "Dry-run. Repite con --apply para escribir."
fi
