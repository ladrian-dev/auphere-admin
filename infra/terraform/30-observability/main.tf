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
  description = "Viene de <workspace>.tfvars. Si Terraform te lo pregunta, te falta -var-file."
  type        = string
}

# Sin default, como `grafana_enabled`: un valor por defecto aquí es lo que permitía
# que olvidar un -var cambiase un entorno. Ver el README.
variable "alert_email" {
  description = "Viene de <workspace>.tfvars. Si Terraform te lo pregunta, te falta -var-file. Destinatario de las alarmas del entorno; null en un entorno que no avisa a nadie."
  type        = string

  validation {
    condition     = var.alert_email == null || can(regex("^[^@ ]+@[^@ ]+$", var.alert_email))
    error_message = "alert_email tiene que ser una dirección de correo, o null si el entorno no avisa a nadie."
  }
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
  # de estar montada. En prod se rechaza, porque detrás hay clientes de Facelad
  # y Amacrux. En staging es lo decidido, y sus alarmas lo dicen con
  # `actions_enabled = false` (ver `alert_actions_enabled` en alarms.tf).
  #
  # La misma guarda para el otro error caro: pasar el -var-file de otro entorno,
  # que con el de prod en staging destruiría Grafana. Si cambia el destino, por
  # ejemplo a un canal de chat, suscríbelo aquí antes de vaciar esta variable.
  lifecycle {
    precondition {
      condition     = (var.alert_email != null) == local.alert_actions_enabled
      error_message = "alert_email no cuadra con el workspace ${terraform.workspace}: prod tiene que tener destinatario y staging ninguno. Lo normal es haber pasado el -var-file de otro entorno: usa ${terraform.workspace}.tfvars."
    }
  }
}

# El correo de confirmación de AWS lo tiene que abrir una persona: hasta ese
# clic la suscripción queda en PendingConfirmation y no entrega nada. La
# comprobación de que quedó Confirmed va en el runbook, no aquí — Terraform da
# por bueno el recurso en cuanto lo crea.
resource "aws_sns_topic_subscription" "alert_email" {
  count = var.alert_email == null ? 0 : 1

  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email

  # Estos dos solo los usa el proveedor al crear; AWS no los guarda, y una
  # suscripción importada los trae a null. Sin esto, cada plan enseñaría un cambio
  # que no toca nada en AWS.
  lifecycle {
    ignore_changes = [confirmation_timeout_in_minutes, endpoint_auto_confirms]
  }
}
