resource "aws_lb" "main" {
  name               = local.name
  load_balancer_type = "application"
  security_groups    = [local.network.alb_security_group_id]
  subnets            = local.network.public_subnet_ids

  # Los webhooks de Meta reintentan, pero un deploy no debería tirar el ALB.
  enable_deletion_protection = terraform.workspace == "prod"
}

resource "aws_lb_target_group" "api" {
  name        = "${local.name}-api"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = local.network.vpc_id
  target_type = "ip"

  # WP-03: /health/ready valida Postgres+Redis — un deploy con el wiring
  # roto nunca recibe tráfico. Liveness queda en el healthcheck del contenedor.
  health_check {
    path                = "/health/ready"
    interval            = 15
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
    matcher             = "200"
  }

  deregistration_delay = 30
}

resource "aws_lb_listener" "https" {
  count = local.https_enabled ? 1 : 0

  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = local.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

# Certificados ADICIONALES del listener, servidos por SNI.
#
# El de arriba es el POR DEFECTO y cubre ``api.auphere.com``. Pero el
# webhook de Meta no entra por ese nombre: entra por
# ``webhooks.auphere.com`` (default de ``meta_webhook_callback_url``, y lo
# que el panel de Meta tiene configurado), y ese host va **sin proxy de
# Cloudflare** a propósito — Meta desactiva webhooks que responden lento y
# un salto de CDN con WAF en la ruta de entrada es riesgo sin beneficio.
# Sin un cert que cubra ese nombre, el ALB presenta el de api y Meta corta
# el TLS.
#
# Se declara aquí porque el 2026-08-19, en el corte a AWS, este cert se
# añadió con ``aws elbv2 add-listener-certificates`` para desbloquear la
# ventana. Un ``apply`` no se lo llevaría —no es un recurso declarado— pero
# eso es justo el problema: infraestructura que sostiene la entrada de
# producción y no está en el código.
#
# Por qué un cert aparte y no un SAN en el de arriba: cambiar los
# ``subject_alternative_names`` de un cert ACM lo **reemplaza**, y el nuevo
# nace ``PENDING_VALIDATION``. Con un listener sirviendo tráfico real eso es
# la peor secuencia posible. El extra ya está ``ISSUED`` y cubre los dos
# nombres, así que atarlo por SNI no cambia nada en caliente.
resource "aws_lb_listener_certificate" "extra" {
  for_each = local.https_enabled ? toset(var.extra_certificate_arns) : toset([])

  listener_arn    = aws_lb_listener.https[0].arn
  certificate_arn = each.value
}

# Con HTTPS activo: 80 redirige a 443. Sin él (cert aún sin emitir): 80
# forwardea directo — suficiente para humo, nunca para webhooks de Meta.
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  dynamic "default_action" {
    for_each = local.https_enabled ? [] : [1]
    content {
      type             = "forward"
      target_group_arn = aws_lb_target_group.api.arn
    }
  }

  dynamic "default_action" {
    for_each = local.https_enabled ? [1] : []
    content {
      type = "redirect"

      redirect {
        port        = "443"
        protocol    = "HTTPS"
        status_code = "HTTP_301"
      }
    }
  }
}
