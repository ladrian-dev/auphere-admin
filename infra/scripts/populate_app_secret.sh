#!/usr/bin/env bash
# Rellena el secreto ``nexus/<ws>/app`` que 10-data crea VACÍO.
#
# Divide las claves en dos grupos, y la división es lo importante:
#
#   DERIVADAS  — se calculan solas desde los outputs de Terraform y la
#                password que gestiona RDS. Nadie las teclea, así que
#                nadie las escribe mal.
#
#   HEREDADAS  — tienen que ser BYTE A BYTE las mismas que en Railway o
#                algo se rompe en silencio. No se generan aquí ni se
#                inventan: se copian del entorno que ya está en producción.
#
# La que más duele de las heredadas es NEXUS_FERNET_KEY: cifra las
# credenciales de los conectores en ``tenant_connectors``. Una clave nueva
# no da un error de arranque — da conectores que dejan de descifrar
# después de migrar los datos, uno a uno, sin traza clara. Lo mismo con
# NEXUS_WEBHOOK_HMAC_SECRET: cambiarlo invalida las firmas que los
# partners ya calculan en su lado.
#
# Uso:
#   1. Exporta las heredadas en tu shell (desde Railway/Doppler, NUNCA
#      en un fichero que acabe en git):
#        export NEXUS_FERNET_KEY=...  NEXUS_META_APP_SECRET=...  etc.
#   2. ./populate_app_secret.sh prod
#
# El script NO imprime ningún valor: sólo qué claves quedaron puestas.

set -euo pipefail

WS="${1:-}"
if [[ "$WS" != "staging" && "$WS" != "prod" ]]; then
  echo "uso: $0 staging|prod" >&2
  exit 2
fi

REGION="${AWS_REGION:-eu-south-2}"
TF="$(cd "$(dirname "$0")/../terraform" && pwd)"

tfout() { # stack, output
  terraform -chdir="$TF/$1" output -raw "$2"
}

echo "==> leyendo outputs de Terraform (workspace $WS)"
for stack in 10-data 20-services; do
  current=$(terraform -chdir="$TF/$stack" workspace show)
  if [[ "$current" != "$WS" ]]; then
    echo "ERROR: $stack está en el workspace '$current', no en '$WS'." >&2
    echo "       terraform -chdir=$TF/$stack workspace select $WS" >&2
    exit 1
  fi
done

AURORA_WRITER=$(tfout 10-data aurora_cluster_endpoint)
AURORA_READER=$(tfout 10-data aurora_reader_endpoint)
MASTER_ARN=$(tfout 10-data aurora_master_secret_arn)
MEDIA_BUCKET=$(tfout 10-data media_bucket)
VALKEY=$(terraform -chdir="$TF/10-data" output -raw valkey_primary_endpoint)
PGB=$(tfout 20-services pgbouncer_dns)
APP_SECRET_ARN=$(tfout 10-data app_secret_arn)

# La password maestra la gestiona RDS en su propio secreto. Se
# percent-encodea porque va dentro de una URL: una '/' o un '@' sin
# escapar parten el DSN por la mitad y el error que sale habla de "host
# desconocido", que manda a depurar al sitio equivocado.
echo "==> leyendo la password maestra de Aurora (secreto gestionado por RDS)"
MASTER_PW=$(aws secretsmanager get-secret-value --region "$REGION" \
  --secret-id "$MASTER_ARN" --query SecretString --output text \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["password"])')
