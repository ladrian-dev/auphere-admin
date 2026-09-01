from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The dev/test default Fernet key (see ``fernet_key`` below). Hoisted to a
# module constant so the production secret guard can compare against it
# without duplicating the literal.
_DEV_FERNET_KEY = "RQ8j4zYQ3W3ofSt7pUJoKxTYwhZ8JkRdJ-T_Wc1G3xs="


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NEXUS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = "dev"
    log_level: str = "INFO"

    # ── WP-01 (plataforma v2, Fase 0): OTLP export ──────────────────────────
    # Master switch for shipping traces/metrics out of the process. Endpoint,
    # headers and sampler come from the standard OTEL_* env vars
    # (OTEL_EXPORTER_OTLP_ENDPOINT, OTEL_EXPORTER_OTLP_HEADERS,
    # OTEL_TRACES_SAMPLER=parentbased_traceidratio, OTEL_TRACES_SAMPLER_ARG).
    # Default OFF per execution rule 5 — flipped per environment.
    otel_enabled: bool = False

    database_url: str = "postgresql+asyncpg://nexus:nexus@localhost:5433/nexus"

    # WP-15 — tres URLs de base de datos:
    #   ``database_url``        → tráfico de la app; con PgBouncer delante va
    #                             en modo transaction (ver db_transaction_pooling).
    #   ``database_url_direct`` → Alembic y el checkpointer de LangGraph:
    #                             conexiones de sesión larga que NO deben pasar
    #                             por el pooler. Vacía = usa database_url.
    #   ``database_url_ro``     → réplica de lectura para los routers de solo
    #                             lectura pesada. Vacía = usa database_url.
    database_url_direct: str = ""
    database_url_ro: str = ""

    # WP-15 — activar cuando database_url apunta a un pooler en modo
    # transaction (PgBouncer): desactiva el cache de prepared statements de
    # asyncpg y hace únicos los nombres de statement, que es lo que rompe
    # con multiplexado de conexiones.
    db_transaction_pooling: bool = False

    @field_validator("database_url", "database_url_direct", "database_url_ro", mode="before")
    @classmethod
    def _coerce_async_driver(cls, v: object) -> object:
        # Railway's Postgres add-on exposes ``postgresql://...`` while the
        # SQLAlchemy + asyncpg stack expects ``postgresql+asyncpg://...``.
        # Normalise on read so operators can paste the platform URL
        # verbatim without learning the dialect tag.
        if isinstance(v, str) and v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        if isinstance(v, str) and v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        return v

    redis_url: str = "redis://localhost:6379/0"

    # WP-09 (plataforma v2, Fase 1): engine pool sizing. Sizing rule to keep:
    # replicas x (pool_size + max_overflow) < Postgres max_connections x 0.7.
    # With PgBouncer (WP-15) the ceiling becomes the pooler's, not Postgres'.
    # Defaults preserve the historical 10/20 shape until tuned per service.
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # Auth for admin endpoints. Better Auth replaces this in block G.
    admin_token: str = "dev-admin-token-change-me"

    # Generic HMAC secret kept for any future webhook with a simple HMAC scheme.
    webhook_hmac_secret: str = "dev-hmac-secret-change-me"

    # Meta WhatsApp Cloud API — direct Tech Provider integration. The only
    # WhatsApp provider (YCloud removed 2026-06-12).
    #
    # App ID and Configuration IDs are PUBLIC values from the Meta App
    # dashboard (https://developers.facebook.com/apps/957213733862330/).
    # The App Secret and Webhook Verify Token live in Doppler — change
    # them via env vars only, never inline.
    meta_app_id: str = "957213733862330"
    meta_app_secret: str = "dev-meta-app-secret-change-me"
    # The webhook verify token used for the *app-level* callback (Meta's
    # GET ``hub.verify_token`` handshake when the URL is registered in the
    # app dashboard). Per-tenant verify tokens used by ``subscribed_apps``
    # overrides live in ``tenant_credentials.encrypted_payload``.
    meta_webhook_verify_token: str = "dev-meta-verify-token-change-me"
    # Configuration IDs for Embedded Signup v4 — frontend passes one of
    # these to ``FB.login({config_id})``.
    meta_config_id_wa_cloud_api: str = "1976547999669619"
    meta_config_id_wa_coexistence: str = "27787800820807899"
    # Business Manager hosting the Meta App (Facelad SpA — Tech Provider).
    meta_business_manager_id: str = "342042661294231"
    # Graph API version pinned at the client level. Bump as Meta rolls
    # new majors — keep the pin so the deprecation surface is explicit.
    meta_graph_api_version: str = "v22.0"
    # Webhook callback URL passed to ``subscribed_apps`` per tenant.
    # Defaults to the production webhooks subdomain; override in dev via
    # ``NEXUS_META_WEBHOOK_CALLBACK_URL`` (an ngrok tunnel pointing to
    # ``/webhook/meta`` on the local API).
    meta_webhook_callback_url: str = "https://webhooks.auphere.com/webhook/meta"
    # Toggle ``appsecret_proof`` on outbound Graph API calls. Auphere has
    # ``Require App Secret Proof`` ON in the Meta App since 2026-05-21, so
    # this stays True in every environment that talks to the real API.
    meta_require_appsecret_proof: bool = True

    # TikTok Business Messaging API — single Auphere developer app, same
    # Tech-Provider shape as Meta: every tenant authorises *this* app over
    # their own Business Account.
    #
    # ``tiktok_enabled`` is the master switch and defaults OFF. TikTok gates
    # Business Messaging behind a Data Security & Privacy Review that is
    # still in flight, so production runs with the channel dark until the
    # App ID / App Secret are real. Keeping the flag means the prod secret
    # guard below can be strict *without* blocking every deploy in the
    # meantime.
    tiktok_enabled: bool = False
    tiktok_app_id: str = ""
    tiktok_app_secret: str = "dev-tiktok-app-secret-change-me"
    # Where TikTok redirects after the business owner authorises the app.
    # Must match the redirect URL registered in the developer app exactly —
    # TikTok rejects the code exchange on any mismatch.
    # Must match the **TikTok account holder redirect URL** registered on the
    # app (My Apps > App Detail > Basic Information) character for character —
    # TikTok re-validates it at token-exchange time, and a trailing slash is
    # enough to fail it. Note this is a different field in the TikTok console
    # from the "Advertiser redirect URL", which belongs to the ad-account flow
    # we do not use.
    tiktok_redirect_uri: str = "https://api.auphere.com/admin/integrations/tiktok/callback"
    # The base authorisation URL is **issued by TikTok**, not constructed by
    # us: it lives at My Apps > App Detail > Basic Information > "TikTok
    # account holder authorization URL" and only appears once the app has the
    # TikTok Accounts permission. Paste it here verbatim; the service appends
    # a signed ``state`` for CSRF protection, which TikTok echoes back.
    #
    # Empty by default because guessing the format would produce a URL that
    # looks plausible and fails at authorisation time — better to fail fast
    # with "not configured".
    tiktok_authorize_url: str = ""
    # Signs the OAuth ``state`` that carries the connecting tenant through
    # TikTok's redirect. Deliberately NOT the app secret: this key protects a
    # cross-tenant write on our side, and reusing TikTok's credential for it
    # would mean a TikTok-side leak also lets an attacker graft accounts onto
    # arbitrary tenants.
    tiktok_oauth_state_secret: str = "dev-tiktok-state-secret-change-me-min-32"
    # Callback registered per tenant on the Business Messaging webhook
    # configuration. Override in dev with a tunnel pointing at
    # ``/webhook/tiktok`` on the local API.
    tiktok_webhook_callback_url: str = "https://webhooks.auphere.com/webhook/tiktok"
    # API host + version pinned at the client level, same rationale as the
    # Graph API pin above.
    tiktok_api_base_url: str = "https://business-api.tiktok.com"
    tiktok_api_version: str = "v1.3"

    # Operator phone (E.164) used as recipient for ``alert_*`` templates when
    # the tenant has not configured ``tenants.owner_phone``. In Phase 1 this
    # is Lee. Templates for the tenant owner override this when present.
    operator_fallback_phone: str | None = None

    # WP-07: worker services expected to report a heartbeat, comma-separated.
    # Single-service deploys keep the default; after cutting over to the
    # split deployment set
    # ``NEXUS_EXPECTED_WORKER_SERVICES=nexus-runner,nexus-scheduler,nexus-egress``.
    # Consumed by GET /health/workers and by the platform watcher's
    # dead-worker alert.
    expected_worker_services: str = "nexus-worker"

    @property
    def expected_worker_services_list(self) -> tuple[str, ...]:
        return tuple(
            name.strip() for name in self.expected_worker_services.split(",") if name.strip()
        )

    # WP-06 (plataforma v2, Fase 0): destination for platform-level alerts
    # (queue backlog, DLQ entries, dead workers, cache-ratio collapse, Meta
    # failure bursts). Unset → alerts are logged at ERROR only.
    operator_alert_email: str | None = None

    # Owner backchannel (ADR-018 / architecture/owner-backchannel.md).
    # Auphere backchannel numbers live in the ``auphere_owner_channels``
    # registry (provider=meta, with phone_number_id + encrypted access
    # token per row). No settings-based fallback — registering a channel
    # in the panel is the only way to enable the backchannel.

    # Fernet key for tenant_credentials.encrypted_payload. Must be a urlsafe-base64
    # 32-byte key. Generate one with `python -c 'from cryptography.fernet import Fernet;
    # print(Fernet.generate_key().decode())'`. The default below is for tests/dev only.
    fernet_key: str = "RQ8j4zYQ3W3ofSt7pUJoKxTYwhZ8JkRdJ-T_Wc1G3xs="

    # Tenant resolver cache TTL (seconds). 1h matches channel-adapters spec.
    tenant_cache_ttl: int = 3600

    # WP-30: entre cuántas réplicas se reparte el límite de partner cuando
    # el limitador pierde Redis y cae al cubo en memoria. Debe seguir al
    # ``max_capacity`` de la política de autoescalado de la API (WP-24,
    # 6 en producción): con ese valor, el techo global durante una caída
    # de Redis se parece al límite configurado en el peor caso y es más
    # estricto en el normal. Subirlo afloja el freno; bajarlo lo aprieta.
    rate_limit_fallback_replicas: int = 6

    # ── WP-28: obsolescencia de la API pública ────────────────────────────
    # Fecha en que ``/v1`` quedó congelada, en formato HTTP-date (RFC 9745).
    # Es un hecho, no una promesa.
    api_v1_deprecation_date: str = "Mon, 11 Aug 2026 00:00:00 GMT"
    # Fecha de apagado (RFC 8594). VACÍA a propósito: anunciar una fecha
    # que nadie ha acordado con el partner es peor que no anunciar ninguna.
    # Se rellena cuando Facelad confirme su plan de migración.
    api_v1_sunset_date: str = ""

    # Isolation enforcer behavior in dev: raise vs. warn. In prod we always raise.
    isolation_enforcer_raise_in_dev: bool = False

    # Composio (Block L / ADR-011) — OAuth proxy for non-channel connectors.
    # API key from composio.dev dashboard. Empty in dev means the live client
    # is not built; the API falls back to FakeComposioClient automatically.
    # auth_config_ids are NOT stored here — Composio dashboard is the single
    # source of truth, resolved via ``composio.auth_configs.list(toolkit=...)``
    # at consent-initiation time.
    composio_api_key: str = ""
    composio_webhook_secret: str = "dev-composio-webhook-secret-change-me"
    # Public base URL of the API — used to build the OAuth callback the user
    # is redirected to after consenting on the provider. Local dev keeps it
    # blank and uses http://localhost:8000 via the frontend BFF.
    public_api_base_url: str = "http://localhost:8000"
    # Public base URL of the operator panel. Used to bounce a browser back
    # into the UI after a provider redirect (TikTok's OAuth callback lands on
    # the API, not on the panel, and a person should not end up staring at a
    # JSON body).
    admin_panel_base_url: str = "http://localhost:3000"

    # HMAC secret for consent_token signing (see services/connectors/consent_token.py).
    # Used to mint the magic-link tokens we ship to tenant owners via WhatsApp.
    connector_consent_secret: str = "dev-consent-secret-change-me-min-32-chars"

    # Block N: "Mejorar prompt" utility. Same provider abstraction the
    # worker uses for the agent runtime — Claude Sonnet 4.6 via LiteLLM —
    # but called inline from the API because the operation is
    # operator-interactive.
    llm_improve_model: str = "anthropic/claude-sonnet-4-6"

    # LiteLLM OSS proxy (Fase 1). Env names match the SDK docs
    # (``LITELLM_PROXY_API_BASE``) and also accept the ``NEXUS_`` prefix.
    # Virtual keys are a JSON map partner_id → sk-… — never the master key,
    # never ANTHROPIC/OPENAI vendor keys.
    litellm_proxy_api_base: str = ""
    litellm_proxy_virtual_keys: str = ""
    # ¿El proxy es un requisito para responder? (ADR-036)
    #
    # ``False`` = si no hay proxy configurado, el hop va al vendor directo.
    # ``True``  = su ausencia es un error ruidoso y el turno se descarta.
    #
    # El defecto es ``False`` a propósito: producción no lleva proxy
    # (``litellm.tf:23`` lo fija a staging) y antes de esta bandera la
    # ausencia enmudecía a todo tenant con partner sin error ni alarma —
    # el corte de 2 h 37 del 31-ago-2026. Staging lo pone a ``True``.
    llm_proxy_required: bool = False
    llm_improve_timeout_s: float = 30.0
    # Token budget guardrails so a runaway prompt doesn't bill us 100k
    # input tokens. ``max_input_chars`` is a cheap pre-LLM check; the
    # actual token count is enforced by the provider.
    improve_prompt_max_input_chars: int = 20_000
    improve_prompt_max_output_tokens: int = 4_000

    # CO-01: el Companion de la consola. Modelo propio (rol ``companion``,
    # migración 0090) y no compartido con los agentes de cliente: el
    # Companion es la cara de Auphere ante el partner y aquí no se ahorra.
    # El techo de duración corta un run desbocado; el tope mensual por
    # partner es lo que impide que el gasto dependa de la buena fe.
    llm_companion_model: str = "openai/gpt-5.6-sol"
    # Techo de duración de un run. Además de cortar un turno desbocado es el
    # corte del reaper Y del lector: un run más viejo que esto está muerto lo
    # ejecute quien lo ejecute, que es lo único que un proceso puede afirmar
    # sin saber qué réplica lo lanzó. Alineado con el ``maxDuration`` del
    # proxy SSE de la consola.
    companion_run_max_seconds: float = 300.0
    # Turnos por miembro y minuto. El tope mensual se mide sobre runs
    # TERMINADOS, así que sin esto una ráfaga de POST paralelos lo pasa de
    # largo antes de que ninguno cierre su fila.
    companion_runs_per_minute: int = 15
    # Turnos SIMULTÁNEOS por miembro. El límite por minuto no acota el
    # trabajo en vuelo cuando cada run dura minutos: con 15/min y un techo
    # de 300 s, un solo miembro puede tener ~75 runs vivos a la vez, cada
    # uno con su tarea, su conexión y su gasto. Esto sí lo acota, y se
    # cuenta sobre ``companion.runs`` en ``running`` que aún no han
    # cumplido su techo de duración — los huérfanos de un proceso muerto no
    # bloquean a nadie.
    companion_max_concurrent_runs: int = 3
    # Turnos que corren A LA VEZ en este proceso, sumando todos los miembros
    # de todos los partners. El tope de arriba es por persona y no acota nada
    # global: con N personas trabajando son 3·N tareas en el mismo event loop,
    # cada una con hasta 25 llamadas de herramienta que abren su propia
    # transacción contra un pool de 10+20 conexiones **compartido con el
    # webhook de WhatsApp**. Once personas a la vez bastan para que el camino
    # que gana el dinero espere por una conexión.
    #
    # Doce deja holgura para ~4 personas trabajando en paralelo sin que el
    # pool se acerque al límite, y es un número que se sube cuando el runtime
    # se mueva al worker y deje de compartir proceso.
    companion_max_process_runs: int = 12
    # Cuánto espera un turno por su hueco antes de rendirse. Sin plazo, el
    # cajón se queda quieto sin explicación y el reaper acaba matando el run
    # igual al cumplir su techo de duración — o sea, la persona habría
    # esperado para nada. Con plazo, el turno cierra diciendo qué pasó.
    companion_queue_timeout_s: float = 30.0
    # CO-02. Tope DURO de consultas por turno; el modelo además ve una
    # cuenta atrás (``budget_note``) para poder cerrar con elegancia en vez
    # de que lo corten a mitad. Y techo por consulta: una herramienta que
    # tarda más ya rompió la conversación, porque el usuario está mirando.
    companion_max_tool_calls_per_turn: int = 25
    companion_tool_timeout_s: float = 10.0
    # CO-04. Cuánto vive una propuesta sin decidir. Quince minutos es lo que
    # fija la investigación (§10) y es **la única fuente de la cuenta atrás**:
    # el backend manda ``expires_at`` en ``hitl.requested`` y la interfaz no
    # recalcula el plazo por su cuenta, así que subirlo o bajarlo aquí mueve
    # también lo que la persona ve. La caducidad se aplica al LEER la acción,
    # sin cron: un proceso más que puede fallar en silencio es peor que una
    # comparación de fechas en el sitio donde importa.
    companion_action_ttl_seconds: float = 900.0
    # La palanca de coste que el D6 del ADR-033 nombra y que no existía:
    # "para bajar coste se baja ``effort``, no se apaga el pensamiento".
    # Viaja como ``output_config: {"effort": …}`` y NO como
    # ``reasoning_effort``: ese segundo lo traduce LiteLLM inyectando su
    # propio ``thinking``, y por el camino se pierde
    # ``display: "summarized"`` — que es justo lo que el cajón pinta.
    #
    # Medido contra Anthropic (2026-08-21, sonnet-4-6, misma pregunta):
    #   sin effort → 484 tokens de salida · 1.208 chars de pensamiento
    #   effort low →  58 tokens de salida ·    12 chars de pensamiento
    # Ocho veces menos salida. Y ocho veces menos pensamiento, que es
    # exactamente el riesgo: con menos razonamiento el modelo también elige
    # peor la herramienta.
    #
    # Por eso el defecto es ``None`` = sin cambio. La palanca existe, está
    # medida y está documentada; encenderla es una decisión que se toma
    # **después** de tener evals contra el modelo real (P6), porque hoy no
    # hay forma de ver la degradación que provoca.
    companion_effort: str | None = None
    # CO-08. Dónde avisa Auphere de un ticket de soporte abierto desde la
    # consola. Vacío = no se manda correo, y **no pasa nada**: el ticket
    # existe igual, con su fila de auditoría, su notificación al partner y
    # su línea de log estructurada (``console.support.ticket_opened``), que
    # es la que alimenta la agregación por ``topic``. Lo que falta sin esto
    # es el empujón, no el registro.
    support_alert_email: str = ""
    # Tickets de soporte por persona y minuto. Bajo a propósito: abrir un
    # ticket es un acto deliberado y con confirmación humana delante, así
    # que una ráfaga solo puede ser un bucle.
    console_support_tickets_per_minute: int = 6

    # ── Block N: WhatsApp media + multimodal ────────────────────────────────
    # S3 (or S3-compatible — Cloudflare R2, MinIO) for media storage. All
    # inbound media (audio/image/document/video/sticker) goes into the bucket
    # keyed by tenant + wamid + extension; outbound media is uploaded the
    # same way before generating a presigned URL for Meta to fetch.
    media_s3_bucket: str = ""
    media_s3_region: str = "us-east-1"
    # When ``endpoint_url`` is set we hit a non-AWS endpoint (R2, MinIO).
    media_s3_endpoint_url: str | None = None
    media_s3_access_key_id: str = ""
    media_s3_secret_access_key: str = ""
    # En ECS/Fargate no hay claves: las credenciales las da el TASK ROLE y
    # boto3 las resuelve solo por su cadena por defecto (el cliente ya pasa
    # ``aws_access_key_id=None`` cuando no hay clave). Sin este flag, el
    # gate de abajo exigía claves explícitas y el almacenamiento de media
    # se quedaba en memoria en AWS, silenciosamente. Es opt-in y no
    # implícito para que en dev y en los tests siga sin activarse por
    # accidente al haber un bucket configurado.
    media_s3_use_default_credentials: bool = False
    media_s3_presign_ttl_seconds: int = 300  # 5 min — enough for Meta to fetch
    # If true, attempt server-side encryption (SSE-S3). Cloudflare R2 ignores
    # this header; AWS S3 and MinIO honour it.
    media_s3_sse_enabled: bool = True
    # Inbound media size cap (MB). Anything larger we skip the download and
    # park the message as ``failed:media_too_large`` so we never blow memory.
    media_max_size_mb: int = 64

    # Multimodal LLM providers — separate from the conversational LLM
    # because Whisper (audio) and a vision-capable model (image / document)
    # may bill differently. All run through the LiteLLM gateway so the
    # interface is the same.
    llm_transcribe_model: str = "openai/whisper-1"
    llm_vision_model: str = "anthropic/claude-sonnet-4-6"
    # Per-turn timeouts. The pipeline awaits these in parallel for a single
    # multimodal turn so the worst case is the slowest leg.
    llm_transcribe_timeout_s: float = 25.0
    llm_vision_timeout_s: float = 25.0

    # ── Phase 2 (ADR-020): UCM formatter ────────────────────────────────────
    # When True the ``ucm_formatter`` node between ``respond`` and
    # ``checkpoint`` wraps the agent's text response into a UCM v1.0.0
    # payload and writes shadow-diff telemetry. The node is wired into
    # the graph topology unconditionally — this flag only toggles the
    # node's behaviour (passthrough vs emit).
    #
    # Default ``True`` because Nexus has no real customers in production
    # yet; we want the formatter exercising the path on every turn so the
    # shadow-diff data is available the moment Phase 3 ships the Playground.
    # If a production tenant lands before Phase 3, flip to ``False`` per
    # environment via ``NEXUS_USE_UCM_FORMATTER=false`` for instant rollback.
    use_ucm_formatter: bool = True

    @property
    def media_s3_enabled(self) -> bool:
        """True when enough creds are present to upload to S3. In dev with
        no S3 configured the platform stores media inline as base64 in
        ``messages.media_transcript`` for unit-test convenience."""
        return bool(
            self.media_s3_bucket
            and (
                self.media_s3_endpoint_url
                or (self.media_s3_access_key_id and self.media_s3_secret_access_key)
                or self.media_s3_use_default_credentials
            )
        )

    # Transactional email (Resend HTTP API) — used for the monthly partner
    # receipt. When the key is unset/placeholder the email step no-ops with a
    # warning, so the receipt is still generated and visible in the panel.
    resend_api_key: str = "dev-resend-key-change-me"
    receipt_from_email: str = "Auphere <facturacion@auphere.com>"

    @property
    def email_enabled(self) -> bool:
        key = self.resend_api_key
        return bool(key) and not key.startswith("dev-")

    # ── Partner console (PLAN-CONSOLE-V1, CP-03) ────────────────────────
    #
    # The console BFF (``apps/console``) never holds a backend credential.
    # Per request it mints a 60-second EdDSA (Ed25519) JWT with the user's
    # id, the partner id and a unique ``jti``; the backend verifies the
    # signature with the PUBLIC key below, checks the membership in
    # ``partner_memberships`` again, and rejects any replayed ``jti``.
    #
    # ``console_enabled`` is the master switch (rule 4 of the plan). It is
    # OFF by default everywhere; the per-partner switch is
    # ``partners.console_enabled`` (migration 0080). Both must be on.
    console_enabled: bool = False
    # D1 — cuota que recibe un cliente al crearse, en tokens de cuota C3.
    #
    # Antes de esto el único escritor de ``partner_allocations`` era
    # ``PUT /console/clients/{ref}/allocation``, a mano: todo cliente nuevo
    # nacía MUDO, sin error y sin aviso, porque ``allow_channel_turn`` exige
    # esa fila. Un mínimo fijo y no un reparto del included a propósito: no
    # se recalcula al dar de alta a otro cliente, así que el cap de uno no
    # baja solo cuando el partner añade otro. Caben 10 clientes en el
    # included de 500k; a partir de ahí el partner reparte desde Consumo.
    partner_default_client_allocation_tokens: int = 50_000
    # PEM-encoded Ed25519 public key ("-----BEGIN PUBLIC KEY-----"). Empty
    # means the console cannot authenticate anything — fail closed. Only a
    # public key lives here; the private half stays in the console.
    console_jwt_public_key: str = ""
    console_jwt_issuer: str = "nexus-console"
    console_jwt_audience: str = "nexus-api"
    # The longest life a console token may claim (``exp - iat``). The BFF
    # mints exactly this; anything longer is a forged or misconfigured
    # token and is rejected regardless of signature.
    console_jwt_max_ttl_seconds: int = 60
    # Clock skew tolerated between the BFF and the API, in seconds.
    console_jwt_leeway_seconds: int = 5

    @field_validator("console_jwt_public_key", mode="before")
    @classmethod
    def _pem_newlines(cls, v: object) -> object:
        # Secret managers and .env files usually cannot carry real newlines;
        # accept the escaped form so the PEM parses.
        if isinstance(v, str):
            return v.replace("\\n", "\n").strip().strip('"')
        return v

    @property
    def is_prod(self) -> bool:
        return self.environment.lower() in {"prod", "production"}

    @property
    def is_dev(self) -> bool:
        return not self.is_prod

    @model_validator(mode="after")
    def _forbid_dev_secrets_in_prod(self) -> "Settings":
        """Hard-fail boot in production if the WhatsApp/Meta credential
        secrets still carry their dev placeholders. Without this guard a
        prod deploy missing ``NEXUS_META_APP_SECRET`` /
        ``NEXUS_META_WEBHOOK_VERIFY_TOKEN`` boots silently with the
        ``change-me`` defaults and fails every Meta call + the webhook
        handshake — a footgun the security audit flagged. The Fernet key is
        included because the dev default would make stored BISUATs readable
        by anyone who knows the public placeholder.
        """
        if not self.is_prod:
            return self
        offenders: list[str] = []
        if "change-me" in self.meta_app_secret:
            offenders.append("NEXUS_META_APP_SECRET")
        if "change-me" in self.meta_webhook_verify_token:
            offenders.append("NEXUS_META_WEBHOOK_VERIFY_TOKEN")
        if self.fernet_key == _DEV_FERNET_KEY:
            offenders.append("NEXUS_FERNET_KEY")
        # Signs the Composio consent links partners now open from the console.
        if "change-me" in self.connector_consent_secret:
            offenders.append("NEXUS_CONNECTOR_CONSENT_SECRET")
        # Only enforced once the operator flips ``NEXUS_TIKTOK_ENABLED`` on —
        # until TikTok approves the Business Messaging review the channel
        # ships dark and there is nothing real to put here.
        if self.tiktok_enabled:
            if "change-me" in self.tiktok_app_secret:
                offenders.append("NEXUS_TIKTOK_APP_SECRET")
            if not self.tiktok_app_id:
                offenders.append("NEXUS_TIKTOK_APP_ID")
            if "change-me" in self.tiktok_oauth_state_secret:
                offenders.append("NEXUS_TIKTOK_OAUTH_STATE_SECRET")
        # The console is fail-closed without a verification key; booting
        # prod with the switch on and no key would make every console
        # request a 401 with a misleading cause.
        if self.console_enabled and not self.console_jwt_public_key.strip():
            offenders.append("NEXUS_CONSOLE_JWT_PUBLIC_KEY")
        if not self.composio_api_key.strip():
            offenders.append("NEXUS_COMPOSIO_API_KEY")
        if "change-me" in self.composio_webhook_secret:
            offenders.append("NEXUS_COMPOSIO_WEBHOOK_SECRET")
        if "localhost" in self.public_api_base_url:
            offenders.append("NEXUS_PUBLIC_API_BASE_URL")
        if "localhost" in self.admin_panel_base_url:
            offenders.append("NEXUS_ADMIN_PANEL_BASE_URL")
        if offenders:
            raise ValueError(
                "Refusing to boot in production with dev placeholder secrets: "
                + ", ".join(offenders)
                + ". Set them via Doppler/env before deploying."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
