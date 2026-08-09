#!/usr/bin/env bash
# WP-15 — chaos: mata una réplica del runner A MITAD de una rampa de carga
# y verifica las dos invariantes del plan:
#   1. cero respuestas duplicadas (el dedupe Redis + provider_message_id
#      aguantan el re-claim del stream tras la muerte del consumer);
#   2. cero mensajes perdidos (XAUTOCLAIM recupera los pending del muerto).
#
# Uso (con webhook_ramp.js corriendo en otra terminal):
#   AWS_PROFILE=nexus ./tests/load/chaos_kill_runner.sh staging
set -euo pipefail

WS="${1:-staging}"
CLUSTER="nexus-${WS}"
export AWS_REGION="${AWS_REGION:-eu-south-2}"

echo "── réplicas del runner en ${CLUSTER}:"
TASKS=$(aws ecs list-tasks --cluster "$CLUSTER" --service-name "${CLUSTER}-runner" \
  --query 'taskArns' --output text)
echo "$TASKS" | tr '\t' '\n'

VICTIM=$(echo "$TASKS" | awk '{print $1}')
[ -n "$VICTIM" ] || { echo "no hay tasks del runner"; exit 1; }

echo "── matando: $VICTIM"
aws ecs stop-task --cluster "$CLUSTER" --task "$VICTIM" \
  --reason "chaos test WP-15: kill runner mid-turn" >/dev/null

echo "── esperando a que ECS reponga la réplica…"
aws ecs wait services-stable --cluster "$CLUSTER" --services "${CLUSTER}-runner"
echo "── runner estable de nuevo."

# Verificación post-mortem vía task efímera con psql (la task de migración
# lleva postgresql-client y el secreto):
#   - duplicados: mismo wamid entrante respondido 2 veces.
#   - perdidos: entrantes de la última hora sin saliente posterior en su
#     conversación (aproximación razonable con el agente respondiendo).
read -r -d '' CHECK_SQL <<'SQL' || true
SELECT 'saliente_duplicado' AS invariante, count(*) AS violaciones FROM (
  SELECT conversation_id, context_message_id
  FROM messages
  WHERE direction = 'outbound' AND context_message_id IS NOT NULL
    AND created_at > now() - interval '1 hour'
  GROUP BY conversation_id, context_message_id
  HAVING count(*) > 1
) d
UNION ALL
SELECT 'entrante_sin_respuesta', count(*) FROM messages m
WHERE m.direction = 'inbound'
  AND m.created_at BETWEEN now() - interval '1 hour' AND now() - interval '5 minutes'
  AND NOT EXISTS (
    SELECT 1 FROM messages o
    WHERE o.conversation_id = m.conversation_id
      AND o.direction = 'outbound'
      AND o.created_at > m.created_at
  );
SQL

get() { aws ssm get-parameter --name "/nexus/${WS}/deploy/$1" --query Parameter.Value --output text; }
SUBNETS=$(get private_subnet_ids); SG=$(get migrate_sg_id)

echo "── lanzando verificación SQL (task efímera)…"
OVERRIDES=$(python3 - "$CHECK_SQL" <<'PY'
import json, sys
sql = sys.argv[1]
print(json.dumps({"containerOverrides": [{"name": "migrate",
  "command": ["sh", "-c", f'psql "$NEXUS_DATABASE_URL_DIRECT" -v ON_ERROR_STOP=1 -c {json.dumps(sql)}']}]}))
PY
)
TASK=$(aws ecs run-task --cluster "$CLUSTER" --task-definition "${CLUSTER}-migrate" \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SG],assignPublicIp=DISABLED}" \
  --overrides "$OVERRIDES" --query 'tasks[0].taskArn' --output text)
aws ecs wait tasks-stopped --cluster "$CLUSTER" --tasks "$TASK"
EXIT=$(aws ecs describe-tasks --cluster "$CLUSTER" --tasks "$TASK" \
  --query 'tasks[0].containers[0].exitCode' --output text)
echo "── resultado en CloudWatch /nexus/${WS}/migrate (exit $EXIT):"
aws logs tail "/nexus/${WS}/migrate" --since 5m | grep -A4 "invariante" || true
[ "$EXIT" = "0" ] || exit 1
