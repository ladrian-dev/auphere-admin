#!/usr/bin/env bash
# Añade claves a ``nexus/<ws>/app`` SIN tocar las que ya están.
#
# Por qué existe, aparte de los otros dos:
#
#   populate_app_secret.sh  compone el JSON **desde cero** con una lista fija.
#                           Es el primer llenado, y en un secreto que ya vive
#                           borra en silencio todo lo que no esté en su lista.
#                           Pasó el 2026-08-19: se llevó las 3 claves de la
#                           consola y las tasks dejaron de arrancar.
#
#   refresh_app_secret.sh   reescribe SOLO la contraseña de las 4 URLs de base
#                           de datos tras una rotación de Aurora. No sabe
#                           añadir una clave nueva.
#
# Faltaba el tercer caso, que es el de una spec que estrena configuración:
# meter dos o tres claves nuevas en un secreto que ya está poblado, sin
# arriesgar las 34 que ya funcionan.
#
# El orden importa y es el motivo de este script. Una definición de tarea que
# pide una clave ausente del secreto **no arranca**:
#
#   ResourceInitializationError: ... did not contain json key NEXUS_BILLING_API_KEY
#
# Así que la clave entra en el secreto AQUÍ primero, y solo después aparece en
# ``app_secret_keys`` de Terraform. Nunca al revés.
#
# Uso:
#   1. Exporta los valores en tu shell (NUNCA en un fichero que acabe en git):
#        export NEXUS_BILLING_API_KEY=sk_test_...
#        export NEXUS_CONSOLE_BASE_URL=https://console.staging.auphere.com
#   2. AWS_PROFILE=nexus ./infra/scripts/add_app_secret_keys.sh staging \
#        NEXUS_BILLING_API_KEY NEXUS_CONSOLE_BASE_URL
#
# No imprime ningún valor: sólo nombres de claves y qué pasó con cada una.
# Una clave que ya existe con otro valor NO se sobreescribe salvo --force,
# porque pisar una clave viva es justo el fallo que este script evita.

set -euo pipefail

FORCE=0
ARGS=()
for a in "$@"; do
  case "$a" in
    --force) FORCE=1 ;;
    *) ARGS+=("$a") ;;
  esac
done

WS="${ARGS[0]:-}"
if [[ "$WS" != "staging" && "$WS" != "prod" ]]; then
  echo "uso: $0 [--force] staging|prod CLAVE [CLAVE...]" >&2
  exit 2
