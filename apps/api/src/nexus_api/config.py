from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NEXUS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = "dev"
    log_level: str = "INFO"

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

    # Auth for admin endpoints. Better Auth replaces this in block G.
    admin_token: str = "dev-admin-token-change-me"

    # Generic HMAC secret kept for any future webhook with a simple HMAC scheme
    # (NOT YCloud — YCloud has its own ``t={ts},s={sig}`` shape, see below).
    webhook_hmac_secret: str = "dev-hmac-secret-change-me"

    # YCloud — Phase 1 BSP for WhatsApp.
    # Auphere is the YCloud customer; each tenant is a WABA migrated to that
    # BSP. Per-tenant API keys are a Phase 4+ white-label concern.
    ycloud_api_key: str = "dev-ycloud-key-change-me"
    ycloud_webhook_secret: str = "dev-ycloud-webhook-secret-change-me"
    ycloud_api_base_url: str = "https://api.ycloud.com/v2"
    # YCloud webhook signature timestamp tolerance (replay protection).
    ycloud_signature_tolerance_seconds: int = 300

    # Operator phone (E.164) used as recipient for ``alert_*`` templates when
    # the tenant has not configured ``tenants.owner_phone``. In Phase 1 this
    # is Lee. Templates for the tenant owner override this when present.
    operator_fallback_phone: str | None = None

    # Owner backchannel (ADR-018 / architecture/owner-backchannel.md).
    # ``auphere_owner_phone`` is the E.164 of the Auphere multi-tenant
    # number used to talk to ALL owners. Inbound webhooks from this number
    # route through ``/webhooks/ycloud/owner-channel``; outbound template
    # sends use this as ``from_phone``. ``auphere_owner_number_id`` is the
    # YCloud phone_number_id reserved for the same number — kept separate
    # because some YCloud endpoints take the id rather than the E.164.
    # ``auphere_owner_webhook_secret`` lets the owner-channel webhook have
    # its own signing secret distinct from the tenant business numbers
    # (operationally we may reuse ``ycloud_webhook_secret`` if the BSP
    # signs all events with the same secret).
    auphere_owner_phone: str | None = None
    auphere_owner_number_id: str | None = None
    auphere_owner_webhook_secret: str | None = None

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
    # same way before generating a presigned URL for YCloud to fetch.
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

    @property
    def is_prod(self) -> bool:
        return self.environment.lower() in {"prod", "production"}

    @property
    def is_dev(self) -> bool:
        return not self.is_prod


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
