# Proxy LiteLLM OSS (staging). Techo USD al vendor; no sustituye C3.
#
# Partner no ve LiteLLM: sin ALB, sin host público. La UI admin (si se
# abre) solo es alcanzable dentro del VPC (Cloud Map / SSM).
# Apagado por defecto; aunque se pase el flag en prod, count = 0.

variable "litellm_enabled" {
  description = <<-EOT
    Crea el proxy LiteLLM OSS. Apagado por defecto. Solo tiene efecto en
    el workspace staging: un apply de prod con el flag no crea nada.
  EOT
  type    = bool
  default = false
}

variable "litellm_image" {
  description = "Imagen oficial pinneada. No usar :latest."
  type        = string
  default     = "ghcr.io/berriai/litellm:v1.74.15-stable"
}

locals {
  litellm_count  = var.litellm_enabled && terraform.workspace == "staging" ? 1 : 0
  litellm_cpu    = 256
  litellm_memory = 512
  litellm_dns    = "litellm.${aws_service_discovery_private_dns_namespace.internal.name}"
}

# Secreto VACÍO. Rellenar a mano ANTES del servicio (ECS aborta si
# valueFrom no resuelve). No meter estas claves en nexus/<ws>/app:
# ese JSON llega a api/runner/scheduler/egress/metering.
resource "aws_secretsmanager_secret" "litellm" {
  count = local.litellm_count

  name        = "nexus/${terraform.workspace}/litellm"
  description = "LITELLM_MASTER_KEY (sk-), LITELLM_SALT_KEY, DATABASE_URL (db litellm, directa), ANTHROPIC_API_KEY, OPENAI_API_KEY. VIRTUAL_KEYS (partner_id->sk) es mapping de producto, no de proxy_admin, y no se inyecta al contenedor."
}

data "aws_iam_policy_document" "litellm_ecs_assume" {
  count = local.litellm_count

  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "litellm_execution" {
  count = local.litellm_count

  name               = "${local.name}-litellm-execution"
  assume_role_policy = data.aws_iam_policy_document.litellm_ecs_assume[0].json
}

resource "aws_iam_role_policy_attachment" "litellm_execution_managed" {
  count = local.litellm_count

  role       = aws_iam_role.litellm_execution[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "litellm_execution_secrets" {
  count = local.litellm_count

  name = "read-litellm-secret"
  role = aws_iam_role.litellm_execution[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["secretsmanager:GetSecretValue"]
      Resource = [
        aws_secretsmanager_secret.litellm[0].arn,
      ]
    }]
  })
}

resource "aws_iam_role" "litellm_task" {
  count = local.litellm_count

  name               = "${local.name}-litellm-task"
  assume_role_policy = data.aws_iam_policy_document.litellm_ecs_assume[0].json
}

resource "aws_service_discovery_service" "litellm" {
  count = local.litellm_count

  name = "litellm"

  dns_config {
    namespace_id   = aws_service_discovery_private_dns_namespace.internal.id
    routing_policy = "MULTIVALUE"

    dns_records {
      ttl  = 10
      type = "A"
    }
  }

  health_check_custom_config {
    failure_threshold = 1
  }
}

resource "aws_cloudwatch_log_group" "litellm" {
  count = local.litellm_count

  name              = "/nexus/${terraform.workspace}/litellm"
  retention_in_days = 30
}

resource "aws_ecs_task_definition" "litellm" {
  count = local.litellm_count

  family                   = "${local.name}-litellm"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = local.litellm_cpu
  memory                   = local.litellm_memory
  execution_role_arn       = aws_iam_role.litellm_execution[0].arn
  task_role_arn            = aws_iam_role.litellm_task[0].arn

  container_definitions = jsonencode([
    {
      name         = "litellm"
      image        = var.litellm_image
      essential    = true
      portMappings = [{ containerPort = 4000, protocol = "tcp" }]

      environment = [
        { name = "PORT", value = "4000" },
        { name = "STORE_MODEL_IN_DB", value = "True" },
      ]

      secrets = [
        {
          name      = "LITELLM_MASTER_KEY"
          valueFrom = "${aws_secretsmanager_secret.litellm[0].arn}:LITELLM_MASTER_KEY::"
        },
        {
          name      = "LITELLM_SALT_KEY"
          valueFrom = "${aws_secretsmanager_secret.litellm[0].arn}:LITELLM_SALT_KEY::"
        },
        {
          name      = "DATABASE_URL"
          valueFrom = "${aws_secretsmanager_secret.litellm[0].arn}:DATABASE_URL::"
        },
        {
          name      = "ANTHROPIC_API_KEY"
          valueFrom = "${aws_secretsmanager_secret.litellm[0].arn}:ANTHROPIC_API_KEY::"
        },
        {
          name      = "OPENAI_API_KEY"
          valueFrom = "${aws_secretsmanager_secret.litellm[0].arn}:OPENAI_API_KEY::"
        },
      ]

      healthCheck = {
        command     = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:4000/health/liveliness')\""]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 120
      }

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.litellm[0].name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "litellm"
        }
      }
    }
  ])

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }
}

resource "aws_ecs_service" "litellm" {
  count = local.litellm_count

  name            = "${local.name}-litellm"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.litellm[0].arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = local.network.private_subnet_ids
    security_groups  = [local.network.litellm_security_group_id]
    assign_public_ip = false
  }

  service_registries {
    registry_arn = aws_service_discovery_service.litellm[0].arn
  }

  health_check_grace_period_seconds = 120

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  deployment_maximum_percent         = 100
  deployment_minimum_healthy_percent = 0
}

output "litellm_dns" {
  description = "Cloud Map interno. Null si el flag esta apagado o el workspace no es staging."
  value       = local.litellm_count == 1 ? "${local.litellm_dns}:4000" : null
}

output "litellm_secret_arn" {
  description = "Rellenar a mano: MASTER, SALT, DATABASE_URL (db litellm), keys de vendor."
  value       = local.litellm_count == 1 ? aws_secretsmanager_secret.litellm[0].arn : null
}
