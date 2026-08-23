# Task definitions (WP-24). Dos imágenes, cuatro servicios: runner /
# scheduler / egress son ``nexus-worker`` con command distinto — el mismo
# patrón que infra/railway/*.toml. Cada task lleva un sidecar ADOT que
# recibe OTLP de la app y lo exporta a CloudWatch EMF (namespace ``Nexus``),
# que es de donde leen las políticas de autoescalado y las alarmas.

locals {
  sizing = {
    staging = {
      # "Lite" de verdad (2026-08-12), dimensionado con la utilización REAL
      # de 3 días medida en Container Insights, no a ojo:
      #
      #   servicio   CPU máx/asignada   MEM máx/asignada
      #   api            512 / 512         379 / 1024
      #   runner         511 / 512         341 / 1024
      #   scheduler      256 / 256         305 / 512
      #   egress         257 / 256         306 / 512
      #   metering       190 / 256         301 / 512
      #
      # La CPU máxima toca el techo en los picos de arranque, pero la
      # MEDIA va entre el 1% y el 4%. Así que se recorta CPU —que a
      # 0,0466 $/vCPU-h es ~9 veces más cara por unidad que la memoria a
      # 0,0051 $/GB-h— y se CONSERVA la memoria de api y runner: sus picos
      # reales (379 y 341 MiB) dejarían sólo un 30% de holgura sobre 512,
      # y quedarse corto de memoria no degrada, mata el contenedor.
      #
      # Contrapartida asumida: con 0,25 vCPU los arranques y los picos van
      # más lentos, así que staging deja de ser un instrumento válido para
      # medir el p95 del ack. Esa medición se muda a prod (decisión de
      # Luis del 2026-08-12 al mover allí el reloj de la Fase 1).
      cpu    = { api = 256, runner = 256, scheduler = 256, egress = 256, metering = 256 }
      memory = { api = 1024, runner = 1024, scheduler = 512, egress = 512, metering = 512 }
    }
    prod = {
      # Redimensionado el 2026-08-12: prod arranca con el tamaño que pide
      # el volumen de HOY y crece con el autoescalado de WP-24, que ya
      # está puesto. La api conserva 512/1024 porque es la que recibe los
      # webhooks de Meta y su p95 es un SLI; el resto baja al mínimo de
      # staging. Subirlo es cambiar un número aquí.
      cpu    = { api = 512, runner = 512, scheduler = 256, egress = 256, metering = 256 }
      memory = { api = 1024, runner = 1024, scheduler = 512, egress = 512, metering = 512 }
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
    metering  = "${local.ecr_base}/nexus-worker:${var.image_tag}"
  }

  # (los command de runner/scheduler/egress van inline en
  # ``container_definitions`` más abajo — un ternario sobre objetos con
  # atributos distintos no tipa en Terraform)

  common_env_base = [
    { name = "NEXUS_ENVIRONMENT", value = local.nexus_environment },
    # WP-15: NEXUS_DATABASE_URL atraviesa PgBouncer en modo transaction —
    # sin prepared statements compartidos. Inofensivo si la URL fuera
    # directa (solo pierde el cache de statements).
    { name = "NEXUS_DB_TRANSACTION_POOLING", value = "true" },
    { name = "NEXUS_OTEL_ENABLED", value = "true" },
    { name = "OTEL_EXPORTER_OTLP_ENDPOINT", value = "http://127.0.0.1:4318" },
    # Los dos ajustes que hacen MEDIBLES en CloudWatch los SLI del plan.
    # Por defecto el SDK exporta acumulativo y con histogramas de buckets
    # explícitos, y así:
    #   - acumulativo → cada minuto se re-publica el agregado desde el
    #     arranque del proceso, de modo que el Maximum de la métrica no
    #     decae nunca y no dice nada del minuto que se está mirando;
    #   - buckets explícitos → el exportador EMF los manda como
    #     StatisticSet (min/max/sum/count) y CloudWatch NO puede calcular
    #     percentiles sobre eso: p95 sale vacío.
    # Delta + histograma exponencial base-2 hacen que EMF publique
    # Values/Counts por intervalo, que es lo que CloudWatch necesita para
    # p95. Comprobado el 2026-08-09: antes de esto, `webhook_ack_ms` p95
    # devolvía None y el máximo era el mismo valor en todos los periodos.
    { name = "OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE", value = "delta" },
    {
      name  = "OTEL_EXPORTER_OTLP_METRICS_DEFAULT_HISTOGRAM_AGGREGATION"
      value = "base2_exponential_bucket_histogram"
    },
    { name = "NEXUS_LANGFUSE_ENVIRONMENT", value = local.nexus_environment },
    # /health/workers en la API espera exactamente estos servicios (WP-07).
    { name = "NEXUS_EXPECTED_WORKER_SERVICES", value = "nexus-runner,nexus-scheduler,nexus-egress" },
    # En Fargate no hay access keys: las credenciales de S3 vienen del task
    # role y boto3 las resuelve por su cadena por defecto. Sin este flag el
    # gate ``media_s3_enabled`` exigía claves explícitas y la media se
    # guardaba en memoria en vez de en S3, sin un solo error.
    { name = "NEXUS_MEDIA_S3_USE_DEFAULT_CREDENTIALS", value = "true" },
  ]

  # LiteLLM OSS solo en staging. Prod NO lleva esta variable: el Builder
  # falla cerrado si falta. El hostname es el Cloud Map de litellm.tf,
  # no un ALB.
  common_env = concat(
    local.common_env_base,
    terraform.workspace == "staging" ? [
      { name = "LITELLM_PROXY_API_BASE", value = "http://litellm.nexus-staging.internal:4000" },
    ] : [],
  )

  secrets = [
    for key in var.app_secret_keys : {
      name      = key
      valueFrom = "${local.data.app_secret_arn}:${key}::"
    }
  ]

  # Mapping VK: solo api/runner en staging. El JSON entero del secreto
  # (no una clave dentro). Prod y el resto de servicios no lo ven.
  partner_keys_secret = terraform.workspace == "staging" ? [
    {
      name      = "LITELLM_PROXY_VIRTUAL_KEYS"
      valueFrom = aws_secretsmanager_secret.litellm_partner_keys[0].arn
    },
  ] : []

  # OTLP → EMF. dimension_rollup NoDimensionRollup: queremos exactamente
  # las series con dimensión ``stream`` que usan autoescalado y alarmas,
  # no el producto cartesiano de rollups.
  #
  # ``metric_declarations`` NO es opcional aquí, es el contrato: sin ellas
  # el exportador añade por su cuenta una dimensión ``OTelLib`` a TODAS las
  # series. En CloudWatch la identidad de una métrica es su conjunto EXACTO
  # de dimensiones, así que una política que pide ``{stream}`` no encuentra
  # una serie publicada como ``{stream, OTelLib}``: el autoescalado del
  # runner y la alarma de cola llevaban desde el primer despliegue mirando
  # a una métrica sin datos (y la alarma, con ``notBreaching``, sin poder
  # dispararse jamás). Verificado con ``list-metrics`` el 2026-08-09.
  #
  # Cada entrada declara el conjunto de dimensiones EXPORTADO — y solo se
  # exporta lo declarado, lo que además evita pagar por series que nadie
  # consulta. Fuera va deliberadamente ``tenant``: a escala de plataforma
  # es una serie por cliente y por métrica; ese corte es trabajo del WP de
  # Grafana/Langfuse self-hosted (D8), no de CloudWatch.
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

        metric_declarations = [
          # Sin dimensiones: los SLI agregados del plan y el gauge del que
          # autoescala egress (su política declara la métrica sin
          # dimensiones — ver autoscaling.tf).
          {
            dimensions = [[]]
            metric_name_selectors = [
              "turn_latency_ms",
              "turn_errors_total",
              "llm_call_ms",
              "outbound_pending_messages",
              "outbound_oldest_pending_seconds",
            ]
          },
          # Cola de entrada por tier (WP-10): autoescalado del runner y
          # alarma de cola envejecida.
          {
            dimensions            = [["stream"]]
            metric_name_selectors = ["queue_lag_entries", "queue_oldest_pending_seconds"]
          },
          {
            dimensions            = [["provider"]]
            metric_name_selectors = ["webhook_ack_ms", "outbound_delivery_ms"]
          },
          # Dónde falla un turno, y por qué rebota Meta.
          {
            dimensions            = [["stage"]]
            metric_name_selectors = ["turn_errors_total"]
          },
          {
            dimensions            = [["code"]]
            metric_name_selectors = ["meta_send_failures_total"]
          },
          # ``type`` es lo que hace derivable el ratio de cache read.
          {
            dimensions            = [["type"], ["model"]]
            metric_name_selectors = ["llm_tokens_total"]
          },
          {
            dimensions            = [["pool.name", "state"]]
            metric_name_selectors = ["db.client.connections.usage"]
          },
        ]
      }
      awsxray = {
        region = var.region
      }
    }
    service = {
      pipelines = {
        metrics = {
          receivers  = ["otlp"]
          processors = ["batch"]
          exporters  = ["awsemf"]
        }
        # Sin este pipeline los spans OTLP de la app reciben 404 del
        # collector (visto en el primer despliegue). X-Ray es el destino
        # provisional hasta el WP de Grafana self-hosted (D8 enmendada).
        traces = {
          receivers  = ["otlp"]
          processors = ["batch"]
          exporters  = ["awsxray"]
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
      secrets     = concat(local.secrets, contains(["api", "runner"], svc) ? local.partner_keys_secret : [])
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
    # WP-18: ingesta de consumo. Servicio propio y no una tarea del runner
    # porque escribe en una tabla de FACTURACIÓN: no debe competir por los
    # slots del turno ni caerse con él.
    metering = [
      merge(local.app_base["metering"], { command = ["nexus-metering"] }),
      local.adot_sidecar["metering"],
    ]
  }
}

resource "aws_cloudwatch_log_group" "service" {
  for_each = toset(local.services)

  name              = "/nexus/${terraform.workspace}/${each.key}"
  retention_in_days = terraform.workspace == "prod" ? 90 : 30
}

# El collector escribe aquí el EMF del que CloudWatch extrae las métricas.
# Lo creaba el propio collector, y por tanto SIN retención: a volumen de
# producción (un evento EMF por exportación y por serie) es el log group
# más caro de todos, y lo que se guarda ahí ya está en las métricas.
# Una semana basta para depurar una serie rara.
resource "aws_cloudwatch_log_group" "emf" {
  name              = "/nexus/${terraform.workspace}/emf"
  retention_in_days = 7
}

resource "aws_ecs_task_definition" "service" {
  for_each = toset(local.services)

  family                   = "${local.name}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = local.cfg.cpu[each.key]
  memory                   = local.cfg.memory[each.key]
  execution_role_arn = (
    terraform.workspace == "staging" && contains(["api", "runner"], each.key)
    ? aws_iam_role.execution_proxy[0].arn
    : aws_iam_role.execution.arn
  )
  task_role_arn = aws_iam_role.task[each.key].arn

  container_definitions = jsonencode(local.container_definitions[each.key])

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }
}
