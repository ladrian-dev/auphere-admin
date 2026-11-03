locals {
  alarm_actions = [aws_sns_topic.alerts.arn]
}

# ── ALB / API ──────────────────────────────────────────────────────────

resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  alarm_name          = "${local.name}-api-5xx"
  alarm_description   = "Respuestas 5xx de la API por encima de 10/5min. El barrido de Astroluv enseñó que la métrica de errores puede ser ciega a 500 manejados — esta cuenta TODAS las respuestas 5xx del target."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_Target_5XX_Count"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 10
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = local.services.alb_arn_suffix
  }

  alarm_actions = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "api_unhealthy_hosts" {
  alarm_name          = "${local.name}-api-unhealthy-hosts"
  alarm_description   = "Al menos un target de la API lleva 2 periodos sin pasar /health/ready."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "UnHealthyHostCount"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 2
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = local.services.alb_arn_suffix
    TargetGroup  = local.services.api_target_group_arn_suffix
  }

  alarm_actions = local.alarm_actions
}

# ── Runner: cola envejeciendo pese al autoescalado ─────────────────────
# Si esto suena, el autoescalado (target 15 s) ya perdió la batalla: o el
# max de réplicas se quedó corto o los turnos están fallando en bucle.

resource "aws_cloudwatch_metric_alarm" "runner_queue_stalled" {
  alarm_name          = "${local.name}-runner-queue-stalled"
  alarm_description   = "El pending más viejo de cualquier stream de entrada supera 120 s durante 20 min (4×300s). Mail solo ALARM e INSUFFICIENT, no OK."
  threshold           = 120
  evaluation_periods  = 4
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  metric_query {
    id          = "worst"
    expression  = "MAX([m0, m1])"
    label       = "oldest pending across tiers"
    return_data = true
  }

  metric_query {
    id = "m0"

    metric {
      namespace   = "Nexus"
      metric_name = "queue_oldest_pending_seconds"
      stat        = "Maximum"
      period      = 300

      dimensions = {
        stream = "nexus:inbound:standard"
      }
    }
  }

  metric_query {
    id = "m1"

    metric {
      namespace   = "Nexus"
      metric_name = "queue_oldest_pending_seconds"
      stat        = "Maximum"
      period      = 300

      dimensions = {
        stream = "nexus:inbound:priority"
      }
    }
  }

  alarm_actions = local.alarm_actions

  # Verificado el 2026-08-12 contra CloudWatch: `m0` publica un punto cada
  # 300 s incluso con la cola a cero, y `m1` (stream priority) no existe
  # todavía — `MAX` ignora la serie ausente, así que la alarma SÍ evalúa.
  #
  # Pero con `notBreaching`, "nadie publica" y "cola sana" son el mismo
  # OK. Y quien publica esta métrica es justo el servicio cuya caída hay
  # que detectar: un metering muerto apagaría la única alarma que vigila
  # que el agente sigue contestando. INSUFFICIENT_DATA avisa de eso sin
  # convertir cada hueco en una falsa alarma de cola parada.
  insufficient_data_actions = local.alarm_actions
}

# ── Aurora ─────────────────────────────────────────────────────────────

resource "aws_cloudwatch_metric_alarm" "aurora_acu_ceiling" {
  alarm_name          = "${local.name}-aurora-acu-ceiling"
  alarm_description   = "Aurora lleva 15 min pegada a >90% de su techo de ACU — o hay una query rota o toca subir max_capacity."
  namespace           = "AWS/RDS"
  metric_name         = "ACUUtilization"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 3
  threshold           = 90
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    DBClusterIdentifier = "${local.name}-aurora"
  }

  alarm_actions = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "aurora_connections" {
  alarm_name          = "${local.name}-aurora-connections"
  alarm_description   = "Conexiones cerca del max_connections fijado (500 staging / 2000 prod). Antes de subir el parámetro: ¿está PgBouncer/WP-15 hecho?"
  namespace           = "AWS/RDS"
  metric_name         = "DatabaseConnections"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 2
  threshold           = terraform.workspace == "prod" ? 1600 : 400
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    DBClusterIdentifier = "${local.name}-aurora"
  }

  alarm_actions = local.alarm_actions
}

# ── Valkey ─────────────────────────────────────────────────────────────
# maxmemory-policy=noeviction: quedarse sin memoria = XADD fallando = turnos
# perdidos. Avisar MUCHO antes.

resource "aws_cloudwatch_metric_alarm" "valkey_memory" {
  alarm_name          = "${local.name}-valkey-memory"
  alarm_description   = "Valkey por encima del 75% de memoria. Con noeviction, llegar al 100% es dejar de aceptar turnos."
  namespace           = "AWS/ElastiCache"
  metric_name         = "DatabaseMemoryUsagePercentage"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 2
  threshold           = 75
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    ReplicationGroupId = "${local.name}-valkey"
  }

  alarm_actions = local.alarm_actions
}

