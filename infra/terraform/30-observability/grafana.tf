# WP-30b fase 1 — Grafana autohospedado (decisión D8).
#
# Qué añade, y qué NO: los datos ya están en CloudWatch (métricas con
# percentiles), X-Ray (trazas) y Aurora (coste). Grafana no aporta ningún
# dato nuevo. Aporta **el corte que CloudWatch no puede dar barato**: la
# dimensión `tenant` está fuera del EMF a propósito porque se paga por
# serie, y el panel de margen quiere justo ese corte. Pasando de ~9
# clientes, cortar por cliente en CloudWatch cuesta más que esta instancia
# entera.
#
# Sin EFS: el aprovisionamiento va horneado en la imagen (ver
# infra/grafana/Dockerfile) y el estado en Aurora. No hay volumen que
# gestionar ni copia de seguridad que recordar.
#
# ARM: los tres proyectos publican arm64 y Fargate ARM es ~20-25% más
# barato en eu-south-2. Los servicios de la app siguen en x86 porque sus
# imágenes se construyen --platform linux/amd64.

variable "grafana_enabled" {
  description = <<-EOT
    Crea Grafana. Apagado por defecto para que un `apply` de las alarmas
    en un workspace nuevo no levante un servicio de más sin pedirlo.
  EOT
  type        = bool
  default     = false
}

variable "grafana_image_tag" {
  type    = string
  default = "staging"
}

data "terraform_remote_state" "data" {
  count = var.grafana_enabled ? 1 : 0

  backend   = "s3"
  workspace = terraform.workspace

  config = {
    bucket = var.state_bucket
    key    = "nexus/10-data.tfstate"
    region = var.region
  }
}

data "aws_caller_identity" "current" {}

locals {
  grafana_count = var.grafana_enabled ? 1 : 0
  ecr_base      = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.region}.amazonaws.com"
  # OJO en prod: el cert de `20-services/acm.tf` pide SOLO `api.auphere.com`,
  # sin comodín (staging sí lo tiene, y por eso allí esto no cuesta nada).
  # Encender Grafana en prod exige antes añadir `grafana.auphere.com` al
  # cert — y un cert de ACM no se modifica: hay que pedir uno nuevo y
  # validarlo. Sin eso el listener sirve el cert de la api para este host y
  # el navegador da error de nombre, no un 404 que se entienda.
  grafana_host = terraform.workspace == "prod" ? "grafana.auphere.com" : "grafana.staging.auphere.com"

  # 0,5 vCPU / 1 GB (≈16,58 $/mes en ARM). Grafana con paneles
  # aprovisionados y un puñado de operadores no necesita más; si algún día
  # lo necesita, se sube aquí y se ve en la factura.
  grafana_cpu    = 512
  grafana_memory = 1024
}

# ── Guardas: fallar en el plan, no a mitad del apply ───────────────────

check "grafana_needs_https" {
  assert {
    condition     = !var.grafana_enabled || local.services.https_listener_arn != null
    error_message = "grafana_enabled=true exige el listener 443 en 20-services (aplica allí con -var https_enabled=true). Sin él no hay dónde colgar la regla de host."
  }
}

# ── Secreto: contraseña de admin + contraseña del rol de reporting ─────
#
# El secreto se crea VACÍO y se rellena a mano, igual que nexus/<ws>/app.
# La contraseña del rol `nexus_reporting` tiene que coincidir con la que
# se le ponga en Postgres (la 0078 crea el rol sin contraseña a propósito:
# una credencial en una migración es una credencial publicada en el
# historial de git para siempre).

resource "aws_secretsmanager_secret" "grafana" {
  count = local.grafana_count

  name        = "nexus/${terraform.workspace}/grafana"
  description = "GF_SECURITY_ADMIN_PASSWORD y NEXUS_REPORTING_DB_PASSWORD"
}

# ── IAM ────────────────────────────────────────────────────────────────

data "aws_iam_policy_document" "ecs_assume" {
  count = local.grafana_count

  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "grafana_execution" {
  count = local.grafana_count

  name               = "${local.name}-grafana-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume[0].json
}

resource "aws_iam_role_policy_attachment" "grafana_execution_managed" {
  count = local.grafana_count

  role       = aws_iam_role.grafana_execution[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "grafana_execution_secrets" {
  count = local.grafana_count

  name = "read-grafana-secret"
  role = aws_iam_role.grafana_execution[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["secretsmanager:GetSecretValue"]
      Resource = [
        aws_secretsmanager_secret.grafana[0].arn,
        # El secreto que gestiona RDS con la password maestra: Grafana la
        # necesita para crear sus propias tablas en la base `grafana`.
        # Olvidarlo no da un error de permisos legible sino un servicio
        # que reintenta colocar tasks para siempre con `runningCount = 0`.
        local.data.aurora_master_secret_arn,
      ]
    }]
  })
}

resource "aws_iam_role" "grafana_task" {
  count = local.grafana_count

  name               = "${local.name}-grafana-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume[0].json
}

