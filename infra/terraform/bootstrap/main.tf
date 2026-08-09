# Bootstrap — estado remoto de Terraform + ECR compartido.
#
# Estado LOCAL a propósito (huevo y gallina: este stack crea el bucket donde
# vive el estado de todos los demás). Se aplica UNA vez por cuenta. Los
# recursos aquí son de cuenta, no de entorno: no usa workspaces.

terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.70, < 7.0"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "nexus"
      ManagedBy = "terraform"
      Stack     = "bootstrap"
    }
  }
}

variable "region" {
  type    = string
  default = "eu-south-2"
}

data "aws_caller_identity" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
}

# ── Estado remoto ──────────────────────────────────────────────────────

resource "aws_s3_bucket" "tf_state" {
  bucket = "nexus-terraform-state-${local.account_id}"

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "tf_state" {
  bucket                  = aws_s3_bucket.tf_state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_dynamodb_table" "tf_lock" {
  name         = "nexus-terraform-lock"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  lifecycle {
    prevent_destroy = true
  }
}

# ── ECR (compartido staging/prod: promoción por tag, WP-26) ────────────

resource "aws_ecr_repository" "repos" {
  # nexus-pgbouncer es un espejo de edoburu/pgbouncer (WP-15): Fargate no
  # debe depender del rate limit anónimo de Docker Hub. Se actualiza a mano:
  #   docker buildx imagetools create --tag <ecr>/nexus-pgbouncer:<tag> edoburu/pgbouncer:<tag>
  for_each = toset(["nexus-api", "nexus-worker", "nexus-pgbouncer"])

  name = each.key
  # Tags móviles (``staging``) requieren mutabilidad; la trazabilidad la da
  # el tag inmutable de facto ``<git sha>`` que CI empuja junto al móvil.
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

# keep-50, NO keep-10: precedente real de un lifecycle agresivo podando
# imágenes de Lambdas/servicios ociosos y rompiéndolos al siguiente arranque.
resource "aws_ecr_lifecycle_policy" "keep_50" {
  for_each   = aws_ecr_repository.repos
  repository = each.value.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "keep last 50 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 50
        }
        action = { type = "expire" }
      }
    ]
  })
}

# ── Outputs ────────────────────────────────────────────────────────────

output "state_bucket" {
  value = aws_s3_bucket.tf_state.bucket
}

output "lock_table" {
  value = aws_dynamodb_table.tf_lock.name
}

output "ecr_repository_urls" {
  value = { for k, r in aws_ecr_repository.repos : k => r.repository_url }
}
