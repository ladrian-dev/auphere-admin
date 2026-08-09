# Autoescalado (WP-24, § del plan):
#   api       → CPU 60%                                   min 2 / max 6  (prod)
#   runner    → queue_oldest_pending_seconds, target 15 s  min 2 / max 10 (prod)
#   egress    → outbound_pending_messages                  min 2 / max 4  (prod)
#   scheduler → FIJO en 1 (sin política)
#
# Las métricas custom viven en CloudWatch namespace ``Nexus`` vía el sidecar
# ADOT. ``queue_oldest_pending_seconds`` la publica ya el claimer del runner
# (dimensión ``stream``, una serie por tier WP-10). ``outbound_pending_messages``
# AÚN NO EXISTE en la app — hasta que egress publique ese gauge la política
# no ve datos y el servicio se queda en min capacity, que es el estado
# seguro (min 2 en prod cubre la carga actual con holgura).

locals {
  scaling = {
    staging = {
      api    = { min = 1, max = 2 }
      runner = { min = 1, max = 2 }
      egress = { min = 1, max = 2 }
    }
    prod = {
      api    = { min = 2, max = 6 }
      runner = { min = 2, max = 10 }
      egress = { min = 2, max = 4 }
    }
  }

  scale_cfg = local.scaling[local.env]

  # Streams de entrada por tier (WP-10) — el runner escala por el MÁXIMO de
  # ambas series: da igual qué tier se atasca, se escala.
  inbound_streams = ["nexus:inbound:standard", "nexus:inbound:priority"]
}

resource "aws_appautoscaling_target" "service" {
  for_each = local.scale_cfg

  service_namespace  = "ecs"
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.service[each.key].name}"
  scalable_dimension = "ecs:service:DesiredCount"
  min_capacity       = each.value.min
  max_capacity       = each.value.max
}

# ── api: CPU 60% ───────────────────────────────────────────────────────

resource "aws_appautoscaling_policy" "api_cpu" {
  name               = "${local.name}-api-cpu"
  policy_type        = "TargetTrackingScaling"
  service_namespace  = aws_appautoscaling_target.service["api"].service_namespace
  resource_id        = aws_appautoscaling_target.service["api"].resource_id
  scalable_dimension = aws_appautoscaling_target.service["api"].scalable_dimension

  target_tracking_scaling_policy_configuration {
    target_value = 60

    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }

    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}

# ── runner: edad del pending más viejo, target 15 s ────────────────────

resource "aws_appautoscaling_policy" "runner_queue_age" {
  name               = "${local.name}-runner-queue-age"
  policy_type        = "TargetTrackingScaling"
  service_namespace  = aws_appautoscaling_target.service["runner"].service_namespace
  resource_id        = aws_appautoscaling_target.service["runner"].resource_id
  scalable_dimension = aws_appautoscaling_target.service["runner"].scalable_dimension

  target_tracking_scaling_policy_configuration {
    target_value = 15

    customized_metric_specification {
      dynamic "metrics" {
        for_each = { for i, s in local.inbound_streams : i => s }
        content {
          id          = "m${metrics.key}"
          return_data = false

          metric_stat {
            stat = "Maximum"

            metric {
              namespace   = "Nexus"
              metric_name = "queue_oldest_pending_seconds"

              dimensions {
                name  = "stream"
                value = metrics.value
              }
            }
          }
        }
      }

      metrics {
        id          = "worst"
        expression  = "MAX([m0, m1])"
        label       = "oldest pending across tiers"
        return_data = true
      }
    }

    # Cola envejeciendo = escalar rápido; desescalar con calma para no
    # oscilar con el tráfico a ráfagas de WhatsApp.
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}

# ── egress: profundidad de messages.pending ────────────────────────────

resource "aws_appautoscaling_policy" "egress_pending_depth" {
  name               = "${local.name}-egress-pending"
  policy_type        = "TargetTrackingScaling"
  service_namespace  = aws_appautoscaling_target.service["egress"].service_namespace
  resource_id        = aws_appautoscaling_target.service["egress"].resource_id
  scalable_dimension = aws_appautoscaling_target.service["egress"].scalable_dimension

  target_tracking_scaling_policy_configuration {
    # 50 salientes encolados por réplica es ~25 s de drenaje al ritmo del
    # dispatcher — por encima, réplica nueva.
    target_value = 50

    customized_metric_specification {
      metric_name = "outbound_pending_messages"
      namespace   = "Nexus"
      statistic   = "Maximum"
    }

    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}
