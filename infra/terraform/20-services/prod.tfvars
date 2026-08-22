# Variables del workspace ``prod`` de 20-services.
#
#   terraform -chdir=infra/terraform/20-services workspace select prod
#   terraform -chdir=infra/terraform/20-services plan  -var-file=prod.tfvars -out=prod.plan
#   terraform -chdir=infra/terraform/20-services apply prod.plan
#
# Existe por un motivo concreto: ``image_tag`` tiene default ``staging`` y
# el workspace prod nunca lo fijó, así que **los cinco servicios de
# producción apuntaban a la imagen de develop**. Con un despliegue
# automático desde main eso sería peor todavía: main publicaría su imagen y
# prod seguiría ejecutando la de otra rama, sin que nada lo delatase.
#
# Se usa el tag móvil ``prod`` y no un sha fijo, que es lo que insinuaba la
# descripción original de la variable. El motivo es que main pasa a ser el
# disparador del despliegue (deploy-prod.yml): con main como fuente, la rama
# YA es el registro de qué corre en producción, y fijar además un sha
# obligaría a tocar Terraform en cada release — un paso manual que se acaba
# saltando. La vuelta atrás no se pierde: el workflow publica también
# ``nexus-api:<sha>``, así que revertir es apuntar aquí a ese sha y aplicar.
image_tag = "prod"

# ⚠️ SIN ESTO, UN APPLY TUMBA PRODUCCIÓN.
#
# ``https_enabled`` tiene default ``false`` porque el listener 443 no se
# puede crear hasta que el cert esté ISSUED, y la validación DNS de
# auphere.com es manual (esa zona no vive en esta cuenta). Pero prod pasó
# esa fase hace tiempo: el cert está emitido y el listener sirve el tráfico
# real desde el corte del 2026-08-19.
#
# Al no fijarlo aquí, un ``apply -var-file=prod.tfvars`` planificaba
# **destruir `aws_lb_listener.https[0]`** ("index [0] is out of range for
# count") y devolver el 80 a forward. Comprobado con un plan el
# 2026-08-19: `Plan: 0 to add, 1 to change, 1 to destroy`. Eso deja a Meta
# sin poder entregar por HTTPS y a Cloudflare sin origen válido en modo
# Full (strict) — los tres tenants mudos, sin un solo error en el código.
#
# `deploy-prod.yml` NO ejecuta Terraform (sólo construye imágenes, migra y
# rueda servicios), así que la mina sólo salta con un apply a mano. Que es
# exactamente cuando nadie está mirando el plan con cuidado.
https_enabled = true

# Cert SNI adicional del listener 443, para ``webhooks.auphere.com`` — el
# host por el que Meta entrega los webhooks, sin proxy de Cloudflare.
# Emitido a mano el 2026-08-19 durante el corte (api.auphere.com +
# webhooks.auphere.com como SAN) y atado entonces por CLI; se declara aquí
# para que deje de ser infraestructura fuera del código.
extra_certificate_arns = [
  "arn:aws:acm:eu-south-2:793033583982:certificate/ca6d3efb-2187-4347-973c-8340b33f7f72",
]
