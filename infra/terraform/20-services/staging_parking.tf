# Apagado nocturno de staging (Fase 5 del plan de costes, 2026-09-08).
#
# Ventana elegida por Luis: 03:00–09:00 Europe/Madrid, todos los días.
# Apaga 42 h de 168 (25%) y vale ~39 USD/mes entre Fargate y Aurora.
#
# ── POR QUÉ ACCIONES PROGRAMADAS Y NO `desired_count` ──────────────────
#
# Application Auto Scaling es dueño de `desired_count` en cuanto registra el
# target (ya está avisado en autoscaling.tf). Poner el servicio a 0 con
# `update-service` no serviría de nada: el target con `min_capacity = 1` lo
# volvería a levantar en segundos. Lo que hay que mover son los LÍMITES del
# target, y para eso existen las acciones programadas.
#
# ── POR QUÉ LOS SIETE, SIN EXCEPCIÓN ───────────────────────────────────
#
# El ahorro de Aurora (min_acu = 0 en 10-data) NO EXISTE si queda una sola
# conexión viva: la documentación de AWS es explícita en que cualquier
# conexión de usuario impide la pausa. `pgbouncer` mantiene el pool abierto
# y el `scheduler` sondea sin parar — por eso staging nunca baja de 16
# conexiones y consume más ACU que producción. Si se deja fuera cualquiera
# de los dos, se pierde la mitad del ahorro sin que nada lo delate.
#
# `grafana` vive en 30-observability y queda fuera por ahora: no toca
# Aurora, así que no bloquea la pausa. Entra cuando ese stack tenga su
# `staging.tfvars` (hoy un apply allí destruiría Grafana entera).
#
# ── EFECTO EN CI ───────────────────────────────────────────────────────
#
# `deploy-staging.yml` rueda con `--force-new-deployment`, no con
# `--desired-count`. Un push a develop dentro de la ventana da un run VERDE
# que no despliega nada: `wait services-stable` considera estable un
# servicio con desired=0. La imagen entra sola a las 09:00, porque los
# taskdefs apuntan al tag móvil `staging`. Es benigno y se auto-corrige,
# pero que nadie persiga el fantasma de "el deploy no tuvo efecto".

locals {
  parking_enabled = terraform.workspace == "staging"

  # Servicios sin autoescalado propio. El target es inerte (min = max = 1):
  # existe solo para que las acciones programadas puedan bajarlo a 0.
  parking_extra_targets = local.parking_enabled ? {
    scheduler = aws_ecs_service.service["scheduler"].name
    metering  = aws_ecs_service.service["metering"].name
    pgbouncer = aws_ecs_service.pgbouncer.name
    litellm   = aws_ecs_service.litellm[0].name
  } : {}

  # Límites a restaurar a las 09:00, por servicio.
  parking_wake = local.parking_enabled ? merge(
    { for k, v in local.scale_cfg : k => { min = v.min, max = v.max } },
    { for k, _ in local.parking_extra_targets : k => { min = 1, max = 1 } },
  ) : {}
}

resource "aws_appautoscaling_target" "parked" {
  for_each = local.parking_extra_targets

  service_namespace  = "ecs"
  resource_id        = "service/${aws_ecs_cluster.main.name}/${each.value}"
  scalable_dimension = "ecs:service:DesiredCount"
  min_capacity       = 1
  max_capacity       = 1
}

# Un solo mapa de resource_id para las acciones: los tres que ya tenían
# target (api/runner/egress) y los cuatro nuevos.
locals {
  parking_resource_ids = local.parking_enabled ? merge(
    { for k, t in aws_appautoscaling_target.service : k => t.resource_id },
    { for k, t in aws_appautoscaling_target.parked : k => t.resource_id },
  ) : {}
}

resource "aws_appautoscaling_scheduled_action" "down" {
  for_each = local.parking_resource_ids

  name               = "nexus-staging-park-${each.key}"
  service_namespace  = "ecs"
  resource_id        = each.value
  scalable_dimension = "ecs:service:DesiredCount"
  schedule           = "cron(0 3 * * ? *)"
  timezone           = "Europe/Madrid"

  scalable_target_action {
    min_capacity = 0
    max_capacity = 0
  }
}

resource "aws_appautoscaling_scheduled_action" "up" {
  for_each = local.parking_resource_ids

  name               = "nexus-staging-wake-${each.key}"
  service_namespace  = "ecs"
  resource_id        = each.value
  scalable_dimension = "ecs:service:DesiredCount"
  schedule           = "cron(0 9 * * ? *)"
  timezone           = "Europe/Madrid"

  scalable_target_action {
    min_capacity = local.parking_wake[each.key].min
    max_capacity = local.parking_wake[each.key].max
  }
}
