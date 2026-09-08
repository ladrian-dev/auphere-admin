# Muestreo explícito de X-Ray (2026-09-08).
#
# La regla `Default` de AWS (prioridad 10000) está al 5% + reservoir 1/s y
# producía ~3,9 M trazas/mes (~19 USD) con un tráfico real de 0,07 req/s
# entre prod y staging juntos: casi todo era ruido de los crons del
# scheduler, no peticiones. Bajamos al 1% CONSERVANDO el reservoir en 1/s,
# que garantiza que siempre haya trazas aunque el ratio sea bajo.
# Ver Auphere/nexus/PLAN-COSTES-AWS-2026-09-01.md en el vault.
#
# ⚠️ DOS COSAS QUE NO SON OBVIAS:
#
# 1. Las reglas de muestreo de X-Ray son de CUENTA Y REGIÓN, no por VPC ni
#    por workspace. Esta regla gobierna prod Y staging por igual. Por eso se
#    crea UNA sola vez; declararla en los dos workspaces dejaría dos reglas
#    idénticas compitiendo a la misma prioridad.
#
# 2. Está anclada a `staging` sólo porque los apply de prod están
#    congelados a la espera de la migración pendiente (los taskdefs de prod
#    arrastran secretos que aún no existen en `nexus/prod/app`). Cuando esa
#    migración se haga, esto puede moverse a prod — pero NO se aplica en los
#    dos a la vez: primero se quita de aquí, luego se pone allí.
#
# Los 11 campos son obligatorios en la API CreateSamplingRule aunque valgan "*".
resource "aws_xray_sampling_rule" "base" {
  count = terraform.workspace == "staging" ? 1 : 0

  rule_name      = "nexus-base"
  priority       = 9000
  version        = 1
  reservoir_size = 1
  fixed_rate     = 0.01
  service_name   = "*"
  service_type   = "*"
  host           = "*"
  http_method    = "*"
  url_path       = "*"
  resource_arn   = "*"
}
