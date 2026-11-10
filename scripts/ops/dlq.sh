#!/usr/bin/env bash
#
# La salida de nexus:inbound:dlq, desde tu máquina. Manual: docs/dlq.md.
#
#   ./scripts/ops/dlq.sh <staging|prod> list [--older-than 30d] [--id ID]
#   ./scripts/ops/dlq.sh <staging|prod> discard  <selección> [--yes --reason "…"]
#   ./scripts/ops/dlq.sh <staging|prod> reinject <selección> [--allow-stale] [--yes --reason "…"]
#
# Valkey solo se alcanza desde la VPC y el `api` de producción no tiene ECS Exec,
# así que lanza `python -m nexus_worker.ops.dlq …` como una tarea suelta, con la
# definición y la red del `scheduler`: misma imagen, mismas variables, y sus líneas
# caen en /nexus/<entorno>/scheduler. Espera a que acabe, enseña esas líneas y sale
# con el código de la tarea.
#
# Existe porque un motivo con espacios, dentro de un JSON, dentro de una orden
# pegada en zsh, es la forma segura de equivocarse en producción.
#
# AWS_PROFILE elige el perfil (por defecto, nexus).

set -euo pipefail

usage() {
  sed -n '3,7p' "$0" | sed 's/^# \{0,1\}//' >&2
  exit 2
}

[ "$#" -ge 2 ] || usage
env_name="$1"
shift
case "$env_name" in
  staging | prod) ;;
  *) usage ;;
esac

aws_args=(--profile "${AWS_PROFILE:-nexus}" --region eu-south-2 --no-cli-pager)
cluster="nexus-$env_name"
service="nexus-$env_name-scheduler"
log_group="/nexus/$env_name/scheduler"
container="scheduler"

network="$(
  aws ecs describe-services "${aws_args[@]}" \
    --cluster "$cluster" --services "$service" \
    --query 'services[0].networkConfiguration' --output json
)"

overrides="$(
  python3 -c '
import json, sys
container, *command = sys.argv[1:]
print(json.dumps({"containerOverrides": [{"name": container, "command": command}]}))
' "$container" python -m nexus_worker.ops.dlq "$@"
)"

task_arn="$(
  aws ecs run-task "${aws_args[@]}" \
    --cluster "$cluster" \
    --task-definition "$service" \
    --launch-type FARGATE \
    --started-by ops-dlq \
    --network-configuration "$network" \
    --overrides "$overrides" \
    --query 'tasks[0].taskArn' --output text
)"
case "$task_arn" in
  arn:*) ;;
  *)
    echo "La tarea no arrancó (run-task devolvió «${task_arn}»). Míralo sin --query." >&2
    exit 1
    ;;
esac
echo "Tarea $task_arn. Esperando a que acabe…" >&2

aws ecs wait tasks-stopped "${aws_args[@]}" --cluster "$cluster" --tasks "$task_arn"

exit_code="$(
  aws ecs describe-tasks "${aws_args[@]}" --cluster "$cluster" --tasks "$task_arn" \
    --query "tasks[0].containers[?name=='$container'] | [0].exitCode" --output text
)"

# El registro tarda unos segundos en llegar a CloudWatch.
sleep "${DLQ_LOG_DELAY_S:-8}"
aws logs filter-log-events "${aws_args[@]}" \
  --log-group-name "$log_group" \
  --log-stream-names "$container/$container/${task_arn##*/}" \
  --query 'events[].[message]' --output text

case "$exit_code" in
  '' | *[!0-9]*)
    reason="$(
      aws ecs describe-tasks "${aws_args[@]}" --cluster "$cluster" --tasks "$task_arn" \
        --query 'tasks[0].stoppedReason' --output text
    )"
    echo "La tarea paró sin código de salida: $reason" >&2
    exit 1
    ;;
esac
exit "$exit_code"
