locals {
  service_counts = {
    staging = { api = 1, runner = 1, scheduler = 1, egress = 1, metering = 1 }
    # El scheduler es SINGLETON (WP-08: advisory locks toleran 2 durante un
    # rollout como transitorio, no como estado estable).
    prod = { api = 2, runner = 2, scheduler = 1, egress = 2, metering = 1 }
  }

  desired = local.service_counts[local.env]
}

resource "aws_ecs_service" "service" {
  for_each = toset(local.services)

  name            = "${local.name}-${each.key}"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.service[each.key].arn
  desired_count   = local.desired[each.key]
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = local.network.private_subnet_ids
    security_groups  = [local.network.service_security_group_ids[each.key]]
    assign_public_ip = false
  }

  dynamic "load_balancer" {
    for_each = each.key == "api" ? [1] : []
    content {
      target_group_arn = aws_lb_target_group.api.arn
      container_name   = "api"
      container_port   = 8000
    }
  }

  health_check_grace_period_seconds = each.key == "api" ? 60 : null

  # Un rollout que no estabiliza vuelve solo a la revisión anterior — el
  # equivalente ECS del restartPolicy de Railway, pero con rollback.
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  # 100/200 también para el scheduler: WP-08 sancionó explícitamente 2
  # réplicas como transitorio de rollout (advisory locks), así que el
  # solape breve es preferible a una ventana sin crons.
  deployment_maximum_percent         = 200
  deployment_minimum_healthy_percent = 100

  # El autoescalado es dueño de desired_count tras el primer apply.
  lifecycle {
    ignore_changes = [desired_count]
  }
}
