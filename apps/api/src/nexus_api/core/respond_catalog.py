"""Closed console catalog for the client respond model (Fase 2).

Three LiteLLM ids, verbatim. No alias ``gpt-5.6``. Classify / Companion /
whisper are not in this catalog and cannot be chosen from the console PUT.
"""

from __future__ import annotations

RESPOND_MODELS: tuple[tuple[str, str], ...] = (
    ("openai/gpt-5.6-sol", "Sol"),
    ("openai/gpt-5.6-terra", "Terra"),
    ("openai/gpt-5.6-luna", "Luna"),
)

RESPOND_MODEL_IDS: tuple[str, ...] = tuple(model_id for model_id, _ in RESPOND_MODELS)
RESPOND_MODEL_ID_SET: frozenset[str] = frozenset(RESPOND_MODEL_IDS)
RESPOND_ROLE: str = "respond"

__all__ = [
    "RESPOND_MODELS",
    "RESPOND_MODEL_IDS",
    "RESPOND_MODEL_ID_SET",
    "RESPOND_ROLE",
]
