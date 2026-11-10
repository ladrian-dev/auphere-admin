"""Los embeddings del conocimiento — spec 047, T133 (research D14).

Titan v2 (1024 dimensiones) por el proxy de modelos, con el modelo de
``settings.knowledge_embedding_model``. Sin modelo configurado no hay embeddings:
los fragmentos se guardan sin vector y la recuperación es solo por palabras, que
es lo que hace un entorno de desarrollo sin credenciales.

Las pruebas ponen el suyo con ``set_embedder``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Final

import structlog

from nexus_api.config import get_settings

log = structlog.get_logger(__name__)

DIMENSIONS: Final = 1024

Embedder = Callable[[Sequence[str]], Awaitable[list[list[float]]]]

_override: Embedder | None = None
_override_set = False


def set_embedder(embedder: Embedder | None) -> None:
    """Para las pruebas: un embedder propio, o ``None`` para ninguno."""
    global _override, _override_set
    _override = embedder
    _override_set = True


def reset_embedder() -> None:
    global _override, _override_set
    _override = None
    _override_set = False


async def _litellm(texts: Sequence[str]) -> list[list[float]]:
    import litellm

    model = get_settings().knowledge_embedding_model
    assert model is not None
    response = await litellm.aembedding(model=model, input=list(texts), dimensions=DIMENSIONS)
    return [list(item["embedding"]) for item in response.data]


def get_embedder() -> Embedder | None:
    if _override_set:
        return _override
    return _litellm if get_settings().knowledge_embedding_model else None


async def embed(texts: Sequence[str]) -> list[list[float]] | None:
    """Los vectores de ``texts``, o ``None`` si no hay modelo o falla: quien
    llama sigue sin ellos (la búsqueda por palabras no los necesita)."""
    embedder = get_embedder()
    if embedder is None or not texts:
        return None
    try:
        vectors = await embedder(texts)
    except Exception as exc:
        log.warning("knowledge.embed_failed", error=type(exc).__name__, count=len(texts))
        return None
    if len(vectors) != len(texts) or any(len(v) != DIMENSIONS for v in vectors):
        log.warning("knowledge.embed_bad_shape", count=len(texts))
        return None
    return vectors


def as_literal(vector: Sequence[float]) -> str:
    """El vector como literal de pgvector, para ``CAST(:q AS vector)``."""
    return "[" + ",".join(f"{x:.7g}" for x in vector) + "]"


__all__ = [
    "DIMENSIONS",
    "Embedder",
    "as_literal",
    "embed",
    "get_embedder",
    "reset_embedder",
    "set_embedder",
]
