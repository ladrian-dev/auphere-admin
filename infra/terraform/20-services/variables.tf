variable "certificate_arn" {
  description = <<-EOT
    Override: ARN de un certificado ACM (eu-south-2) gestionado FUERA de
    este stack. Vacío = Terraform pide el cert él mismo (ver acm.tf) con
    los dominios del entorno.
  EOT
  type        = string
  default     = ""
}

variable "extra_certificate_arns" {
  description = <<-EOT
    Certificados ACM adicionales que el listener 443 sirve por SNI, aparte
    del por defecto. Para nombres que entran al MISMO ALB pero no están en
    el cert principal — en prod, ``webhooks.auphere.com``, que es por donde
    Meta entrega y que va sin proxy de Cloudflare.

    Deben estar ya ``ISSUED``: esto sólo los ata al listener. Se usa un
    cert aparte en vez de un SAN en el principal porque cambiar los SAN de
    un cert ACM lo reemplaza, y el reemplazo nace PENDING_VALIDATION — con
    un listener sirviendo tráfico real, la peor secuencia posible.
  EOT
  type        = list(string)
  default     = []
}

variable "https_enabled" {
  description = <<-EOT
    Crea el listener 443 y convierte el 80 en redirect. Requiere que el
    certificado esté ISSUED: con el cert en PENDING_VALIDATION el apply
    falla. La validación DNS es manual (auphere.com no está en esta
    cuenta), así que la secuencia es apply → crear CNAME → esperar ISSUED
    → apply -var https_enabled=true.
  EOT
  type        = bool
  default     = false
}

variable "image_tag" {
  description = <<-EOT
    Tag de imagen que corre el entorno. CI empuja el tag móvil
    ``staging`` en cada push a develop; prod se fija a un sha concreto
    en el tfvars del workspace (promoción explícita, WP-26).
  EOT
  type        = string
  default     = "staging"
}

variable "app_secret_keys" {
  description = <<-EOT
    Claves del secreto JSON nexus/<ws>/app que se inyectan como env vars
    en TODOS los servicios (mismo modelo que Railway+Doppler hoy: un set
    único por entorno). Añadir una clave aquí exige que exista en el
    secreto ANTES del siguiente deploy — ECS aborta el arranque de la
    task si un valueFrom no resuelve.
  EOT
  type        = list(string)
  default = [
    "NEXUS_DATABASE_URL",        # app → PgBouncer (WP-15)
    "NEXUS_DATABASE_URL_DIRECT", # Alembic + checkpointer LangGraph → Aurora directo
    "NEXUS_DATABASE_URL_RO",     # routers de lectura pesada → reader endpoint
    "DATABASE_URL",              # release.sh (psql) + Drizzle + PgBouncer → Aurora directo
    "NEXUS_REDIS_URL",
    "NEXUS_ADMIN_TOKEN",
    "NEXUS_WEBHOOK_HMAC_SECRET",
    "NEXUS_FERNET_KEY",
    "NEXUS_OPERATOR_FALLBACK_PHONE",
    "NEXUS_META_APP_SECRET",
    "NEXUS_META_WEBHOOK_VERIFY_TOKEN",
    "NEXUS_LANGFUSE_PUBLIC_KEY",
    "NEXUS_LANGFUSE_SECRET_KEY",
    "NEXUS_MEDIA_S3_BUCKET",
    "NEXUS_MEDIA_S3_REGION",
    "NEXUS_MEDIA_S3_ACCESS_KEY_ID",
    "NEXUS_MEDIA_S3_SECRET_ACCESS_KEY",
    "ANTHROPIC_API_KEY",
    # Consola de partners (PLAN-CONSOLE-V1). El interruptor global y la
    # clave PÚBLICA con la que la API verifica los JWT de 60 s del BFF; la
    # privada vive solo en Vercel. ``NEXUS_CONNECTOR_CONSENT_SECRET`` firma
    # los enlaces de consentimiento OAuth de conectores y desde 2026-08-16
    # la API se niega a arrancar en prod si lleva el valor de desarrollo.
    "NEXUS_CONSOLE_ENABLED",
    "NEXUS_CONSOLE_JWT_PUBLIC_KEY",
    "NEXUS_CONNECTOR_CONSENT_SECRET",
    "NEXUS_COMPOSIO_API_KEY",
    "NEXUS_COMPOSIO_WEBHOOK_SECRET",
    "NEXUS_PUBLIC_API_BASE_URL",
    "NEXUS_ADMIN_PANEL_BASE_URL",
    "NEXUS_META_APP_ID",
    "NEXUS_META_BUSINESS_MANAGER_ID",
    "NEXUS_META_CONFIG_ID_WA_CLOUD_API",
    "NEXUS_META_CONFIG_ID_WA_COEXISTENCE",
    "NEXUS_META_WEBHOOK_CALLBACK_URL",
    "NEXUS_EMBED_JWT_SECRET",
    "NEXUS_LANGFUSE_HOST",
    "OPENAI_API_KEY",
    "BROWSERBASE_API_KEY",
    "BROWSERBASE_PROJECT_ID",
  ]
}

variable "adot_image" {
  description = "Imagen del collector ADOT (sidecar OTLP→CloudWatch EMF). Pinear versión, no latest."
  type        = string
  default     = "public.ecr.aws/aws-observability/aws-otel-collector:v0.43.3"
}
