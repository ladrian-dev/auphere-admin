# Task de migración pre-rollout (WP-24): mismo contrato que el
# ``preDeployCommand`` de Railway — release.sh (Alembic + Drizzle + seed de
# catálogo) corre ANTES de mover tráfico y un exit != 0 aborta el deploy.
# Quién la ejecuta: .github/workflows/deploy-staging.yml (run-task + wait +
# check de exitCode). Terraform solo define la task.

resource "aws_cloudwatch_log_group" "migrate" {
  name              = "/nexus/${terraform.workspace}/migrate"
  retention_in_days = terraform.workspace == "prod" ? 90 : 30
}

resource "aws_ecs_task_definition" "migrate" {
  family                   = "${local.name}-migrate"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.execution.arn
  # Rol de la API: las migraciones no necesitan S3, pero compartir rol
  # evita un quinto rol para una task efímera.
  task_role_arn = aws_iam_role.task["api"].arn

  container_definitions = jsonencode([
    {
      name        = "migrate"
      image       = local.images.api
      essential   = true
      command     = ["/app/apps/api/scripts/release.sh"]
      environment = local.common_env
      secrets     = local.secrets
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.migrate.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "migrate"
        }
      }
    }
  ])

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }
}
