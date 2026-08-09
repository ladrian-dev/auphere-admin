# Alarmas CloudWatch + SNS (WP-23). La lección de Astroluv aplica entera:
# "NO hay alarmas" es un estado, no un default aceptable. Estas son las
# mínimas que convierten un incidente en una notificación en vez de en un
# cliente escribiendo por WhatsApp.

terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.70, < 7.0"
    }
  }

  backend "s3" {
    key = "nexus/30-observability.tfstate"
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = "nexus"
      ManagedBy   = "terraform"
      Stack       = "30-observability"
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
  default = "eu-west-1"
}

variable "state_bucket" {
  type = string
}

variable "alert_email" {
  description = "Email para las alarmas. Vacío = topic sin suscripción (suscribir a mano o vía chat webhook)."
  type        = string
  default     = ""
}

data "terraform_remote_state" "services" {
  backend   = "s3"
  workspace = terraform.workspace

  config = {
    bucket = var.state_bucket
    key    = "nexus/20-services.tfstate"
    region = var.region
  }
}

locals {
  name     = "nexus-${terraform.workspace}"
  services = data.terraform_remote_state.services.outputs
}

resource "aws_sns_topic" "alerts" {
  name = "${local.name}-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  count = var.alert_email == "" ? 0 : 1

  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}
