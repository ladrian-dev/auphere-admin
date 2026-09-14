# El canal de versiones de la aplicación de escritorio (spec 008).
#
# **Este fichero es código reconstruido, no código nuevo.** Los recursos que
# describe **ya existen en producción** desde el 2026-09-13: alguien los aplicó
# desde un módulo que nunca se versionó, y de él sólo sobrevivía un `prod.tfplan`
# binario. El estado remoto los tenía; el repositorio, no. Esto lo arregla —y es
# literalmente lo que pide R7.1: que la infraestructura se pueda reconstruir
# desde el repositorio y no desde la memoria de alguien.
#
# Por eso los nombres de recurso son `desktop` y no algo más bonito: **tienen que
# coincidir con los del estado**. Terraform empareja por nombre de recurso, no
# por lo que el recurso es; renombrarlos aquí haría que un `apply` destruyera los
# doce y creara doce nuevos — incluidos el certificado y la distribución, que
# tarda un cuarto de hora en desplegarse y dejaría `updates.auphere.com` fuera
# mientras tanto.
#
# **Lo que este canal es, y por qué se trata así** (spec 008): lo que se publique
# aquí reemplaza el binario que ejecuta comandos en la máquina del partner —
# ejecución remota de código con otro nombre. De ahí las tres propiedades que hay
# que conservar al tocar este fichero:
#
#   1. El bucket es PRIVADO y lo sirve la distribución con Origin Access Control.
#      «Público» es una casilla que alguien afloja sin querer.
#   2. Escribe UNA identidad: el rol de la cadena (iam.tf), que NO es el rol de
#      despliegue. Comprometer el despliegue no puede significar, además, poder
#      meter un binario en la máquina de un cliente.
#   3. Publicar es AÑADIR. El versionado está encendido y el rol no puede borrar:
#      cuando el puente es saliente, la única marcha atrás es que la versión
#      anterior siga ahí.
#
# **La trampa que cuesta un apply fallido:** CloudFront sólo acepta certificados
# de ACM en `us-east-1`, aunque todo lo demás de esta cuenta viva en
# `eu-south-2`. De ahí el segundo `provider` con alias.

terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.70, < 7.0"
    }
  }

  backend "s3" {
    key = "nexus/40-releases.tfstate"
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = "nexus"
      ManagedBy   = "terraform"
      Stack       = "40-releases"
      Environment = terraform.workspace
    }
  }
}

# Sólo para el certificado: CloudFront no mira en ninguna otra región.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = {
      Project     = "nexus"
      ManagedBy   = "terraform"
      Stack       = "40-releases"
      Environment = terraform.workspace
    }
  }
}

check "workspace_is_named" {
  assert {
    condition     = contains(["staging", "prod"], terraform.workspace)
    error_message = "Selecciona un workspace válido: terraform workspace select staging|prod."
  }
}

variable "region" {
  type    = string
  default = "eu-south-2"
}

variable "channel_domain" {
  type        = string
  description = "El nombre por el que la aplicación pide versiones."
  default     = "updates.auphere.com"
}

variable "channel_prefix" {
  type        = string
  description = "Prefijo dentro del bucket. El cliente pide /desktop/… (e100564)."
  default     = "desktop"
}

data "aws_caller_identity" "current" {}

locals {
  bucket_name = "nexus-${terraform.workspace}-desktop-releases-${data.aws_caller_identity.current.account_id}"
  origin_id   = "s3-desktop-releases"
}

# ── el bucket ───────────────────────────────────────────────────────────

resource "aws_s3_bucket" "desktop" {
  bucket = local.bucket_name
}

