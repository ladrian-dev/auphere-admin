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
  default = "eu-south-2"
}

variable "state_bucket" {
  type = string
}

variable "alert_email" {
  description = "Destinatario de las alarmas. El default no es cosmético: un topic sin suscripción convierte cada alarma en un mensaje al vacío, y ese es justo el modo de fallo que estas alarmas existen para cazar."
  type        = string
  default     = "contacto@ladrian.dev"
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

data "terraform_remote_state" "network" {
  count = var.grafana_enabled ? 1 : 0

  backend   = "s3"
  workspace = terraform.workspace

  config = {
    bucket = var.state_bucket
    key    = "nexus/00-network.tfstate"
    region = var.region
  }
}

locals {
  name     = "nexus-${terraform.workspace}"
  services = data.terraform_remote_state.services.outputs

  # Sólo se leen cuando Grafana está encendido: las alarmas por sí solas
  # no necesitan ni la red ni la base. ``one()`` y no un ternario con
  # ``{}``: los dos brazos de un condicional tienen que tipar igual, y un
  # objeto de 9 atributos no tipa como un mapa vacío. Con Grafana apagado
  # esto vale null, y nadie lo mira porque todo lo que lo usa va con
  # count = 0.
  network = one(data.terraform_remote_state.network[*].outputs)
  data    = one(data.terraform_remote_state.data[*].outputs)
}

resource "aws_sns_topic" "alerts" {
  name = "${local.name}-alerts"

  # Un topic sin suscriptores no es media alarma: es cero alarma con aspecto
  # de estar montada. Staging vivió así desde WP-23 y nadie lo notó, que es
  # exactamente el síntoma. Se rechaza el apply antes que heredar el hueco en
  # prod, donde detrás hay clientes de Facelad y Amacrux.
  lifecycle {
    precondition {
      condition     = var.alert_email != ""
      error_message = "alert_email vacío dejaría ${local.name}-alerts sin suscriptores. Si el destino pasa a ser un canal de chat, suscríbelo aquí explícitamente antes de vaciar esta variable."
    }
  }
}

# El correo de confirmación de AWS lo tiene que abrir una persona: hasta ese
# clic la suscripción queda en PendingConfirmation y no entrega nada. La
# comprobación de que quedó Confirmed va en el runbook, no aquí — Terraform da
# por bueno el recurso en cuanto lo crea.
resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}
