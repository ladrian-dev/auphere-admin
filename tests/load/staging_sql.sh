#!/usr/bin/env bash
# Ejecuta SQL contra la base de un entorno AWS desde una task efímera de
# Fargate — la única forma de llegar a Aurora, que vive en subredes
# privadas sin acceso público.
#
# Reutiliza la task definition de migración (lleva psql y el secreto de la
# app) sobreescribiendo el comando. La salida aparece en el log group
# /nexus/<ws>/migrate y se vuelca aquí al terminar.
#
# Uso:
#   AWS_PROFILE=nexus ./tests/load/staging_sql.sh staging "SELECT count(*) FROM messages;"
#   AWS_PROFILE=nexus ./tests/load/staging_sql.sh staging < consulta.sql
#
# OJO: lo que se imprima acaba en CloudWatch Logs. No seleccionar
# columnas con credenciales (``channels.config_encrypted``, secretos), que
# es exactamente cómo la contraseña de Aurora acabó en un log stream.
set -euo pipefail

WS="${1:-staging}"
SQL="${2:-$(cat)}"
CLUSTER="nexus-${WS}"
export AWS_REGION="${AWS_REGION:-eu-south-2}"

get() { aws ssm get-parameter --name "/nexus/${WS}/deploy/$1" --query Parameter.Value --output text; }
SUBNETS=$(get private_subnet_ids)
SG=$(get migrate_sg_id)

OVERRIDES=$(python3 - "$SQL" <<'PY'
import json, sys

# Colapsado a una línea a propósito: el SQL viaja como argumento de
# ``sh -c`` dentro de JSON, y un \n escapado llega a psql como barra-ene
# literal. Por lo mismo, nada de comentarios ``--`` en el SQL.
sql = " ".join(sys.argv[1].split())
print(json.dumps({"containerOverrides": [{"name": "migrate",
  "command": ["sh", "-c", f'psql "$NEXUS_DATABASE_URL_DIRECT" -v ON_ERROR_STOP=1 -c {json.dumps(sql)}']}]}))
PY
)

START=$(python3 -c 'import time; print(int(time.time()*1000))')
TASK=$(aws ecs run-task --cluster "$CLUSTER" --task-definition "${CLUSTER}-migrate" \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SG],assignPublicIp=DISABLED}" \
  --overrides "$OVERRIDES" --query 'tasks[0].taskArn' --output text)

aws ecs wait tasks-stopped --cluster "$CLUSTER" --tasks "$TASK"
EXIT=$(aws ecs describe-tasks --cluster "$CLUSTER" --tasks "$TASK" \
  --query 'tasks[0].containers[0].exitCode' --output text)

aws logs filter-log-events --log-group-name "/nexus/${WS}/migrate" \
  --start-time "$START" --query 'events[].message' --output text 2>/dev/null || true

exit "${EXIT:-1}"
