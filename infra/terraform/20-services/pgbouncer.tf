# WP-15 — PgBouncer en modo transaction delante de Aurora.
#
# Por qué PgBouncer y no RDS Proxy: mismo modelo de multiplexado, pero RDS
# Proxy factura por ACU del cluster (mínimo 8 ACU ≈ 88 USD/mes incluso en
# staging) mientras una task Fargate de 256/512 cuesta ~9 USD/mes; y el
# plan (WP-15) ya fijó PgBouncer con el código de la app preparado para
# ello (set_config transaccional + connect_args sin prepared statements).
#
# La app llega por Cloud Map: ``pgbouncer.nexus-<ws>.internal:5432``.
# Alembic y el checkpointer de LangGraph NO pasan por aquí — usan
# NEXUS_DATABASE_URL_DIRECT (conexiones de sesión).
#
# La imagen es el espejo en ECR de edoburu/pgbouncer (ver bootstrap) — la
# config sale de DATABASE_URL (el secreto de app) + envs PGBOUNCER_*.

variable "pgbouncer_image_tag" {
  type    = string
  default = "v1.24.1-p1"
}

locals {
  pgbouncer_sizing = {
    staging = {
      count             = 1
      default_pool_size = 20
      max_client_conn   = 500
    }
    prod = {
      # 2 réplicas tras Cloud Map (round-robin DNS). Pool por réplica:
      # 2 x 50 = 100 conexiones de servidor como techo — muy por debajo
      # del max_connections=2000 fijado en Aurora.
      count             = 2
      default_pool_size = 50
      max_client_conn   = 2000
    }
  }

  pgbouncer = local.pgbouncer_sizing[local.env]
}

# ── Cloud Map (DNS privado del VPC) ────────────────────────────────────

resource "aws_service_discovery_private_dns_namespace" "internal" {
  name        = "nexus-${terraform.workspace}.internal"
  description = "Descubrimiento interno Nexus ${terraform.workspace}"
  vpc         = local.network.vpc_id
}

resource "aws_service_discovery_service" "pgbouncer" {
  name = "pgbouncer"

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

# ── Task definition + servicio ─────────────────────────────────────────

resource "aws_cloudwatch_log_group" "pgbouncer" {
  name              = "/nexus/${terraform.workspace}/pgbouncer"
  retention_in_days = terraform.workspace == "prod" ? 90 : 30
}

resource "aws_ecs_task_definition" "pgbouncer" {
  family                   = "${local.name}-pgbouncer"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.execution.arn

  container_definitions = jsonencode([
    {
      name         = "pgbouncer"
      image        = "${local.ecr_base}/nexus-pgbouncer:${var.pgbouncer_image_tag}"
      essential    = true
      portMappings = [{ containerPort = 5432, protocol = "tcp" }]
      environment = [
        { name = "POOL_MODE", value = "transaction" },
        { name = "MAX_CLIENT_CONN", value = tostring(local.pgbouncer.max_client_conn) },
        { name = "DEFAULT_POOL_SIZE", value = tostring(local.pgbouncer.default_pool_size) },
        # plain A PROPÓSITO (iteración 3 — el historial completo está en el
        # session log del 2026-08-09):
        #   scram-sha-256 → la userlist que genera la imagen es md5 → SASL
        #     failed en el tramo cliente→pooler.
        #   md5 → clientes entran, pero el pooler→Aurora no puede negociar
        #     SCRAM desde un hash md5 ("cannot do SCRAM authentication:
        #     wrong password type").
        #   plain → userlist en claro: clientes autentican y el pooler
        #     negocia SCRAM con Aurora. El tramo va por subred privada con
        #     SG que solo admite a los servicios. Endurecer (auth_query /
        #     verifier SCRAM) queda para WP-27.
        { name = "AUTH_TYPE", value = "plain" },
        # Config por variables sueltas, NO por DATABASE_URL: las URLs del
        # secreto de app llevan la password percent-encodeada y la imagen
        # hashea la string cruda → los clientes (que mandan la password
        # decodificada) fallaban el login md5. La password CRUDA vive en
        # el secreto que gestiona RDS y llega por valueFrom abajo.
        { name = "DB_HOST", value = local.data.aurora_cluster_endpoint },
        { name = "DB_PORT", value = "5432" },
        { name = "DB_USER", value = "nexus" },
        { name = "DB_NAME", value = "nexus" },
        # Los admin listados pueden ejecutar SHOW POOLS etc. vía psql.
        { name = "ADMIN_USERS", value = "nexus" },
      ]
      secrets = [
        { name = "DB_PASSWORD", valueFrom = "${local.data.aurora_master_secret_arn}:password::" }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.pgbouncer.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "pgbouncer"
        }
      }
    }
  ])

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }
}

resource "aws_ecs_service" "pgbouncer" {
  name            = "${local.name}-pgbouncer"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.pgbouncer.arn
  desired_count   = local.pgbouncer.count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = local.network.private_subnet_ids
    security_groups  = [local.network.pgbouncer_security_group_id]
    assign_public_ip = false
  }

  service_registries {
    registry_arn = aws_service_discovery_service.pgbouncer.arn
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  deployment_maximum_percent         = 200
  deployment_minimum_healthy_percent = 100
}

output "pgbouncer_dns" {
  value = "pgbouncer.${aws_service_discovery_private_dns_namespace.internal.name}"
}
