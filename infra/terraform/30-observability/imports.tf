# Lo que ya existe en AWS y hay que adoptar sin recrear. Este archivo se borra entero
# cuando esté aplicado en staging y en prod: ver infra/terraform/README.md.
#
# Los `for_each` van por el workspace porque todo esto solo existe en prod. Con ellos
# vacíos, staging no importa nada.

locals {
  imports_in_prod = terraform.workspace == "prod" ? toset(["prod"]) : toset([])
}

# ── La suscripción al topic ────────────────────────────────────────────
#
# El estado de los dos entornos guarda `aws_sns_topic_subscription.email` con un ARN
# que ya no existe: se creó pendiente de confirmar y se confirmó después con otro. El
# refresco la tira y el plan quiere crearla, con su correo de confirmación. Y un
# `import` a esa misma dirección **no hace nada y no avisa**: Terraform ve la dirección
# ocupada y lo salta. Comprobado con un plan el 2026-11-03. Por eso cambia de nombre:
# se olvida la entrada antigua, sin destruir, y se importa la buena en la dirección nueva.

removed {
  from = aws_sns_topic_subscription.email

  lifecycle {
    destroy = false
  }
}

# El ARN llega por variable y **no se escribe en ningún archivo**. Este repo es
# público, y esta suscripción se confirmó sin autenticar
# (`ConfirmationWasAuthenticated = false`): con su ARN, `sns:Unsubscribe` no pide
# firma. Publicarlo es dar a cualquiera la forma de dejar las alarmas de prod sin
# destinatario. No hay fuente de datos de suscripciones en el proveedor, y sin default
# olvidarla hace fallar el plan en vez de enseñar un `create`.
variable "alert_subscription_arn_to_import" {
  description = <<-EOT
    Solo para adoptar la suscripción de prod, y desaparece con este archivo. Si
    Terraform te lo pregunta, te falta (y no lo escribas en ningún archivo):
      export TF_VAR_alert_subscription_arn_to_import="$(aws sns list-subscriptions-by-topic --topic-arn arn:aws:sns:eu-south-2:793033583982:nexus-prod-alerts --query 'Subscriptions[0].SubscriptionArn' --output text)"
    En staging vale null, desde staging.tfvars.
  EOT
  type        = string

  validation {
    condition     = var.alert_subscription_arn_to_import == null || can(regex("^arn:aws:sns:[^:]+:[0-9]+:nexus-prod-alerts:", var.alert_subscription_arn_to_import))
    error_message = "alert_subscription_arn_to_import tiene que ser el ARN de una suscripción confirmada de nexus-prod-alerts. Si vale None o PendingConfirmation, el topic no tiene una: párate y mira antes de aplicar."
  }
}

import {
  for_each = local.imports_in_prod

  to = aws_sns_topic_subscription.alert_email[0]
  id = var.alert_subscription_arn_to_import
}

# ── Filtros y alarmas creados por CLI (alarms_db_auth.tf) ──────────────

import {
  for_each = local.db_auth_services

  to = aws_cloudwatch_log_metric_filter.db_auth_failed[each.key]
  id = "/nexus/prod/${each.key}:nexus-prod-db-auth-failed-${each.key}"
}

import {
  for_each = local.imports_in_prod

  to = aws_cloudwatch_log_metric_filter.scheduler_leader_failed[0]
  id = "/nexus/prod/scheduler:nexus-prod-scheduler-leader-failed"
}

import {
  for_each = local.imports_in_prod

  to = aws_cloudwatch_metric_alarm.db_auth_failures[0]
  id = "nexus-prod-db-auth-failures"
}

import {
  for_each = local.imports_in_prod

  to = aws_cloudwatch_metric_alarm.scheduler_leader_failed[0]
  id = "nexus-prod-scheduler-leader-failed"
}
