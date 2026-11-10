"""Settings, read once from the environment at start.

Only the token, the port and the concurrency come from the environment. The
budget the spec fixes (20 s per request, 2 MB of HTML — requirement 59.2) is a
constant here, not a knob: a renderer that can be configured to wait a minute
is a renderer that one day will.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

#: How the reader introduces itself to a site (same name its robots.txt rules
#: are matched against: ``nexus_api.services.business.reader.USER_AGENT``).
USER_AGENT: Final = "NexusReader/1.0 (+https://auphere.com/bot)"
MIN_TOKEN_CHARS: Final = 32


class ConfigError(Exception):
    """The service refuses to start."""


@dataclass(frozen=True)
class Settings:
    token: str
    host: str = "0.0.0.0"  # inside the task; reachable only from the runner's SG
    port: int = 8080
    max_concurrency: int = 2
    total_timeout_s: float = 20.0
    settle_timeout_s: float = 3.0
    max_html_bytes: int = 2 * 1024 * 1024
    max_body_bytes: int = 8 * 1024
    user_agent: str = USER_AGENT

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        source = os.environ if env is None else env
        token = source.get("NEXUS_RENDERER_TOKEN", "").strip()
        if len(token) < MIN_TOKEN_CHARS:
            raise ConfigError(
                f"NEXUS_RENDERER_TOKEN must be set (at least {MIN_TOKEN_CHARS} characters)"
            )
        port = _int(source, "NEXUS_RENDERER_PORT", 8080, low=1, high=65535)
        concurrency = _int(source, "NEXUS_RENDERER_MAX_CONCURRENCY", 2, low=1, high=8)
        return cls(token=token, port=port, max_concurrency=concurrency)


def _int(source: Mapping[str, str], name: str, default: int, *, low: int, high: int) -> int:
    raw = source.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if not low <= value <= high:
        raise ConfigError(f"{name} must be between {low} and {high}")
    return value


__all__ = ["MIN_TOKEN_CHARS", "USER_AGENT", "ConfigError", "Settings"]