# Publicar es añadir, no sustituir: si una versión sale mala, la anterior tiene
# que seguir ahí. Con el puente saliente no hay forma de empujar un arreglo.
resource "aws_s3_bucket_versioning" "desktop" {
  bucket = aws_s3_bucket.desktop.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "desktop" {
  bucket                  = aws_s3_bucket.desktop.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "desktop" {
  bucket = aws_s3_bucket.desktop.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Las versiones antiguas no se guardan para siempre, pero 90 días son muchas
# publicaciones: la marcha atrás sigue disponible mucho después de que nadie la
# necesite. Y los multipart a medias se abortan a la semana, que es basura que
# se paga sin que aparezca en ninguna lista.
resource "aws_s3_bucket_lifecycle_configuration" "desktop" {
  bucket = aws_s3_bucket.desktop.id

  rule {
    id     = "expire-noncurrent"
    status = "Enabled"

    filter {
      prefix = ""
    }

    noncurrent_version_expiration {
      noncurrent_days = 90
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# ── la distribución que lo sirve ────────────────────────────────────────

resource "aws_cloudfront_origin_access_control" "desktop" {
  name                              = "nexus-${terraform.workspace}-desktop-releases"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_acm_certificate" "desktop" {
  provider          = aws.us_east_1
  domain_name       = var.channel_domain
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

# La validación se completó a mano en Cloudflare, que es quien lleva el DNS del
# dominio (igual que api.auphere.com). No se automatiza porque la zona no está
# en esta cuenta.
resource "aws_acm_certificate_validation" "desktop" {
  provider        = aws.us_east_1
  certificate_arn = aws_acm_certificate.desktop.arn
}

resource "aws_cloudfront_distribution" "desktop" {
  enabled         = true
  comment         = "Nexus ${terraform.workspace} desktop releases"
  price_class     = "PriceClass_100"
  aliases         = [var.channel_domain]
  http_version    = "http2"
  is_ipv6_enabled = false

  origin {
    origin_id                = local.origin_id
    domain_name              = aws_s3_bucket.desktop.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.desktop.id
  }

  default_cache_behavior {
    target_origin_id       = local.origin_id
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    # Cache-Policy gestionada "CachingOptimized". El índice lo invalida la
    # cadena al publicar; los paquetes son inmutables por versión.
    cache_policy_id = "658327ea-f89d-4fab-a63d-7e88639e58f6"
  }

  # **El índice NO se cachea, y los paquetes sí.** Es la decisión que hace que
  # una publicación se vea al instante sin depender de una invalidación: el
  # `latest-mac.yml` que la aplicación consulta cada cuatro horas tiene que
  # reflejar lo último, mientras que un paquete es inmutable por versión y
  # puede vivir en el borde todo lo que quiera.
  #
  # `4135ea2d-…` es la política gestionada **CachingDisabled**. Estaba ya en la
  # distribución de producción y este bloque existe para no borrarla: sin él,
  # Terraform la quitaría y el canal empezaría a servir índices viejos durante
  # el TTL, que es un fallo lento y desconcertante — la versión se publica, y
  # unas máquinas la ven y otras no.
  ordered_cache_behavior {
    path_pattern           = "${var.channel_prefix}/*.yml"
    target_origin_id       = local.origin_id
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    cache_policy_id        = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate.desktop.arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }
}

# Sólo la distribución puede leer el bucket. Nadie más, ni con una URL directa.
resource "aws_s3_bucket_policy" "desktop" {
  bucket = aws_s3_bucket.desktop.id
  policy = data.aws_iam_policy_document.desktop_cloudfront.json
}

data "aws_iam_policy_document" "desktop_cloudfront" {
  statement {
    sid       = "AllowCloudFrontOAC"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.desktop.arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.desktop.arn]
    }
  }
}

output "bucket_name" {
  value = aws_s3_bucket.desktop.id
}

output "distribution_id" {
  description = "Va a la variable DESKTOP_RELEASES_DISTRIBUTION del repositorio."
  value       = aws_cloudfront_distribution.desktop.id
}

output "distribution_domain" {
  description = "A esto apunta el CNAME de updates.auphere.com en Cloudflare."
  value       = aws_cloudfront_distribution.desktop.domain_name
}

output "channel_url" {
  value = "https://${var.channel_domain}/${var.channel_prefix}"
}
