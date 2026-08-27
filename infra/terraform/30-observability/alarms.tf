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

output "alerts_topic_arn" {
  value = aws_sns_topic.alerts.arn
}
