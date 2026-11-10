"""Lo que el turno sabe del conocimiento — spec 047, T133 (requisitos 38.1 a 38.4;
research D14).

- **Si cabe** en el presupuesto del agente (el del negocio más el suyo; por defecto
  20.000 caracteres, ``settings.knowledge_char_budget``), va entero, como datos
  vallados: el prompt cambia poco y la caché se aprovecha (38.1).
- **Si no cabe**, búsqueda híbrida (38.2):
  - por palabras, con la configuración ``spanish`` de Postgres;
  - semántica, con pgvector, si hay embeddings;
  - las dos fusionadas por rangos (RRF, k = 60);
  - **filtradas por cliente y capa dentro de la propia consulta** y exactas: no hay
    índice ANN compartido (38.4).
- Cada elección devuelve sus **fuentes** (documento y, en la búsqueda, fragmento)
  para guardarlas con la respuesta (``turn_sources``, 38.3).

Lo propio de un hermano no entra por ninguna de las dos vías (garantía 9).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Final, Literal

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.config import get_settings
from nexus_api.services.knowledge.embeddings import as_literal, embed
from nexus_api.services.knowledge.layers import visible_documents

#: Fusión de rangos: el ``k`` de la literatura.
RRF_K: Final = 60
#: Candidatos por cada vía antes de fusionar.
CANDIDATES: Final = 50
_WORD = re.compile(r"[0-9A-Za-zÀ-ÿ]{3,}")


@dataclass
class KnowledgePick:
    """Lo que entra en el turno: ``docs`` en orden (título, texto) y sus fuentes."""

    mode: Literal["none", "full", "search"]
    docs: list[tuple[str, str]] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)


def _tsquery(text: str) -> str | None:
    """Las palabras de la pregunta unidas con «o»: una pregunta larga rara vez
    contiene todas las palabras de un fragmento."""
    words = sorted({w.lower() for w in _WORD.findall(text or "")})
    return " | ".join(words) if words else None


#: El filtro de cliente y capa va **dentro** de cada vía (38.2, garantía 9). Cada
#: vía lee ``knowledge_chunks`` por su índice ``(tenant_id, agent_id)`` y solo al
#: final se unen los ganadores con su texto y su título: sin arrastrar vectores.
_LAYER = """c.tenant_id = :tenant
       AND (c.agent_id IS NULL OR c.agent_id = :agent)
       AND EXISTS (
           SELECT 1 FROM knowledge_documents d
            WHERE d.tenant_id = c.tenant_id AND d.id = c.document_id
              AND d.removed_at IS NULL AND d.status = 'indexed'
       )"""

_SEARCH_SQL = (
    """
WITH kw AS (
    SELECT c.id, row_number() OVER (ORDER BY ts_rank(c.tsv, q) DESC, c.id) AS r
      FROM knowledge_chunks c, to_tsquery('spanish', :words) AS q
     WHERE CAST(:words AS text) IS NOT NULL
       AND c.tsv @@ q
       AND """
    + _LAYER
    + """
     ORDER BY ts_rank(c.tsv, q) DESC, c.id
     LIMIT :n
){semantic_cte},
hits AS (
    SELECT id FROM kw{semantic_union}
)
SELECT c.id, c.document_id, c.ordinal, c.text, d.title,
       COALESCE(1.0 / (:k + kw.r), 0){semantic_score} AS score
  FROM hits
  JOIN knowledge_chunks c ON c.id = hits.id AND c.tenant_id = :tenant
  JOIN knowledge_documents d ON d.tenant_id = c.tenant_id AND d.id = c.document_id
  LEFT JOIN kw ON kw.id = c.id{semantic_join}
 ORDER BY score DESC, c.document_id, c.ordinal
 LIMIT :n
"""
)

_SEMANTIC = {
    "semantic_cte": """,
sem AS (
    SELECT v.chunk_id AS id,
           row_number() OVER (
               ORDER BY v.embedding <#> CAST(:vector AS halfvec), v.chunk_id
           ) AS r
      FROM knowledge_chunk_vectors v
     WHERE v.tenant_id = :tenant
       AND (v.agent_id IS NULL OR v.agent_id = :agent)
       AND EXISTS (
           SELECT 1 FROM knowledge_documents d
            WHERE d.tenant_id = v.tenant_id AND d.id = v.document_id
              AND d.removed_at IS NULL AND d.status = 'indexed'
       )
     ORDER BY v.embedding <#> CAST(:vector AS halfvec), v.chunk_id
     LIMIT :n
)""",
    "semantic_union": "\n    UNION\n    SELECT id FROM sem",
    "semantic_score": " + COALESCE(1.0 / (:k + sem.r), 0)",
    "semantic_join": "\n  LEFT JOIN sem ON sem.id = c.id",
}
_KEYWORDS_ONLY = dict.fromkeys(_SEMANTIC, "")


def search_sql(*, semantic: bool) -> str:
    return _SEARCH_SQL.format(**(_SEMANTIC if semantic else _KEYWORDS_ONLY))


async def search(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    agent_id: uuid.UUID | None,
    query: str,
    *,
    limit: int = CANDIDATES,
) -> list[dict[str, Any]]:
    """Fragmentos por relevancia, de las capas del agente. Exacta: sin índice ANN."""
    vectors = await embed([query]) if query.strip() else None
    params: dict[str, Any] = {
        "tenant": tenant_id,
        "agent": agent_id,
        "words": _tsquery(query),
        "n": limit,
        "k": RRF_K,
    }
    if vectors:
        params["vector"] = as_literal(vectors[0])
    rows = (await session.execute(sa.text(search_sql(semantic=bool(vectors))), params)).all()
    return [
        {
            "chunk_id": r.id,
            "document_id": r.document_id,
            "ordinal": r.ordinal,
            "text": r.text,
            "title": r.title,
            "score": float(r.score),
        }
        for r in rows
    ]


async def pick(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    agent_id: uuid.UUID | None,
    query: str,
    *,
    budget: int | None = None,
) -> KnowledgePick:
    """Lo que entra en el turno de ``agent_id``, dentro de ``budget`` caracteres."""
    budget = budget or get_settings().knowledge_char_budget
    docs = await visible_documents(session, tenant_id, agent_id)
    if not docs:
        return KnowledgePick(mode="none")
    total = sum(len(d.content_text or "") for d in docs)
    if total <= budget:
        return KnowledgePick(
            mode="full",
            docs=[(d.title, d.content_text or "") for d in docs],
            sources=[
                {
                    "kind": "knowledge",
                    "ref": str(d.id),
                    "layer": "agent" if d.agent_id else "business",
                }
                for d in docs
            ],
        )
    chosen: list[tuple[str, str]] = []
    sources: list[dict[str, Any]] = []
    used = 0
    for hit in await search(session, tenant_id, agent_id, query):
        size = len(hit["text"])
        if used + size > budget:
            continue
        used += size
        chosen.append((str(hit["title"]), str(hit["text"])))
        sources.append(
            {
                "kind": "knowledge",
                "ref": str(hit["document_id"]),
                "chunk": int(hit["ordinal"]),
            }
        )
    return KnowledgePick(mode="search", docs=chosen, sources=sources)


__all__ = ["CANDIDATES", "RRF_K", "KnowledgePick", "pick", "search", "search_sql"]
