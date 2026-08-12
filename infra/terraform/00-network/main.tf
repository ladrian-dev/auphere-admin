# VPC privada por entorno. Los servicios ECS viven en subredes privadas y
# salen por NAT (Meta Cloud API, Anthropic, Composio…). Solo el ALB toca
# subredes públicas.

locals {
  name = "nexus-${terraform.workspace}"

  # ``validate`` corre en el workspace ``default`` — el fallback a staging
  # existe solo para que las expresiones evalúen; la precondition del VPC
  # impide de verdad aplicar fuera de staging/prod.
  env = contains(["staging", "prod"], terraform.workspace) ? terraform.workspace : "staging"

  sizing = {
    staging = {
      cidr = "10.41.0.0/16"
      # 1 NAT: perder una AZ en staging es un incidente aceptable; dos NAT
      # son ~90 USD/mes que staging no justifica.
      nat_count = 1
    }
    prod = {
      cidr = "10.40.0.0/16"
      # 1 NAT también en prod, decisión de Luis del 2026-08-12 al crear el
      # entorno: 35 $/mes en vez de 70. Es un punto único de fallo para
      # TODO el tráfico saliente —si cae esa AZ el agente deja de poder
      # enviar por WhatsApp aunque la API siga viva— y se dobla con un
      # apply el día que el volumen lo justifique. Queda escrito para que
      # sea una decisión revisable y no un olvido.
      nat_count = 1
    }
  }

  cfg = local.sizing[local.env]

  # /20 por subred: 4094 IPs — holgado para tasks Fargate + ENIs de datos.
  public_cidrs  = [for i, _ in var.azs : cidrsubnet(local.cfg.cidr, 4, i)]
  private_cidrs = [for i, _ in var.azs : cidrsubnet(local.cfg.cidr, 4, i + 8)]

  services = ["api", "runner", "scheduler", "egress", "metering"]
}

resource "aws_vpc" "main" {
  cidr_block           = local.cfg.cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = local.name }

  lifecycle {
    precondition {
      condition     = contains(["staging", "prod"], terraform.workspace)
      error_message = "Workspace inválido '${terraform.workspace}': terraform workspace select staging|prod."
    }
  }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = local.name }
}

# ── Subredes ───────────────────────────────────────────────────────────

resource "aws_subnet" "public" {
  count = length(var.azs)

  vpc_id                  = aws_vpc.main.id
  cidr_block              = local.public_cidrs[count.index]
  availability_zone       = var.azs[count.index]
  map_public_ip_on_launch = false

  tags = { Name = "${local.name}-public-${var.azs[count.index]}" }
}

resource "aws_subnet" "private" {
  count = length(var.azs)

  vpc_id            = aws_vpc.main.id
  cidr_block        = local.private_cidrs[count.index]
  availability_zone = var.azs[count.index]

  tags = { Name = "${local.name}-private-${var.azs[count.index]}" }
}

# ── NAT ────────────────────────────────────────────────────────────────

resource "aws_eip" "nat" {
  count  = local.cfg.nat_count
  domain = "vpc"
  tags   = { Name = "${local.name}-nat-${count.index}" }
}

resource "aws_nat_gateway" "main" {
  count = local.cfg.nat_count

  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id
  tags          = { Name = "${local.name}-nat-${count.index}" }

  depends_on = [aws_internet_gateway.main]
}

# ── Rutas ──────────────────────────────────────────────────────────────

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "${local.name}-public" }
}

resource "aws_route" "public_internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.main.id
}

resource "aws_route_table_association" "public" {
  count = length(var.azs)

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# Una route table privada por AZ: con 2 NAT cada AZ sale por el suyo; con 1
# NAT (staging) ambas apuntan al mismo.
resource "aws_route_table" "private" {
  count = length(var.azs)

  vpc_id = aws_vpc.main.id
  tags   = { Name = "${local.name}-private-${var.azs[count.index]}" }
}

resource "aws_route" "private_nat" {
  count = length(var.azs)

  route_table_id         = aws_route_table.private[count.index].id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.main[min(count.index, local.cfg.nat_count - 1)].id
}

resource "aws_route_table_association" "private" {
  count = length(var.azs)

  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[count.index].id
}

# S3 por gateway endpoint: el tráfico de media (imágenes/audio de WhatsApp)
# no pasa por NAT — gratis y más rápido.
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = aws_route_table.private[*].id

  tags = { Name = "${local.name}-s3" }
}
