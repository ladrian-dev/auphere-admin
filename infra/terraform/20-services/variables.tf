variable "certificate_arn" {
  description = <<-EOT
    ARN del certificado ACM (eu-west-1) para el listener HTTPS del ALB.
    Vacío = el ALB nace solo con listener HTTP :80 — suficiente para el
    primer humo de staging antes de tener DNS; NUNCA aceptable en prod
    (webhooks de Meta exigen HTTPS).
  EOT
  type        = string
  default     = ""
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
    "NEXUS_DATABASE_URL",
    "DATABASE_URL", # release.sh (psql) + Drizzle
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
  ]
}

variable "adot_image" {
  description = "Imagen del collector ADOT (sidecar OTLP→CloudWatch EMF). Pinear versión, no latest."
  type        = string
  default     = "public.ecr.aws/aws-observability/aws-otel-collector:v0.43.3"
}
