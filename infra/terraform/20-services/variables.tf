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
    # Firma las credenciales de dispositivo de la beta 2 (Requisito 6.3). El
    # guard de ``config.py`` se niega a arrancar en producción con el valor de
    # fábrica; en staging solo avisa. La clave tiene que existir en el secreto
    # ANTES de aparecer aquí, o ECS aborta el arranque de la task.
    "NEXUS_DEVICE_TOKEN_SECRET",
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
    # Correo transaccional (Resend). Sin estas dos, ``email_enabled`` es False
    # y ``operator_alert_email`` es None: los recibos mensuales de partner se
    # generan pero no se envían, y las ``platform_alert`` del platform-watcher
    # (DLQ, ráfagas de error) no salen de CloudWatch — nadie se entera.
    "NEXUS_RESEND_API_KEY",
    "NEXUS_OPERATOR_ALERT_EMAIL",
    # ─── Membresías y cobro (spec 005) ────────────────────────────────────
    # Esta lista la comparten los dos workspaces. Las cuatro existen en
    # ``nexus/staging/app`` desde 2026-09-13; en ``nexus/prod/app`` **NO**.
    #
    # ⚠️  ANTES DEL PRÓXIMO ``apply`` EN EL WORKSPACE ``prod``, pobla el secreto
    #     de prod o las cinco tareas de producción no arrancarán:
    #
    #   AWS_PROFILE=nexus ./infra/scripts/add_app_secret_keys.sh prod \
    #     NEXUS_CONSOLE_BASE_URL NEXUS_BILLING_API_KEY \
    #     NEXUS_BILLING_PUBLIC_KEY NEXUS_BILLING_WEBHOOK_SECRET
    #
    # Una definición de tarea que pide una clave ausente del secreto **no
    # arranca** (``ResourceInitializationError: did not contain json key``), y
    # este apply se lleva por delante los cinco servicios del entorno. El orden
    # es secreto primero, Terraform después. Runbook completo en
    # ``docs/go-live-consola-y-teammates.md``.
    #
    # Las tres de ``BILLING`` van juntas o no van: ``billing_enabled`` es todo
    # o nada (config.py), así que con dos de tres el cobro sigue apagado y el
    # despliegue miente. ``CONSOLE_BASE_URL`` es a donde el proveedor devuelve
    # al partner tras pagar: sin ella la API se niega a arrancar en prod desde
    # el guard de config.py, que es mejor que cobrar y perder el acuse.
    #
    "NEXUS_CONSOLE_BASE_URL",
    "NEXUS_BILLING_API_KEY",
    "NEXUS_BILLING_PUBLIC_KEY",
    "NEXUS_BILLING_WEBHOOK_SECRET",
    # ─── Entrar con Google (spec 006, Requisito 5) ─────────────────────────
    # Las tres van juntas o no van: el guard de ``config.py`` rechaza el
    # arranque con Google a medias, porque una consola que pinta el botón y
    # una API que falla al canjear el código da un error del proveedor que no
    # se parece en nada a la causa.
    #
    # ``CLIENT_ID`` y ``REDIRECT_URI`` no son credenciales —el primero viaja
    # en la URL de autorización, el segundo lo conoce cualquiera que mire el
    # navegador— pero viven aquí igual que ``NEXUS_META_APP_ID`` o
    # ``NEXUS_CONSOLE_BASE_URL``: el criterio de esta lista no es «es
    # secreto», es «cambia con el entorno». Y cambian: cada entorno tiene su
    # propio cliente OAuth, para que un compromiso en staging no sea el
    # ``client_secret`` de producción.
    #
    # ⚠️  Pobla LOS DOS secretos ANTES del próximo apply. Esta lista la
    #     comparten los dos workspaces, y una task que pide una clave ausente
    #     **no arranca** — se llevaría por delante los cinco servicios:
    #
    #   AWS_PROFILE=nexus ./infra/scripts/add_app_secret_keys.sh staging \
    #     NEXUS_GOOGLE_CLIENT_ID NEXUS_GOOGLE_CLIENT_SECRET NEXUS_GOOGLE_REDIRECT_URI
    #   AWS_PROFILE=nexus ./infra/scripts/add_app_secret_keys.sh prod \
    #     NEXUS_GOOGLE_CLIENT_ID NEXUS_GOOGLE_CLIENT_SECRET NEXUS_GOOGLE_REDIRECT_URI
    #
    "NEXUS_GOOGLE_CLIENT_ID",
    "NEXUS_GOOGLE_CLIENT_SECRET",
    "NEXUS_GOOGLE_REDIRECT_URI",
  ]
}

variable "adot_image" {
  description = "Imagen del collector ADOT (sidecar OTLP→CloudWatch EMF). Pinear versión, no latest."
  type        = string
  default     = "public.ecr.aws/aws-observability/aws-otel-collector:v0.43.3"
}
