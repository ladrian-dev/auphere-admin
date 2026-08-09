# TLS público del ALB — el cert que los webhooks de Meta exigen.
#
# El DNS de auphere.com NO vive en esta cuenta (aquí solo hay la hosted zone
# PRIVADA que crea Cloud Map), así que la validación es manual: Terraform
# PIDE el certificado y publica en los outputs los CNAME que hay que crear
# en el proveedor de DNS. Hasta que aparezcan, el cert queda
# ``PENDING_VALIDATION`` — y un listener HTTPS contra un cert sin emitir
# hace fallar el apply. De ahí el flag propio y las dos pasadas:
#
#   1. apply normal                → cert pedido + outputs con los registros
#   2. crear los CNAME y esperar a ``ISSUED`` (aws acm describe-certificate)
#   3. apply -var https_enabled=true → listener 443 + redirect 80→443
#
# Staging pide el comodín de su zona (``staging.auphere.com`` +
# ``*.staging.auphere.com``): ACM emite **un solo** registro de validación
# para un dominio y su comodín, así que añadir admin/grafana/langfuse de
# staging más adelante no cuesta ni un DNS más. Prod pide solo
# ``api.auphere.com`` — el resto de auphere.com es de la landing (Vercel) y
# no lo gobierna este stack.

locals {
  dns = {
    staging = {
      certificate_domain        = "staging.auphere.com"
      subject_alternative_names = ["*.staging.auphere.com"]
      hostname                  = "api.staging.auphere.com"
    }
    prod = {
      certificate_domain        = "api.auphere.com"
      subject_alternative_names = []
      hostname                  = "api.auphere.com"
    }
  }

  dns_cfg = local.dns[local.env]

  # ``certificate_arn`` sigue existiendo como override para un cert
  # gestionado fuera de este stack; vacío = lo gestiona Terraform.
  manage_certificate = var.certificate_arn == ""

  certificate_arn = (
    var.certificate_arn != ""
    ? var.certificate_arn
    : (length(aws_acm_certificate.public) > 0 ? aws_acm_certificate.public[0].arn : "")
  )

  https_enabled = var.https_enabled && local.certificate_arn != ""
}

resource "aws_acm_certificate" "public" {
  count = local.manage_certificate ? 1 : 0

  domain_name               = local.dns_cfg.certificate_domain
  subject_alternative_names = local.dns_cfg.subject_alternative_names
  validation_method         = "DNS"

  # Renovar/reemplazar un cert en uso por un listener exige el nuevo antes
  # de soltar el viejo.
  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Name = "${local.name}-public"
  }
}
