# Variables del workspace ``prod`` de 30-observability.
#
#   terraform -chdir=infra/terraform/30-observability workspace select prod
#   terraform -chdir=infra/terraform/30-observability plan  -var-file=prod.tfvars -out=prod.tfplan
#   terraform -chdir=infra/terraform/30-observability apply prod.tfplan
#
# Las variables de este fichero no tienen default a propósito: olvidarlo hace
# fallar el plan, y usar el del otro entorno lo para la guarda de ``aws_sns_topic``.

# Requerida para ``terraform_remote_state``.
state_bucket = "nexus-terraform-state-793033583982"

# Grafana solo existe en staging. Encenderlo aquí exige antes un cert con
# ``grafana.auphere.com`` (ver ``grafana_host`` en grafana.tf).
grafana_enabled = false

# La única suscripción del topic ``nexus-prod-alerts``, confirmada. Si se vacía, la
# guarda de ``aws_sns_topic`` para el plan: un topic sin suscriptores en prod es
# cero alarmas con aspecto de estar montadas.
alert_email = "contacto@ladrian.dev"

# ``alert_subscription_arn_to_import`` falta aquí a propósito: el repo es público y
# ese ARN permite dar de baja la suscripción sin firmar. Va por ``TF_VAR_``, y el
# comando está en infra/terraform/README.md y en la descripción de la variable.
