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
    # from env (ANTHROPIC_API_KEY, OPENAI_API_KEY) when the caller doesn't pass
    # one explicitly; in dev/tests we run in-memory and never touch the wire.
    llm_classify_model: str = "anthropic/claude-haiku-4-5"
    llm_respond_model: str = "anthropic/claude-sonnet-4-6"
    llm_fallback_model: str = "openai/gpt-4o"
    llm_use_inmemory: bool = True

    # Redis Stream names.
    inbound_stream: str = "nexus:inbound"
    inbound_consumer_group: str = "nexus-worker"
    inbound_consumer_name: str = "worker-1"
    promote_channel: str = "nexus:agent_config:promote"

    # AgentLoader cache size (entries == number of distinct (tenant, version) pairs).
    agent_cache_size: int = 64


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
