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

    @field_validator("database_url", mode="before")
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
    llm_improve_timeout_s: float = 30.0
    # Token budget guardrails so a runaway prompt doesn't bill us 100k
    # input tokens. ``max_input_chars`` is a cheap pre-LLM check; the
    # actual token count is enforced by the provider.
    improve_prompt_max_input_chars: int = 20_000
    improve_prompt_max_output_tokens: int = 4_000

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
