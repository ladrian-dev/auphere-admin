# Variables del workspace ``staging`` de 20-services.
#
#   terraform -chdir=infra/terraform/20-services workspace select staging
#   terraform -chdir=infra/terraform/20-services plan  -var-file=staging.tfvars -out=staging.plan
#   terraform -chdir=infra/terraform/20-services apply staging.plan
#
# Existe por el mismo motivo que ``prod.tfvars``, y se creó el 2026-09-01 al
# descubrir que staging tenía la misma mina sin desarmar.

# CI empuja este tag móvil en cada push a develop. Es el default de la
# variable; se fija aquí para que el fichero sea el registro completo de lo
# que corre el entorno y no dependa de un default que alguien cambie.
image_tag = "staging"

# ⚠️ SIN ESTO, UN APPLY DEJA STAGING SIN HTTPS.
#
# Mismo caso que prod: ``https_enabled`` tiene default ``false`` porque el
# listener 443 no se puede crear antes de que el cert esté ISSUED, pero
# staging pasó esa fase hace tiempo — el ALB ``nexus-staging`` sirve 443 con
# el cert ``6707ace4…`` (``api.staging.auphere.com`` + ``*.staging``), que
# gestiona este mismo stack. Un apply sin este flag planifica **destruir**
# ``aws_lb_listener.https[0]`` y devolver el 80 a forward.
#
# ``certificate_arn`` se queda vacío a propósito: el cert de staging lo crea
# y renueva Terraform (``aws_acm_certificate.public``). Fijarlo aquí lo
# convertiría en un override y el recurso gestionado quedaría huérfano.
https_enabled = true

# Requerida sin default (``versions.tf``), para ``terraform_remote_state``
# de la capa de red. prod la pasa con ``-var`` en el comando; aquí va en el
# fichero porque olvidarla es un error de comando, no de infraestructura.
state_bucket = "nexus-terraform-state-793033583982"

# ⚠️ SIN ESTO, UN APPLY BORRA EL PROXY.
#
# ``litellm_enabled`` tiene default ``false`` (litellm.tf), y el proxy de
# staging existe desde que se montó a mano: un apply sin este flag planifica
# destruir el servicio ECS, su secreto y su registro en Cloud Map. Prod no
# necesita el equivalente porque allí ``litellm_count`` es 0 por workspace,
# pase lo que pase con la variable.
litellm_enabled = true
