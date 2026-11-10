# Variables del workspace ``staging`` de 30-observability.
#
#   terraform -chdir=infra/terraform/30-observability workspace select staging
#   terraform -chdir=infra/terraform/30-observability plan  -var-file=staging.tfvars -out=staging.tfplan
#   terraform -chdir=infra/terraform/30-observability apply staging.tfplan
#
# Las variables de este fichero no tienen default a propósito: olvidarlo hace
# fallar el plan, y usar el del otro entorno lo para la guarda de ``aws_sns_topic``.

# Requerida para ``terraform_remote_state``.
state_bucket = "nexus-terraform-state-793033583982"

# ⚠️ SIN ESTO, UN APPLY BORRA GRAFANA.
#
# Grafana está en marcha en staging. Hasta el 2026-11-03 esta variable tenía
# default ``false``, el valor verdadero no estaba en ningún archivo, y un plan
# sin ``-var grafana_enabled=true`` destruía sus 11 recursos, secreto incluido.
grafana_enabled = true

# El tag móvil que empuja ``deploy-grafana.yml``. Coincide con el default de la
# variable; se fija aquí para que el fichero sea el registro completo del entorno.
grafana_image_tag = "staging"

# Staging no avisa a nadie (decisión de Luis, spec 051 R9.9): aparca sus servicios
# de 03:00 a 09:00 y cada mañana registra un ``worker_dead`` que no es un fallo.
# Sin destinatario no se crea la suscripción, y sus alarmas van con
# ``actions_enabled = false``: se miran en la consola.
alert_email = null

# Staging no adopta ninguna suscripción. Esta línea se va con imports.tf.
alert_subscription_arn_to_import = null