fi
KEYS=("${ARGS[@]:1}")
if [[ ${#KEYS[@]} -eq 0 ]]; then
  echo "ERROR: no has nombrado ninguna clave." >&2
  echo "uso: $0 [--force] staging|prod CLAVE [CLAVE...]" >&2
  exit 2
fi

REGION="${AWS_REGION:-eu-south-2}"
SECRET_ID="nexus/$WS/app"

# Los valores viajan por el entorno, no por argv: argv se ve en ``ps``.
for k in "${KEYS[@]}"; do
  if [[ -z "${!k:-}" ]]; then
    echo "ERROR: \$$k no está exportada en este shell. Nada escrito." >&2
    exit 1
  fi
done

echo "==> secreto $SECRET_ID (región $REGION)"

export NEXUS_ADD_KEYS="${KEYS[*]}"
export NEXUS_ADD_FORCE="$FORCE"

python3 - "$REGION" "$SECRET_ID" <<'PY'
import json
import os
import re
import subprocess
import sys

region, secret_id = sys.argv[1:3]
keys = os.environ["NEXUS_ADD_KEYS"].split()
force = os.environ["NEXUS_ADD_FORCE"] == "1"


def aws(*a: str) -> str:
    return subprocess.run(
        ["aws", *a, "--region", region], capture_output=True, text=True, check=True
    ).stdout


#: La forma de las claves cuyo formato conocemos. Existe por una avería real: el
#: 2026-09-13 un ``whsec_`` entró con un punto pegado del copiar y pegar. Eran 39
#: caracteres en vez de 38, nada se quejó, y Stripe firmaba bien mientras la API
#: devolvía ``SignatureVerificationError`` — que se lee como un ataque, no como
#: un dedo. Trece minutos para encontrarlo; un carácter para causarlo.
SHAPES = {
    "NEXUS_BILLING_WEBHOOK_SECRET": (r"^whsec_[A-Za-z0-9]{32}$", "whsec_ + 32 alfanuméricos"),
    "NEXUS_BILLING_API_KEY": (r"^sk_(test|live)_[A-Za-z0-9]+$", "sk_test_… o sk_live_…"),
    "NEXUS_BILLING_PUBLIC_KEY": (r"^pk_(test|live)_[A-Za-z0-9]+$", "pk_test_… o pk_live_…"),
}

problems: list[str] = []
for k in keys:
    value = os.environ[k]
    # Un espacio o un salto de línea en los extremos nunca es parte del valor, y
    # es lo que más veces sobrevive a un copiar y pegar.
    if value != value.strip():
        problems.append(f"{k}: sobran espacios o saltos de línea en los extremos")
        continue
    if k.endswith("_BASE_URL"):
        if not re.match(r"^https?://[^\s/]+$", value):
            problems.append(f"{k}: se esperaba un origen https sin ruta ni barra final")
        continue
    shape = SHAPES.get(k)
    if shape and not re.match(shape[0], value):
        problems.append(f"{k}: no tiene la forma {shape[1]} ({len(value)} caracteres)")

if problems:
    print("ERROR: hay valores con la forma equivocada. Nada escrito.\n", file=sys.stderr)
    for p in problems:
        print(f"    {p}", file=sys.stderr)
    print(
        "\nCompruébalos en el shell antes de repetir. Un valor con un carácter de\n"
        "más no da un error de configuración: da un fallo que parece otra cosa.",
        file=sys.stderr,
    )
    sys.exit(1)

try:
    current = json.loads(
        aws(
            "secretsmanager",
            "get-secret-value",
            "--secret-id",
            secret_id,
            "--version-stage",
            "AWSCURRENT",
            "--query",
            "SecretString",
            "--output",
            "text",
        )
    )
except subprocess.CalledProcessError as exc:
    sys.exit(f"ERROR: no puedo leer {secret_id}: {exc.stderr.strip()}")

if not current:
    sys.exit(
        "ERROR: el secreto está vacío. Para el primer llenado usa "
        "populate_app_secret.sh, no este script."
    )

print(f"    {len(current)} claves ya presentes")

added, updated, unchanged, blocked = [], [], [], []
for k in keys:
    new = os.environ[k]
    if k not in current:
        current[k] = new
        added.append(k)
    elif current[k] == new:
        unchanged.append(k)
    elif force:
        current[k] = new
        updated.append(k)
    else:
        blocked.append(k)

if blocked:
    # Abortar sin escribir: pisar una clave viva a ciegas es el fallo que este
    # script existe para no repetir.
    print("\nERROR: estas claves ya existen con OTRO valor:", file=sys.stderr)
    for k in blocked:
        print(f"    {k}", file=sys.stderr)
    print(
        "\nNada escrito. Si de verdad quieres reemplazarlas, repite con --force.",
        file=sys.stderr,
    )
    sys.exit(1)

if not added and not updated:
    print("\n    nada que hacer: todas las claves ya tenían ese valor.")
    sys.exit(0)

# Red de seguridad: escribir un JSON con menos claves de las que había sería
# el fallo del 2026-08-19 otra vez.
assert len(current) >= len(keys), "el JSON compuesto perdió claves"

aws(
    "secretsmanager",
    "put-secret-value",
    "--secret-id",
    secret_id,
    "--secret-string",
    json.dumps(current),
)

print(f"\n==> escrito. {len(current)} claves en total")
for label, group in (("añadidas", added), ("reemplazadas", updated), ("sin cambio", unchanged)):
    for k in group:
        print(f"    {label:14} {k}")
print(
    "\nAhora sí: añade estas claves a ``app_secret_keys`` en\n"
    "infra/terraform/20-services/variables.tf y despliega."
)
PY
