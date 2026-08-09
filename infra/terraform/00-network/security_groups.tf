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