# Sólo LECTURA de observabilidad. Nada de S3, nada de Secrets Manager
# desde la task: el secreto lo resuelve el execution role al arrancar.
resource "aws_iam_role_policy" "grafana_readonly" {
  count = local.grafana_count

  name = "cloudwatch-xray-read"
  role = aws_iam_role.grafana_task[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:DescribeAlarms",
          "cloudwatch:DescribeAlarmsForMetric",
          "cloudwatch:GetMetricData",
          "cloudwatch:GetMetricStatistics",
          "cloudwatch:ListMetrics",
          "logs:DescribeLogGroups",
          "logs:GetLogGroupFields",
          "logs:GetQueryResults",
          "logs:StartQuery",
          "logs:StopQuery",
          "tag:GetResources",
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "xray:BatchGetTraces",
          "xray:GetTimeSeriesServiceStatistics",
          "xray:GetTraceGraph",
          "xray:GetTraceSummaries",
          "xray:GetGroups",
          "xray:GetInsight",
          "xray:GetInsightSummaries",
        ]
        Resource = "*"
      },
    ]
  })
}

# ── Task definition + servicio ─────────────────────────────────────────

resource "aws_cloudwatch_log_group" "grafana" {
  count = local.grafana_count

  name              = "/nexus/${terraform.workspace}/grafana"
  retention_in_days = terraform.workspace == "prod" ? 90 : 30
}

resource "aws_ecs_task_definition" "grafana" {
  count = local.grafana_count

  family                   = "${local.name}-grafana"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = local.grafana_cpu
  memory                   = local.grafana_memory
  execution_role_arn       = aws_iam_role.grafana_execution[0].arn
  task_role_arn            = aws_iam_role.grafana_task[0].arn

  container_definitions = jsonencode([
    {
      name         = "grafana"
      image        = "${local.ecr_base}/nexus-grafana:${var.grafana_image_tag}"
      essential    = true
      portMappings = [{ containerPort = 3000, protocol = "tcp" }]

      environment = [
        { name = "AWS_REGION", value = var.region },
        { name = "GF_SERVER_ROOT_URL", value = "https://${local.grafana_host}" },
        # Estado en Aurora, no en SQLite efímero: sin esto cada rollout
        # reinicia usuarios, anotaciones y preferencias.
        { name = "GF_DATABASE_TYPE", value = "postgres" },
        { name = "GF_DATABASE_HOST", value = "${local.data.aurora_cluster_endpoint}:5432" },
        { name = "GF_DATABASE_NAME", value = "grafana" },
        { name = "GF_DATABASE_USER", value = "nexus" },
        { name = "GF_DATABASE_SSL_MODE", value = "require" },
        # El datasource de sólo lectura va al endpoint de LECTURA: un
        # panel que haga un scan grande no debe competir con el camino de
        # escritura de los turnos.
        { name = "NEXUS_REPORTING_DB_HOST", value = local.data.aurora_reader_endpoint },
      ]

      secrets = [
        {
          name      = "GF_SECURITY_ADMIN_PASSWORD"
          valueFrom = "${aws_secretsmanager_secret.grafana[0].arn}:GF_SECURITY_ADMIN_PASSWORD::"
        },
        {
          name      = "NEXUS_REPORTING_DB_PASSWORD"
          valueFrom = "${aws_secretsmanager_secret.grafana[0].arn}:NEXUS_REPORTING_DB_PASSWORD::"
        },
        # Grafana guarda su estado con el usuario maestro de Aurora: es el
        # único que puede crear sus tablas en la base `grafana`.
        {
          name      = "GF_DATABASE_PASSWORD"
          valueFrom = "${local.data.aurora_master_secret_arn}:password::"
        },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.grafana[0].name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "grafana"
        }
      }
    }
  ])

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "ARM64"
  }
}

resource "aws_lb_target_group" "grafana" {
  count = local.grafana_count

  name        = "${local.name}-grafana"
  port        = 3000
  protocol    = "HTTP"
  vpc_id      = local.network.vpc_id
  target_type = "ip"

  health_check {
    path                = "/api/health"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
    matcher             = "200"
  }

  deregistration_delay = 30
}

# Se cuelga del listener 443 que ya existe. Un segundo ALB para una UI
# interna serían ~18 $/mes por no escribir esta regla.
resource "aws_lb_listener_rule" "grafana" {
  count = local.grafana_count

  listener_arn = local.services.https_listener_arn
  priority     = 100

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.grafana[0].arn
  }

  condition {
    host_header {
      values = [local.grafana_host]
    }
  }
}

resource "aws_ecs_service" "grafana" {
  count = local.grafana_count

  name            = "${local.name}-grafana"
  cluster         = local.services.cluster_name
  task_definition = aws_ecs_task_definition.grafana[0].arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = local.network.private_subnet_ids
    security_groups  = [local.network.grafana_security_group_id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.grafana[0].arn
    container_name   = "grafana"
    container_port   = 3000
  }

  health_check_grace_period_seconds = 90

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  # UNA réplica: Grafana con backend Postgres tolera varias, pero con un
  # solo operador el 200/100 de los servicios de la app sólo serviría para
  # pagar dos tasks durante cada rollout.
  deployment_maximum_percent         = 100
  deployment_minimum_healthy_percent = 0
}

output "grafana_url" {
  value = var.grafana_enabled ? "https://${local.grafana_host}" : null
}

output "grafana_secret_arn" {
  description = "Rellenar a mano: GF_SECURITY_ADMIN_PASSWORD y NEXUS_REPORTING_DB_PASSWORD."
  value       = var.grafana_enabled ? aws_secretsmanager_secret.grafana[0].arn : null
}
