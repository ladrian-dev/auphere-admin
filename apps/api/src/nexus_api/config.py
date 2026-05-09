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

    # Fernet key for tenant_credentials.encrypted_payload. Must be a urlsafe-base64
    # 32-byte key. Generate one with `python -c 'from cryptography.fernet import Fernet;
    # print(Fernet.generate_key().decode())'`. The default below is for tests/dev only.
    fernet_key: str = "RQ8j4zYQ3W3ofSt7pUJoKxTYwhZ8JkRdJ-T_Wc1G3xs="

    # Tenant resolver cache TTL (seconds). 1h matches channel-adapters spec.
    tenant_cache_ttl: int = 3600

    # Isolation enforcer behavior in dev: raise vs. warn. In prod we always raise.
    isolation_enforcer_raise_in_dev: bool = False

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
