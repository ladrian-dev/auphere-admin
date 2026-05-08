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


settings = Settings()
