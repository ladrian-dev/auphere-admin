"""Worker settings.

The worker reuses the ``NEXUS_*`` env vars from the API and adds runtime-only
fields (LiteLLM keys, model identifiers, stream names). Settings are layered:
the API's ``Settings`` covers DB/Redis/Fernet, this module covers everything
the agent runtime needs on top.
"""

from __future__ import annotations

from functools import lru_cache

from nexus_api.config import Settings as ApiSettings
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NEXUS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM — LiteLLM-compatible identifiers. Keys are read by LiteLLM directly
    # from env (ANTHROPIC_API_KEY) when the caller doesn't pass one explicitly.
    # Production runs the real LiteLLM provider; tests opt-in to
    # ``InMemoryProvider`` via ``NEXUS_LLM_USE_INMEMORY=true``.
    #
    # ``llm_use_inmemory`` previously defaulted to ``True``, which silently
    # caused production to serve the mock fallback string
    # ``[fallback:<model>] ok`` to real patients — incident 2026-05-28,
    # Boreal tenant. Default flipped to False; tests configure the setting
    # explicitly through fixtures.
    #
    # The fallback model lives hardcoded in ``main.py`` — see comment there.
    llm_classify_model: str = "anthropic/claude-haiku-4-5"
    llm_respond_model: str = "anthropic/claude-sonnet-4-6"
    llm_use_inmemory: bool = False

    # Redis Stream names.
    inbound_stream: str = "nexus:inbound"
    inbound_consumer_group: str = "nexus-worker"
    inbound_consumer_name: str = "worker-1"
    promote_channel: str = "nexus:agent_config:promote"

    # AgentLoader cache size (entries == number of distinct (tenant, version) pairs).
    agent_cache_size: int = 64

    # ── Langfuse (block H) ────────────────────────────────────────────────
    # Empty / unset → noop client. Useful for tests and pre-prod. When
    # the cloud workspace is provisioned set ``NEXUS_LANGFUSE_PUBLIC_KEY``
    # + ``NEXUS_LANGFUSE_SECRET_KEY`` and the SDK kicks in.
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"
    langfuse_environment: str = "dev"

    # Cron tick overrides (test fixtures use these to drop seconds → ms).
    health_check_tick_seconds: float = 3600.0
    no_show_scrape_tick_seconds: float = 3600.0
    cost_rollup_tick_seconds: float = 3600.0
    isolation_watcher_tick_seconds: float = 60.0

    # ── Continuous evals (roadmap E2.3) ───────────────────────────────────
    # OFF by default: when on, the cron runs the eval suite against each
    # tenant's ACTIVE config on a schedule, making real LLM calls per case.
    # Enable per environment once API keys + datasets are in place.
    continuous_eval_enabled: bool = False
    continuous_eval_tick_seconds: float = 21_600.0  # 6 hours

    # ── Memory tool retention (Fase B) ────────────────────────────────────
    # Daily sweep of agent_memory_versions older than 30 days. Tests
    # override to a sub-second tick so the cron loop fires inside the
    # test deadline.
    memory_retention_tick_seconds: float = 86_400.0  # 1 day


@lru_cache
def get_worker_settings() -> WorkerSettings:
    return WorkerSettings()


@lru_cache
def get_api_settings() -> ApiSettings:
    """Convenience re-export — keeps callers from importing both modules."""
    from nexus_api.config import get_settings

    return get_settings()


def reset_settings_cache() -> None:
    get_worker_settings.cache_clear()
