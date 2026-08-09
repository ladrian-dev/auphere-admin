# ElastiCache Valkey — streams de entrada, dedupe (TTL 600s), promote
# pub/sub y locks. Multi-AZ con failover en prod; nodo único en staging.
#
# Sin TLS in-transit A PROPÓSITO: la app usa ``redis://`` y el cambio a
# ``rediss://`` toca todos los clientes (API, runner, scheduler, egress).
# El SG solo admite 6379 desde los servicios y las subredes son privadas.
# Se revisita en WP-27 (SOC 2) como cambio coordinado app+infra.

locals {
  valkey_sizing = {
    staging = {
      node_type     = "cache.t4g.micro"
      replicas      = 0
      multi_az      = false
      failover      = false
      snapshot_days = 1
    }
    prod = {
      node_type     = "cache.t4g.medium"
      replicas      = 1 # 2 nodos en total (WP-23)
      multi_az      = true
      failover      = true
      snapshot_days = 7
    }
  }

  valkey = local.valkey_sizing[local.env]
}

resource "aws_elasticache_subnet_group" "valkey" {
  name       = "${local.name}-valkey"
  subnet_ids = local.network.private_subnet_ids
}

resource "aws_elasticache_replication_group" "valkey" {
  replication_group_id = "${local.name}-valkey"
  description          = "Nexus ${terraform.workspace} — streams + dedupe + locks"

  engine         = "valkey"
  engine_version = var.valkey_engine_version
  node_type      = local.valkey.node_type
  port           = 6379

  num_cache_clusters         = 1 + local.valkey.replicas
  multi_az_enabled           = local.valkey.multi_az
  automatic_failover_enabled = local.valkey.failover

  subnet_group_name  = aws_elasticache_subnet_group.valkey.name
  security_group_ids = [local.network.valkey_security_group_id]

  at_rest_encryption_enabled = true
  transit_encryption_enabled = false # ver cabecera

  snapshot_retention_limit = local.valkey.snapshot_days
  maintenance_window       = "sun:05:30-sun:06:30"
  apply_immediately        = terraform.workspace == "staging"

  # Los streams de turnos NO deben ser evictados bajo presión de memoria:
  # perder un XADD es perder un turno de cliente. noeviction hace el fallo
  # explícito (OOM en el write) en vez de silencioso.
  parameter_group_name = aws_elasticache_parameter_group.valkey.name
}

resource "aws_elasticache_parameter_group" "valkey" {
  # Sin name_prefix (el recurso no lo soporta): un cambio de familia exige
  # renombrar a mano (p. ej. sufijo de versión) para evitar el choque de
  # nombre en el replace.
  name   = "${local.name}-valkey8"
  family = "valkey8"

  parameter {
    name  = "maxmemory-policy"
    value = "noeviction"
  }
}

variable "valkey_engine_version" {
  type    = string
  default = "8.0"
}
