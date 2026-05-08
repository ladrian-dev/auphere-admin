from functools import lru_cache

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
    redis_url: str = "redis://localhost:6379/0"

    # Auth for admin endpoints. Better Auth replaces this in block G.
    admin_token: str = "dev-admin-token-change-me"

    # HMAC secret for inbound webhooks (e.g. YCloud). Block F wires the real value.
    webhook_hmac_secret: str = "dev-hmac-secret-change-me"

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
