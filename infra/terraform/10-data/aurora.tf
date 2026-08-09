# Aurora PostgreSQL Serverless v2.
#
# pgvector NO se habilita aquí: en Aurora PG 16 la extensión ``vector`` viene
# disponible y la crea la migración de la app (``CREATE EXTENSION IF NOT
# EXISTS vector``) — igual que en el Postgres de dev. Apache AGE no existe en
# Aurora; el KG es relacional (decisión de Bloque B, sin cambio aquí).

locals {
  aurora_sizing = {
    staging = {
      # WP-25: mínimos. 0.5 ACU idle ≈ 43 USD/mes.
      min_acu        = 0.5
      max_acu        = 2
      instance_count = 1 # sin réplica de lectura en staging
      # max_connections fijo y DOCUMENTADO (WP-23). El default de Aurora
      # deriva del techo de ACU y se mueve con él; fijarlo hace el fallo
      # explícito ("too many connections") en vez de un techo móvil que
      # nadie recuerda. El pooling real llega con PgBouncer/RDS Proxy
      # (WP-15); estos valores son el tope duro, no el pool de trabajo.
      max_connections  = "500"
      backup_days      = 7
      deletion_protect = false
      skip_final_snap  = true
      perf_insights    = false
    }
    prod = {
      min_acu          = 8
      max_acu          = 32
      instance_count   = 2 # writer + 1 réplica de lectura, AZs distintas = Multi-AZ
      max_connections  = "2000"
      backup_days      = 30
      deletion_protect = true
      skip_final_snap  = false
      perf_insights    = true
    }
  }

  aurora = local.aurora_sizing[local.env]
}

resource "aws_db_subnet_group" "aurora" {
  name       = "${local.name}-aurora"
  subnet_ids = local.network.private_subnet_ids
}

resource "aws_rds_cluster_parameter_group" "aurora" {
  name_prefix = "${local.name}-aurora-pg16-"
  family      = "aurora-postgresql16"

  parameter {
    name         = "max_connections"
    value        = local.aurora.max_connections
    apply_method = "pending-reboot"
  }

  # Diagnóstico de queries lentas desde el día uno (el barrido de prod de
  # Astroluv enseñó que sin esto se diagnostica a ciegas).
  parameter {
    name  = "log_min_duration_statement"
    value = "2000"
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_rds_cluster" "main" {
  cluster_identifier = "${local.name}-aurora"

  engine         = "aurora-postgresql"
  engine_mode    = "provisioned" # Serverless v2 usa engine_mode provisioned + instancias db.serverless
  engine_version = var.aurora_engine_version

  database_name               = "nexus"
  master_username             = "nexus"
  manage_master_user_password = true # RDS guarda la password en su propio secreto

  db_subnet_group_name            = aws_db_subnet_group.aurora.name
  vpc_security_group_ids          = [local.network.aurora_security_group_id]
  db_cluster_parameter_group_name = aws_rds_cluster_parameter_group.aurora.name

  serverlessv2_scaling_configuration {
    min_capacity = local.aurora.min_acu
    max_capacity = local.aurora.max_acu
  }

  storage_encrypted               = true
  backup_retention_period         = local.aurora.backup_days
  preferred_backup_window         = "03:00-04:00"
  preferred_maintenance_window    = "sun:04:30-sun:05:30"
  deletion_protection             = local.aurora.deletion_protect
  skip_final_snapshot             = local.aurora.skip_final_snap
  final_snapshot_identifier       = local.aurora.skip_final_snap ? null : "${local.name}-aurora-final"
  enabled_cloudwatch_logs_exports = ["postgresql"]
  apply_immediately               = terraform.workspace == "staging"

  lifecycle {
    precondition {
      condition     = contains(["staging", "prod"], terraform.workspace)
      error_message = "Workspace inválido '${terraform.workspace}': terraform workspace select staging|prod."
    }
  }
}

resource "aws_rds_cluster_instance" "main" {
  count = local.aurora.instance_count

  identifier          = "${local.name}-aurora-${count.index}"
  cluster_identifier  = aws_rds_cluster.main.id
  instance_class      = "db.serverless"
  engine              = aws_rds_cluster.main.engine
  engine_version      = aws_rds_cluster.main.engine_version
  publicly_accessible = false

  # count.index reparte writer/reader entre AZs vía el subnet group; el
  # reader (tier 1) es a la vez réplica de lectura y objetivo de failover.
  promotion_tier               = count.index
  performance_insights_enabled = local.aurora.perf_insights
}

variable "aurora_engine_version" {
  # En eu-south-2 los 16.x serverless disponibles empiezan en 16.8
  # (verificado 2026-08-09 con describe-orderable-db-instance-options).
  type    = string
  default = "16.13"
}
