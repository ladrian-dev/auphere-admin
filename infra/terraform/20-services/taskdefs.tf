# Task definitions (WP-24). Dos imágenes, cuatro servicios: runner /
# scheduler / egress son ``nexus-worker`` con command distinto — el mismo
# patrón que infra/railway/*.toml. Cada task lleva un sidecar ADOT que
# recibe OTLP de la app y lo exporta a CloudWatch EMF (namespace ``Nexus``),
# que es de donde leen las políticas de autoescalado y las alarmas.

locals {
  sizing = {
    staging = {
      # WP-25: tamaños mínimos.
      cpu    = { api = 512, runner = 512, scheduler = 256, egress = 256 }
      memory = { api = 1024, runner = 1024, scheduler = 512, egress = 512 }
    }
    prod = {
      cpu    = { api = 1024, runner = 1024, scheduler = 512, egress = 512 }
      memory = { api = 2048, runner = 2048, scheduler = 1024, egress = 1024 }
    }
  }

  cfg = local.sizing[local.env]

  # staging arranca con NEXUS_ENVIRONMENT=staging: el guard de secretos de
  # config.py solo fuerza en "production", y así los logs/Langfuse quedan
  # etiquetados con el entorno real.
  nexus_environment = terraform.workspace == "prod" ? "production" : "staging"

  images = {
    api       = "${local.ecr_base}/nexus-api:${var.image_tag}"
    runner    = "${local.ecr_base}/nexus-worker:${var.image_tag}"
    scheduler = "${local.ecr_base}/nexus-worker:${var.image_tag}"
    egress    = "${local.ecr_base}/nexus-worker:${var.image_tag}"
  }

  # (los command de runner/scheduler/egress van inline en
  # ``container_definitions`` más abajo — un ternario sobre objetos con
  # atributos distintos no tipa en Terraform)

  common_env = [
    { name = "NEXUS_ENVIRONMENT", value = local.nexus_environment },
    { name = "NEXUS_OTEL_ENABLED", value = "true" },
    { name = "OTEL_EXPORTER_OTLP_ENDPOINT", value = "http://127.0.0.1:4318" },
    { name = "NEXUS_LANGFUSE_ENVIRONMENT", value = local.nexus_environment },
    # /health/workers en la API espera exactamente estos servicios (WP-07).
    { name = "NEXUS_EXPECTED_WORKER_SERVICES", value = "nexus-runner,nexus-scheduler,nexus-egress" },
  ]

  secrets = [
    for key in var.app_secret_keys : {
      name      = key
      valueFrom = "${local.data.app_secret_arn}:${key}::"
    }
  ]

  # OTLP → EMF. dimension_rollup NoDimensionRollup: queremos exactamente
  # las series con dimensión ``stream`` que usan autoescalado y alarmas,
  # no el producto cartesiano de rollups.
  adot_config = yamlencode({
    receivers = {
      otlp = {
        protocols = {
          grpc = { endpoint = "127.0.0.1:4317" }
          http = { endpoint = "127.0.0.1:4318" }
        }
      }
    }
    processors = {
      batch = {}
    }
    exporters = {
      awsemf = {
        namespace                        = "Nexus"
        region                           = var.region
        log_group_name                   = "/nexus/${terraform.workspace}/emf"
        dimension_rollup_option          = "NoDimensionRollup"
        resource_to_telemetry_conversion = { enabled = false }
      }
    }
    service = {
      pipelines = {
        metrics = {
          receivers  = ["otlp"]
          processors = ["batch"]
          exporters  = ["awsemf"]
        }
      }
    }
  })

  app_base = {
    for svc in local.services : svc => {
      name        = svc
      image       = local.images[svc]
      essential   = true
      environment = local.common_env
      secrets     = local.secrets
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.service[svc].name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = svc
        }
      }
    }
  }

  adot_sidecar = {
    for svc in local.services : svc => {
      name      = "adot"
      image     = var.adot_image
      essential = false # si el collector cae, el servicio sigue; solo se pierden métricas
      environment = [
        { name = "AOT_CONFIG_CONTENT", value = local.adot_config },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.service[svc].name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "adot"
        }
      }
    }
  }

  # Mapa literal por servicio (no ternarios sobre objetos heterogéneos:
  # Terraform exige tipos consistentes en ambas ramas de un condicional).
  container_definitions = {
    api = [
      merge(local.app_base["api"], {
        portMappings = [{ containerPort = 8000, protocol = "tcp" }]
        healthCheck = {
          command     = ["CMD-SHELL", "curl --silent --fail http://127.0.0.1:8000/health/live || exit 1"]
          interval    = 30
          timeout     = 5
          retries     = 3
          startPeriod = 20
        }
      }),
      local.adot_sidecar["api"],
    ]
    runner = [
      merge(local.app_base["runner"], { command = ["nexus-runner"] }),
      local.adot_sidecar["runner"],
    ]
    scheduler = [
      merge(local.app_base["scheduler"], { command = ["nexus-scheduler"] }),
      local.adot_sidecar["scheduler"],
    ]
    egress = [
      merge(local.app_base["egress"], { command = ["nexus-egress"] }),
      local.adot_sidecar["egress"],
    ]
  }
}

resource "aws_cloudwatch_log_group" "service" {
  for_each = toset(local.services)

  name              = "/nexus/${terraform.workspace}/${each.key}"
  retention_in_days = terraform.workspace == "prod" ? 90 : 30
}

resource "aws_ecs_task_definition" "service" {
  for_each = toset(local.services)

  family                   = "${local.name}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = local.cfg.cpu[each.key]
  memory                   = local.cfg.memory[each.key]
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task[each.key].arn

  container_definitions = jsonencode(local.container_definitions[each.key])

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }
}
