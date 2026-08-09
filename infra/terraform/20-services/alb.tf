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
  count = var.certificate_arn == "" ? 0 : 1

  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

# Con certificado: 80 redirige a 443. Sin certificado (primer humo de
# staging): 80 forwardea directo.
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  dynamic "default_action" {
    for_each = var.certificate_arn == "" ? [1] : []
    content {
      type             = "forward"
      target_group_arn = aws_lb_target_group.api.arn
    }
  }

  dynamic "default_action" {
    for_each = var.certificate_arn == "" ? [] : [1]
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
