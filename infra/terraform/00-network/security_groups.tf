# Un SG por servicio (WP-23): la separación de red es parte del modelo de
# aislamiento, no cosmética — p. ej. solo el ALB habla con la API, y nada
# entra a runner/scheduler/egress.

resource "aws_security_group" "alb" {
  name_prefix = "${local.name}-alb-"
  description = "ALB publico: 80/443 desde internet"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTP (redirige a HTTPS en el listener)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  lifecycle {
    create_before_destroy = true
  }

  tags = { Name = "${local.name}-alb" }
}

resource "aws_security_group" "service" {
  for_each = toset(local.services)

  name_prefix = "${local.name}-${each.key}-"
  description = "ECS service nexus-${each.key}"
  vpc_id      = aws_vpc.main.id

  # Salida abierta: Meta Cloud API, Anthropic, Composio, Langfuse…
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  lifecycle {
    create_before_destroy = true
  }

  tags = { Name = "${local.name}-${each.key}" }
}

# Solo la API recibe tráfico, y solo desde el ALB.
resource "aws_security_group_rule" "api_from_alb" {
  type                     = "ingress"
  description              = "uvicorn desde el ALB"
  from_port                = 8000
  to_port                  = 8000
  protocol                 = "tcp"
  security_group_id        = aws_security_group.service["api"].id
  source_security_group_id = aws_security_group.alb.id
}

# WP-15: PgBouncer en modo transaction entre los servicios y Aurora.
resource "aws_security_group" "pgbouncer" {
  name_prefix = "${local.name}-pgbouncer-"
  description = "PgBouncer: 5432 desde los servicios; sale solo hacia Aurora"
  vpc_id      = aws_vpc.main.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  lifecycle {
    create_before_destroy = true
  }

  tags = { Name = "${local.name}-pgbouncer" }
}

resource "aws_security_group_rule" "pgbouncer_from_services" {
  for_each = toset(local.services)

  type                     = "ingress"
  description              = "pgbouncer desde nexus-${each.key}"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.pgbouncer.id
  source_security_group_id = aws_security_group.service[each.key].id
}

resource "aws_security_group" "aurora" {
  name_prefix = "${local.name}-aurora-"
  description = "Aurora PostgreSQL: 5432 solo desde los servicios"
  vpc_id      = aws_vpc.main.id

  lifecycle {
    create_before_destroy = true
  }

  tags = { Name = "${local.name}-aurora" }
}

resource "aws_security_group_rule" "aurora_from_services" {
  for_each = toset(local.services)

  type                     = "ingress"
  description              = "postgres desde nexus-${each.key}"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.aurora.id
  source_security_group_id = aws_security_group.service[each.key].id
}

resource "aws_security_group_rule" "aurora_from_pgbouncer" {
  type                     = "ingress"
  description              = "postgres desde pgbouncer"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.aurora.id
  source_security_group_id = aws_security_group.pgbouncer.id
}

# WP-30b — Grafana. Vive aquí y no en 30-observability por la misma razón
# que el resto: la separación de red es parte del modelo de aislamiento y
# se lee entera en un solo fichero. Grafana NO habla con Valkey ni con los
# servicios; solo recibe del ALB y sale hacia Aurora (lectura) y hacia las
# APIs de CloudWatch/X-Ray por el NAT.
resource "aws_security_group" "grafana" {
  name_prefix = "${local.name}-grafana-"
  description = "Grafana: 3000 desde el ALB; sale hacia Aurora y las APIs de AWS"
  vpc_id      = aws_vpc.main.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  lifecycle {
    create_before_destroy = true
  }

  tags = { Name = "${local.name}-grafana" }
}

resource "aws_security_group_rule" "grafana_from_alb" {
  type                     = "ingress"
  description              = "grafana desde el ALB"
  from_port                = 3000
  to_port                  = 3000
  protocol                 = "tcp"
  security_group_id        = aws_security_group.grafana.id
  source_security_group_id = aws_security_group.alb.id
}

# Va al endpoint de LECTURA de Aurora, no al writer: un panel que hace un
# scan grande no debe competir con el camino de escritura de los turnos.
resource "aws_security_group_rule" "aurora_from_grafana" {
  type                     = "ingress"
  description              = "postgres desde grafana (solo lectura, rol nexus_reporting)"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.aurora.id
  source_security_group_id = aws_security_group.grafana.id
}

resource "aws_security_group" "valkey" {
  name_prefix = "${local.name}-valkey-"
  description = "ElastiCache Valkey: 6379 solo desde los servicios"
  vpc_id      = aws_vpc.main.id

  lifecycle {
    create_before_destroy = true
  }

  tags = { Name = "${local.name}-valkey" }
}

resource "aws_security_group_rule" "valkey_from_services" {
  for_each = toset(local.services)

  type                     = "ingress"
  description              = "valkey desde nexus-${each.key}"
  from_port                = 6379
  to_port                  = 6379
  protocol                 = "tcp"
  security_group_id        = aws_security_group.valkey.id
  source_security_group_id = aws_security_group.service[each.key].id
}

# LiteLLM OSS: solo workspace staging. En prod no hay task ni SG.
# :4000 solo desde api y runner (worker). Sin ALB, sin Valkey.
resource "aws_security_group" "litellm" {
  count = terraform.workspace == "staging" ? 1 : 0

  name_prefix = "${local.name}-litellm-"
  description = "LiteLLM: 4000 desde api/runner; sale hacia Aurora y vendors"
  vpc_id      = aws_vpc.main.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  lifecycle {
    create_before_destroy = true
  }

  tags = { Name = "${local.name}-litellm" }
}

resource "aws_security_group_rule" "litellm_from_api_runner" {
  for_each = terraform.workspace == "staging" ? toset(["api", "runner"]) : toset([])

  type                     = "ingress"
  description              = "litellm :4000 desde nexus-${each.key}"
  from_port                = 4000
  to_port                  = 4000
  protocol                 = "tcp"
  security_group_id        = aws_security_group.litellm[0].id
  source_security_group_id = aws_security_group.service[each.key].id
}

resource "aws_security_group_rule" "aurora_from_litellm" {
  count = terraform.workspace == "staging" ? 1 : 0

  type                     = "ingress"
  description              = "postgres desde litellm (writer; DATABASE_URL ya en SM)"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.aurora.id
  source_security_group_id = aws_security_group.litellm[0].id
}
