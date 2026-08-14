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
