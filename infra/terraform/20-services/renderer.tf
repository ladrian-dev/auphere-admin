# Navegador de respaldo (spec 047, requisito 59.2, research D50).
#
# Chromium con Playwright detrás de un proxy propio que resuelve cada nombre
# una vez, rechaza toda dirección no pública y solo sale por 80/443
# (docs/renderer.md). Servicio INTERNO: sin ALB ni ruta pública; lo llama el
# runner (que corre ``client_read``) por Cloud Map, con un token.
#
# APAGADO POR DEFECTO. Con ``renderer_enabled = false`` no se crea nada y la
# definición de tarea del runner no cambia. Encenderlo: docs/renderer.md.

variable "renderer_enabled" {
  description = <<-EOT
    Crea el navegador de respaldo (servicio, SG, secreto con su token, Cloud
    Map) y pasa al runner NEXUS_RENDERER_URL y NEXUS_RENDERER_TOKEN. Apagado
    por defecto. Antes de encenderlo, la imagen nexus-renderer tiene que
    estar en ECR (docs/renderer.md).
  EOT
  type        = bool
  default     = false
}

variable "renderer_image" {
  description = "Imagen del renderer. Vacía = <ecr>/nexus-renderer:<image_tag>."
  type        = string
  default     = ""
}

variable "renderer_cpu" {
  description = "CPU de la task (Fargate). Chromium con dos páginas a la vez."
  type        = number
  default     = 512
}

variable "renderer_memory" {
  description = "Memoria de la task en MiB. Chromium no cabe con holgura en 1024."
  type        = number
  default     = 2048
}

variable "renderer_desired_count" {
  description = "Réplicas. Una basta: es un respaldo y el lector sigue sin él."
  type        = number
  default     = 1
}

locals {
  renderer_count = var.renderer_enabled ? 1 : 0
  renderer_port  = 8080
  renderer_image = (
    var.renderer_image != ""
    ? var.renderer_image
    : "${local.ecr_base}/nexus-renderer:${var.image_tag}"
  )
  renderer_dns = "renderer.${aws_service_discovery_private_dns_namespace.internal.name}"

  # Lo que recibe el runner (taskdefs.tf, contenedor ``runner``). Listas vacías
  # con el interruptor apagado: la definición de tarea del runner queda igual.
  renderer_runner_environment = var.renderer_enabled ? [
    { name = "NEXUS_RENDERER_URL", value = "http://${local.renderer_dns}:${local.renderer_port}" },
  ] : []
  # Una entrada por permiso concedido: recorrer la policy (y citar la versión
  # del secreto) hace que la nueva definición del runner espere a que su
  # execution role pueda leer un token que ya tiene valor. Sin ese orden, las
  # tasks nuevas del runner no arrancarían y el despliegue volvería atrás.
  renderer_runner_secrets = [
    for _grant in aws_iam_role_policy.runner_execution_renderer_secret : {
      name      = "NEXUS_RENDERER_TOKEN"
      valueFrom = "${aws_secretsmanager_secret_version.renderer[0].arn}:NEXUS_RENDERER_TOKEN::"
    }
  ]
}

# ── El token: nace con valor ────────────────────────────────────────────────
#
# Al revés que litellm, el secreto NO nace vacío: el runner lo pide en su
# ``valueFrom`` y una task que pide una clave ausente no arranca — un secreto
# vacío tumbaría el runner, no solo el renderer. Se genera una vez con
# GetRandomPassword y Terraform no lo vuelve a tocar (ignore_changes).
# Rotarlo: docs/renderer.md §Rotar el token.

resource "aws_secretsmanager_secret" "renderer" {
  count = local.renderer_count

  name        = "nexus/${terraform.workspace}/renderer"
  description = "NEXUS_RENDERER_TOKEN: bearer que el runner presenta al navegador de respaldo. Solo lo leen las execution roles del renderer y del runner."
}

data "aws_secretsmanager_random_password" "renderer_token" {
  count = local.renderer_count

  password_length     = 48
  exclude_punctuation = true
}

resource "aws_secretsmanager_secret_version" "renderer" {
  count = local.renderer_count

  secret_id = aws_secretsmanager_secret.renderer[0].id
  secret_string = jsonencode({
    NEXUS_RENDERER_TOKEN = data.aws_secretsmanager_random_password.renderer_token[0].random_password
  })

  lifecycle {
    ignore_changes = [secret_string]
  }
}

data "aws_iam_policy_document" "renderer_secret_read" {
  count = local.renderer_count

  statement {
    sid       = "ReadRendererToken"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.renderer[0].arn]
  }
}

# El runner arranca con ``execution_proxy`` en staging y con la compartida en
# prod (taskdefs.tf); la que toque tiene que poder leer el token. Es la role
# del agente de ECS, no la del código: la aplicación no gana ningún permiso.
resource "aws_iam_role_policy" "runner_execution_renderer_secret" {
  count = local.renderer_count

  name = "read-renderer-secret"
  role = (
    terraform.workspace == "staging"
    ? aws_iam_role.execution_proxy[0].id
    : aws_iam_role.execution.id
  )
  policy = data.aws_iam_policy_document.renderer_secret_read[0].json
}

# ── Execution role propia, y ninguna task role ──────────────────────────────

