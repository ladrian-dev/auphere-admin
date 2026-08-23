"""Companion two-partition retrieval (Fase 3 RAG). No kb.search.

Companion: two reads, two fences, two 20k caps. No ``client_ref`` →
playbook only. A foreign ref is treated as missing — never another
client's KB. The WhatsApp channel path stays on
``nexus_worker.runtime.console_context.load_knowledge_block`` (tenant
``knowledge_documents`` only).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from nexus_api.core.guardrails.untrusted import (
    TAG_KNOWLEDGE,
    TAG_PARTNER_PLAYBOOK,
    UNTRUSTED_PREAMBLE,
    fence,
)
from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    KnowledgeDocument,
    KnowledgeDocumentStatus,
    PartnerKnowledgeDocument,
    PartnerTenant,
)

PROMPT_CHAR_CAP = 20_000


def _capped_fenced(
    docs: list[tuple[str, str]],
    *,
    tag: str,
    cap: int = PROMPT_CHAR_CAP,
    preamble: str = UNTRUSTED_PREAMBLE,
) -> str:
    """Independent character cap per partition. Empty → ``\"\"``."""
    boxes: list[str] = []
    used = len(preamble)
    for title, body in docs:
        box = fence(body, tag=tag, title=title)
        if not box:
            continue
        sep = 2
        room = cap - used - sep
        if room <= 0:
            break
        if len(box) > room:
            inner = fence((body or "")[: max(room - 80, 0)], tag=tag, title=title)
            if inner and used + sep + len(inner) <= cap:
                boxes.append(inner)
            break
        boxes.append(box)
        used += sep + len(box)
    if not boxes:
        return ""
    return preamble + "\n\n" + "\n\n".join(boxes)


async def _indexed(session: Any, model: type[Any]) -> list[tuple[str, str]]:
    rows = (
        await session.execute(
            select(model.title, model.content_text)
            .where(model.status == KnowledgeDocumentStatus.INDEXED.value)
            .order_by(model.created_at.asc())
        )
    ).all()
    return [(str(title), text or "") for title, text in rows]


async def load_companion_knowledge_blocks(
    partner_id: uuid.UUID,
    *,
    client_ref: str | None,
    cap: int = PROMPT_CHAR_CAP,
) -> str:
    """Companion inject: playbook always; client KB only for *this* partner's ref."""
    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_partner_to_session(session, partner_id)
        playbook = await _indexed(session, PartnerKnowledgeDocument)

    playbook_block = _capped_fenced(playbook, tag=TAG_PARTNER_PLAYBOOK, cap=cap)

    client_block = ""
    ref = (client_ref or "").strip()
    if ref:
        async with sm() as session, session.begin():
            mapping = await session.get(PartnerTenant, (partner_id, ref))
            tenant_id = mapping.tenant_id if mapping is not None else None
        if tenant_id is not None:
            async with sm() as session, tenant_scoped_session(session, tenant_id):
                kb = await _indexed(session, KnowledgeDocument)
            client_block = _capped_fenced(kb, tag=TAG_KNOWLEDGE, cap=cap)

    return "\n\n".join(part for part in (playbook_block, client_block) if part)


__all__ = [
    "PROMPT_CHAR_CAP",
    "load_companion_knowledge_blocks",
]
