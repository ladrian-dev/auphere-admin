"""Closed catalog for Sol | Terra | Luna.

Three LiteLLM ids, verbatim. No alias ``gpt-5.6``. Console PUT still
binds only the ``respond`` role. Companion and playground hops must
use an id from this set — a miss is a human 409, never a vendor
``acompletion`` fallback.
"""

from __future__ import annotations

SOL_MODEL_ID = "openai/gpt-5.6-sol"

RESPOND_MODELS: tuple[tuple[str, str], ...] = (
    (SOL_MODEL_ID, "Sol"),
    ("openai/gpt-5.6-terra", "Terra"),
    ("openai/gpt-5.6-luna", "Luna"),
)

RESPOND_MODEL_IDS: tuple[str, ...] = tuple(model_id for model_id, _ in RESPOND_MODELS)
RESPOND_MODEL_ID_SET: frozenset[str] = frozenset(RESPOND_MODEL_IDS)
RESPOND_ROLE: str = "respond"

# Same human phrase the channel uses when a hop cannot complete (QA-14).
HUMAN_TURN_ERROR = "Disculpa, tuve un inconveniente."


class UnknownCatalogModel(ValueError):
    """id not in Sol|Terra|Luna. Do not call ``acompletion``."""

    def __init__(self, model_id: str) -> None:
        super().__init__(model_id)
        self.model_id = model_id


def require_hop_model(model_id: str) -> str:
    """Refuse a hop whose id is outside the closed catalog."""
    if model_id not in RESPOND_MODEL_ID_SET:
        raise UnknownCatalogModel(model_id)
    return model_id


def hop_models_in_catalog(*model_ids: str) -> bool:
    """True when every non-empty id is Sol, Terra or Luna."""
    return all(model_id in RESPOND_MODEL_ID_SET for model_id in model_ids if model_id)


__all__ = [
    "HUMAN_TURN_ERROR",
    "RESPOND_MODELS",
    "RESPOND_MODEL_IDS",
    "RESPOND_MODEL_ID_SET",
    "RESPOND_ROLE",
    "SOL_MODEL_ID",
    "UnknownCatalogModel",
    "hop_models_in_catalog",
    "require_hop_model",
]
