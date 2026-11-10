# Fallos de autenticación contra Aurora y scheduler sin liderazgo.
#
# Se crearon por CLI en prod la noche del 27-ago-2026, tras la caída de 42 h por la
# rotación de la contraseña de Aurora: `scheduler`, `egress` y `metering` siguieron
# con la vieja, y ninguna alarma lo vio, porque `/health/ready` lo sirve la API y la
# API sí se había reiniciado. Ver docs/runbooks/aurora-password-rotation.md.
#
# Solo prod, por el workspace y no por una variable: es donde existen y no hay nada
# que se pueda olvidar. Encenderlas en staging es añadirlo a estos dos locals.
#
# Las descripciones y las `ok_actions` están copiadas tal cual de AWS, con su errata
# y su «cada 7 dias», para que el import no mezcle un cambio. A diferencia del resto
# del stack, estas dos sí avisan al volver a OK.

locals {
  # pgbouncer queda fuera a propósito: toma la contraseña cruda del secreto que
  # gestiona RDS con `valueFrom`, no de las URLs de `nexus/<ws>/app`.
  db_auth_services = terraform.workspace == "prod" ? toset(["api", "egress", "metering", "runner", "scheduler"]) : toset([])

  process_alarms_count = terraform.workspace == "prod" ? 1 : 0
}

resource "aws_cloudwatch_log_metric_filter" "db_auth_failed" {
  for_each = local.db_auth_services

  name           = "${local.name}-db-auth-failed-${each.key}"
  log_group_name = "/nexus/${terraform.workspace}/${each.key}"
  pattern        = "\"password authentication failed\""

  metric_transformation {
    name          = "db_auth_failures"
    namespace     = "Nexus"
    value         = "1"
    default_value = "0"
    unit          = "Count"
  }
}

resource "aws_cloudwatch_log_metric_filter" "scheduler_leader_failed" {
  count = local.process_alarms_count

  name           = "${local.name}-scheduler-leader-failed"
  log_group_name = local.scheduler_log_group
  pattern        = "{ $.event = \"leader.term_failed\" }"

  metric_transformation {
    name          = "scheduler_leader_failed"
    namespace     = "Nexus"
    value         = "1"
    default_value = "0"
    unit          = "Count"
  }
}

resource "aws_cloudwatch_metric_alarm" "db_auth_failures" {
  count = local.process_alarms_count

  alarm_name          = "${local.name}-db-auth-failures"
  alarm_description   = "Un servicio no puede autenticarse contra Aurora. Casi siempre es la rotacion de la contrasena maestra (cada 7 dias) contra una tarea viva desde antes del ultimo cambio del secreto. Comparar startedAt de cada tarea con LastChangedDate de nexus/prod/app; refrescar el secreto y forzar despliegue de TODOS los servicios. Runbook: docs/runbooks/aurora-password-rotation.md"
  namespace           = "Nexus"
  metric_name         = "db_auth_failures"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  actions_enabled = local.alert_actions_enabled
  alarm_actions   = local.alarm_actions
  ok_actions      = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "scheduler_leader_failed" {
  count = local.process_alarms_count

  alarm_name          = "${local.name}-scheduler-leader-failed"
  alarm_description   = "El scheduler no consigue renovar el lock de liderazgo. Con el sin liderazgo NO corre ninguno de los 21 crons (recordatorios de cobranza incluidos) y nada se pone rojo: no hay ALB delante. Calibrado con el incidente del 26-ago: 59 fallos por cada 5 min estando roto, 0 estando sano. Causa mas probable: la contrasena de Aurora roto y esta tarea lleva viva desde antes del ultimo cambio de nexus/prod/app. Runbook: docs/runbooks/aurora-password-rotation.md"
  namespace           = "Nexus"
  metric_name         = "scheduler_leader_failed"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 5
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  actions_enabled = local.alert_actions_enabled
  alarm_actions   = local.alarm_actions
  ok_actions      = local.alarm_actions
}
