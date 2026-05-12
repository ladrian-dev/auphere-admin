"""Load + validate Connector seed YAMLs.

Each YAML in ``seeds/<slug>.yaml`` produces one :class:`ConnectorSeed`. The
loader is intentionally strict (Pydantic ``extra='forbid'``) so a typo'd
field fails the test suite, not production.

The seed runner (``seed_runner.py``) applies these to the DB via
``ON CONFLICT (slug) DO UPDATE``. ``auth_kind`` is treated as immutable —
changing it across runs raises ``ConnectorAuthKindChanged`` instead of
silently rewriting the row, since it implies a different credentials model.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_SEEDS_DIR = Path(__file__).resolve().parent / "seeds"


class ConnectorSeedInvalid(ValueError):
    """Raised when a seed YAML fails schema validation."""


class ConnectorSeedNotFound(LookupError):
    """Raised when the seed file does not exist."""


class ConnectorSeed(BaseModel):
    """Validated shape of a seed YAML row."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    slug: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    display_name: str = Field(min_length=1, max_length=200)
    vendor: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=40)
    capabilities: list[str] = Field(default_factory=list)
    auth_kind: str
    mcp_server_ref: str = Field(min_length=1, max_length=120)
    provider_meta: dict[str, Any] = Field(default_factory=dict)
    auto_enable_on_connect: bool = True
    auto_enable_destructive: bool = False
    consent_link_template_name: str | None = None
    status: str = "available"

    @field_validator("auth_kind")
    @classmethod
    def _check_auth_kind(cls, v: str) -> str:
        allowed = {
            "oauth_composio",
            "browser_credentials",
            "webhook_manual",
            "api_key",
        }
        if v not in allowed:
            msg = f"auth_kind must be one of {sorted(allowed)}; got {v!r}"
            raise ValueError(msg)
        return v

    @field_validator("status")
    @classmethod
    def _check_status(cls, v: str) -> str:
        if v not in {"available", "beta", "deprecated"}:
            msg = f"status must be available|beta|deprecated; got {v!r}"
            raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def _check_consistency(self) -> ConnectorSeed:
        # auto_enable_destructive only meaningful if auto_enable_on_connect.
        if self.auto_enable_destructive and not self.auto_enable_on_connect:
            msg = (
                "auto_enable_destructive=true requires auto_enable_on_connect=true; "
                f"slug={self.slug}"
            )
            raise ValueError(msg)
        # OAuth connectors must declare a consent template.
        if self.auth_kind == "oauth_composio" and not self.consent_link_template_name:
            msg = f"auth_kind=oauth_composio requires consent_link_template_name; slug={self.slug}"
            raise ValueError(msg)
        # Composio mcp refs follow the convention "composio:<toolkit>".
        if self.auth_kind == "oauth_composio" and not self.mcp_server_ref.startswith("composio:"):
            msg = (
                f"oauth_composio connector mcp_server_ref must start with "
                f"'composio:'; slug={self.slug} got {self.mcp_server_ref!r}"
            )
            raise ValueError(msg)
        # icon_url must be https when present.
        icon = self.provider_meta.get("icon_url")
        if icon and not str(icon).startswith("https://"):
            msg = f"provider_meta.icon_url must be https; slug={self.slug} got {icon!r}"
            raise ValueError(msg)
        return self


def list_seed_slugs(seeds_dir: Path | None = None) -> list[str]:
    """Return the sorted list of slugs available on disk."""
    base = seeds_dir or _SEEDS_DIR
    if not base.exists():
        return []
    return sorted(p.stem for p in base.glob("*.yaml"))


def load_seed(slug: str, seeds_dir: Path | None = None) -> ConnectorSeed:
    """Load a single seed by slug. Raises if file missing or invalid."""
    base = seeds_dir or _SEEDS_DIR
    path = base / f"{slug}.yaml"
    if not path.exists():
        msg = f"connector seed not found: {slug} (looked at {path})"
        raise ConnectorSeedNotFound(msg)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        msg = f"connector seed {slug}: invalid YAML — {exc}"
        raise ConnectorSeedInvalid(msg) from exc
    if not isinstance(raw, dict):
        msg = f"connector seed {slug}: top level must be a mapping"
        raise ConnectorSeedInvalid(msg)
    try:
        seed = ConnectorSeed.model_validate(raw)
    except Exception as exc:
        msg = f"connector seed {slug}: schema validation failed — {exc}"
        raise ConnectorSeedInvalid(msg) from exc
    if seed.slug != slug:
        msg = (
            f"connector seed {slug}: file name and slug field mismatch (slug field = {seed.slug!r})"
        )
        raise ConnectorSeedInvalid(msg)
    return seed


def load_all_seeds(seeds_dir: Path | None = None) -> list[ConnectorSeed]:
    """Load every YAML in the seeds dir. Order: sorted by slug."""
    return [load_seed(s, seeds_dir) for s in list_seed_slugs(seeds_dir)]


__all__ = [
    "ConnectorSeed",
    "ConnectorSeedInvalid",
    "ConnectorSeedNotFound",
    "list_seed_slugs",
    "load_all_seeds",
    "load_seed",
]