MASTER_PW_ENC=$(python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$MASTER_PW")

# Heredadas: si falta alguna se para ANTES de escribir nada. Un secreto a
# medias arranca los servicios y los rompe a la primera petición real.
REQUIRED=(
  NEXUS_FERNET_KEY
  NEXUS_META_APP_SECRET
  NEXUS_META_WEBHOOK_VERIFY_TOKEN
  NEXUS_WEBHOOK_HMAC_SECRET
  NEXUS_ADMIN_TOKEN
  NEXUS_OPERATOR_FALLBACK_PHONE
  ANTHROPIC_API_KEY
)
missing=()
for k in "${REQUIRED[@]}"; do
  [[ -n "${!k:-}" ]] || missing+=("$k")
done
if (( ${#missing[@]} )); then
  cat >&2 <<EOF
ERROR: faltan estas variables en el entorno, y NO se pueden inventar:

$(printf '  - %s\n' "${missing[@]}")

Cópialas del entorno de Railway que está sirviendo hoy. En particular:
  NEXUS_FERNET_KEY          descifra tenant_connectors — una clave nueva
                            deja los conectores migrados ilegibles, sin
                            error de arranque.
  NEXUS_WEBHOOK_HMAC_SECRET los partners ya firman con este valor.
EOF
  exit 1
fi

echo "==> componiendo el JSON"
PAYLOAD=$(python3 - "$AURORA_WRITER" "$AURORA_READER" "$PGB" "$MASTER_PW_ENC" "$VALKEY" "$MEDIA_BUCKET" "$REGION" <<'PY'
import json, os, sys
writer, reader, pgb, pw, valkey, bucket, region = sys.argv[1:8]

secret = {
    # La app pasa por PgBouncer (WP-15, modo transaction).
    "NEXUS_DATABASE_URL": f"postgresql+asyncpg://nexus:{pw}@{pgb}:5432/nexus",
    # Alembic y el checkpointer de LangGraph necesitan conexiones de
    # SESIÓN: por el pooler en modo transaction se romperían.
    "NEXUS_DATABASE_URL_DIRECT": f"postgresql+asyncpg://nexus:{pw}@{writer}:5432/nexus",
    "NEXUS_DATABASE_URL_RO": f"postgresql+asyncpg://nexus:{pw}@{reader}:5432/nexus",
    # release.sh usa psql, que no entiende el dialecto +asyncpg.
    "DATABASE_URL": f"postgresql://nexus:{pw}@{writer}:5432/nexus",
    "NEXUS_REDIS_URL": f"redis://{valkey}:6379/0",
    "NEXUS_MEDIA_S3_BUCKET": bucket,
    "NEXUS_MEDIA_S3_REGION": region,
    # Vacías a propósito: en AWS el acceso a S3 va por el ROL de la task
    # (política s3-media en cluster_iam.tf). Poner claves de larga
    # duración aquí sería reintroducir justo lo que WP-27 quiere quitar.
    "NEXUS_MEDIA_S3_ACCESS_KEY_ID": "",
    "NEXUS_MEDIA_S3_SECRET_ACCESS_KEY": "",
    # Langfuse quedó pospuesto (WP-30b): el cliente tolera claves vacías.
    "NEXUS_LANGFUSE_PUBLIC_KEY": "",
    "NEXUS_LANGFUSE_SECRET_KEY": "",
}
for k in ("NEXUS_FERNET_KEY", "NEXUS_META_APP_SECRET", "NEXUS_META_WEBHOOK_VERIFY_TOKEN",
          "NEXUS_WEBHOOK_HMAC_SECRET", "NEXUS_ADMIN_TOKEN",
          "NEXUS_OPERATOR_FALLBACK_PHONE", "ANTHROPIC_API_KEY"):
    secret[k] = os.environ[k]

print(json.dumps(secret))
PY
)

echo "==> escribiendo en $APP_SECRET_ARN"
aws secretsmanager put-secret-value --region "$REGION" \
  --secret-id "$APP_SECRET_ARN" --secret-string "$PAYLOAD" \
  --query VersionId --output text

echo "==> claves escritas (sin valores):"
python3 -c 'import json,sys; [print("   ", k) for k in sorted(json.loads(sys.argv[1]))]' "$PAYLOAD"

cat <<EOF

Comprobación de que las task definitions no piden nada que falte:
  las claves de arriba tienen que cubrir 'app_secret_keys' de
  20-services/variables.tf. ECS ABORTA el arranque de la task si un
  valueFrom no resuelve, y el síntoma es un servicio reintentando con
  runningCount = 0, no un error legible.
EOF