resource "aws_iam_role" "renderer_execution" {
  count = local.renderer_count

  name               = "${local.name}-renderer-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "renderer_execution_managed" {
  count = local.renderer_count

  role       = aws_iam_role.renderer_execution[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "renderer_execution_secret" {
  count = local.renderer_count

  name   = "read-renderer-secret"
  role   = aws_iam_role.renderer_execution[0].id
  policy = data.aws_iam_policy_document.renderer_secret_read[0].json
}

# ── Red: entra solo el runner, sale solo la web ─────────────────────────────
#
# El SG vive aquí y no en 00-network porque solo existe con el interruptor.
# La salida 443 la usan también el arranque de la task (ECR, Secrets Manager,
# CloudWatch Logs). El DNS del VPC no pasa por el SG. Lo que impide llegar a
# direcciones internas por 80/443 es el proxy del servicio, no esta regla.

resource "aws_security_group" "renderer" {
  count = local.renderer_count

  name_prefix = "${local.name}-renderer-"
  description = "Renderer: 8080 only from the runner; egress 80/443 only"
  vpc_id      = local.network.vpc_id

  egress {
    description = "HTTP to public sites (the in-process proxy vets addresses)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "HTTPS to public sites, ECR, Secrets Manager and CloudWatch Logs"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  lifecycle {
    create_before_destroy = true
  }

  tags = { Name = "${local.name}-renderer" }
}

resource "aws_security_group_rule" "renderer_from_runner" {
  count = local.renderer_count

  type                     = "ingress"
  description              = "renderer 8080 from nexus-runner"
  from_port                = local.renderer_port
  to_port                  = local.renderer_port
  protocol                 = "tcp"
  security_group_id        = aws_security_group.renderer[0].id
  source_security_group_id = local.network.service_security_group_ids["runner"]
}

# ── Cloud Map: renderer.nexus-<ws>.internal ─────────────────────────────────

resource "aws_service_discovery_service" "renderer" {
  count = local.renderer_count

  name = "renderer"

  dns_config {
    namespace_id   = aws_service_discovery_private_dns_namespace.internal.id
    routing_policy = "MULTIVALUE"

    dns_records {
      ttl  = 10
      type = "A"
    }
  }

  # Sin failure_threshold: el proveedor lo marca obsoleto (AWS siempre usa 1).
  health_check_custom_config {}
}

resource "aws_cloudwatch_log_group" "renderer" {
  count = local.renderer_count

  name              = "/nexus/${terraform.workspace}/renderer"
  retention_in_days = terraform.workspace == "prod" ? 90 : 30
}

resource "aws_ecs_task_definition" "renderer" {
  count = local.renderer_count

  family                   = "${local.name}-renderer"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.renderer_cpu
  memory                   = var.renderer_memory
  execution_role_arn       = aws_iam_role.renderer_execution[0].arn
  # Sin task_role_arn, a propósito: el contenedor no tiene credenciales de AWS
  # que una página pudiera pedir a 169.254.170.2 (que el proxy ya rechaza).

  container_definitions = jsonencode([
    {
      name         = "renderer"
      image        = local.renderer_image
      essential    = true
      portMappings = [{ containerPort = local.renderer_port, protocol = "tcp" }]

      environment = [
        { name = "NEXUS_RENDERER_PORT", value = tostring(local.renderer_port) },
        { name = "NEXUS_RENDERER_MAX_CONCURRENCY", value = "2" },
      ]

      secrets = [
        {
          name      = "NEXUS_RENDERER_TOKEN"
          valueFrom = "${aws_secretsmanager_secret_version.renderer[0].arn}:NEXUS_RENDERER_TOKEN::"
        },
      ]

      linuxParameters = {
        # Recoge los procesos hijos de Chromium que mueren huérfanos.
        initProcessEnabled = true
        capabilities = {
          drop = ["ALL"]
        }
      }

      healthCheck = {
        command     = ["CMD-SHELL", "curl --silent --fail http://127.0.0.1:${local.renderer_port}/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 30
      }

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.renderer[0].name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "renderer"
        }
      }
    }
  ])

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }
}

resource "aws_ecs_service" "renderer" {
  count = local.renderer_count

  name            = "${local.name}-renderer"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.renderer[0].arn
  desired_count   = var.renderer_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = local.network.private_subnet_ids
    security_groups  = [aws_security_group.renderer[0].id]
    assign_public_ip = false
  }

  service_registries {
    registry_arn = aws_service_discovery_service.renderer[0].arn
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  deployment_maximum_percent         = 200
  deployment_minimum_healthy_percent = 100

  enable_execute_command = false

  # La primera task tiene que poder leer el token al arrancar.
  depends_on = [
    aws_iam_role_policy.renderer_execution_secret,
    aws_iam_role_policy_attachment.renderer_execution_managed,
  ]
}

output "renderer_url" {
  description = "URL interna (Cloud Map) que recibe el runner. Null con el interruptor apagado."
  value       = var.renderer_enabled ? "http://${local.renderer_dns}:${local.renderer_port}" : null
}

output "renderer_secret_arn" {
  description = "Secreto con NEXUS_RENDERER_TOKEN. Null con el interruptor apagado."
  value       = one(aws_secretsmanager_secret.renderer[*].arn)
}