# ── Alertas de la plataforma (spec 051, R9) ────────────────────────────
# `platform_watcher` y la conciliación con Meta ya no mandan correo: solo
# escriben en el registro del scheduler. Estas alarmas son quienes avisan.
#
# Una por tipo, no una para todos. El vigilante repite cada hora lo que sigue
# roto, así que una alarma compartida se queda en ALARM con la DLQ y un
# `worker_dead` posterior no cambia su estado: no sale ningún aviso. Contra los
# registros de prod (27-ago a 3-nov) se habría comido 17 de 20 avisos.
#
# La ventana es lo que convierte una repetición en un solo aviso, y tiene que
# ser mayor que dos repeticiones para aguantar una hora perdida. Con 1 h, la DLQ
# de prod habría dado hasta 1579 avisos; con 2 h o más, 1. Ver
# specs/051-correos-con-oficio/evidence/alarma-calibracion.md.
#
# Sin `ok_actions`, como las demás: mientras sigue en ALARM no se vuelve a avisar,
# tampoco si la DLQ crece. Si cae el scheduler entero, no se registra nada y
# estas alarmas no suenan; el correo tenía el mismo punto ciego.

locals {
  scheduler_log_group = "/nexus/${terraform.workspace}/scheduler"

  # 36 × 300 s con un solo punto: avisa en minutos y aguanta 3 h en ALARM.
  alert_period_seconds     = 300
  alert_evaluation_periods = 36

  # Staging aparca sus servicios de 03:00 a 09:00 y cada mañana registra un
  # `worker_dead` que no es un fallo. Las alarmas se ven en la consola, sin correo.
  alert_actions_enabled = terraform.workspace == "prod"

  # Un `kind` por cada `Alert(...)` de platform_watcher.py. Lo comprueba
  # apps/worker/tests/unit/test_platform_alarms_contract.py.
  platform_alert_kinds = {
    queue_backlog      = "La entrada más vieja de una cola de entrada lleva más de 5 min sin procesarse: hay clientes esperando respuesta."
    dlq_entries        = "Hay mensajes de cliente en nexus:inbound:dlq: agotaron sus reintentos y nadie les va a contestar hasta que se revisen y reinyecten. Solo avisa al empezar: sigue en ALARM mientras la cola tenga entradas, y no avisa si crece."
    turn_error_burst   = "Un negocio lleva más de 5 turnos fallidos en 10 min. Sus operadores también reciben el WhatsApp."
    worker_dead        = "Un servicio lleva más de 3 min sin latido. El detalle dice cuál."
    cache_ratio_low    = "El prompt cache lee menos del 30 % en la hora: algo invalida el prefijo del prompt y cada turno cuesta más del doble."
    meta_failure_burst = "Más de 20 envíos a Meta fallidos con el mismo código en 10 min. El detalle dice cuál."
  }
}

resource "aws_cloudwatch_log_metric_filter" "platform_alert" {
  name           = "${local.name}-platform-alert"
  log_group_name = local.scheduler_log_group
  pattern        = "{ $.event = \"platform_alert\" }"

  metric_transformation {
    name      = "platform_alerts"
    namespace = "Nexus"
    value     = "1"

    # Solo el tipo: es un conjunto cerrado, y el negocio se queda en el registro.
    dimensions = {
      kind = "$.kind"
    }
  }
}

resource "aws_cloudwatch_log_metric_filter" "meta_reconciliation" {
  name           = "${local.name}-meta-reconciliation"
  log_group_name = local.scheduler_log_group
  pattern        = "{ $.event = \"ops.meta_reconciliation\" }"

  metric_transformation {
    name      = "meta_reconciliation_alerts"
    namespace = "Nexus"
    value     = "1"
  }
}

resource "aws_cloudwatch_metric_alarm" "platform_alert" {
  for_each = local.platform_alert_kinds

  alarm_name          = "${local.name}-platform-alert-${replace(each.key, "_", "-")}"
  alarm_description   = "${each.value} Detalle en Logs Insights, grupo ${local.scheduler_log_group}: filter event = \"platform_alert\" and kind = \"${each.key}\". docs/correos.md"
  namespace           = "Nexus"
  metric_name         = "platform_alerts"
  statistic           = "Sum"
  period              = local.alert_period_seconds
  evaluation_periods  = local.alert_evaluation_periods
  datapoints_to_alarm = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    kind = each.key
  }

  actions_enabled = local.alert_actions_enabled
  alarm_actions   = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "meta_reconciliation" {
  alarm_name          = "${local.name}-meta-reconciliation"
  alarm_description   = "La conciliación diaria con Meta encontró mensajes que Meta entregó y no están guardados. Revisa la DLQ y el consumidor de entrantes. Detalle por canal en el admin, en Estado, y en Logs Insights, grupo ${local.scheduler_log_group}: filter event = \"ops.meta_reconciliation\". docs/correos.md"
  namespace           = "Nexus"
  metric_name         = "meta_reconciliation_alerts"
  statistic           = "Sum"
  period              = local.alert_period_seconds
  evaluation_periods  = local.alert_evaluation_periods
  datapoints_to_alarm = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  actions_enabled = local.alert_actions_enabled
  alarm_actions   = local.alarm_actions
}

output "alerts_topic_arn" {
  value = aws_sns_topic.alerts.arn
}
