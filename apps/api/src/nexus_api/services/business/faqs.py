"""Las preguntas frecuentes del negocio — spec 047 (requisito 8.1).

Las del negocio, que heredan todos sus agentes; las propias de un agente van en
su AgentSpec. Una pregunta «Sugerido · confirma» (``suggested``, requisito 18.3)
no se da por cierta hasta que una persona la confirma: no entra en el prompt.
Archivar es borrar.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models.business import BusinessFaq
from nexus_api.services.business import section_write, writes
from nexus_api.services.business.sections import Actor

Q_MAX: Final = 300
A_MAX: Final = 2000
MAX_FAQS: Final = 200


class FaqError(ValueError):
    def __init__(self, code: str, field: str) -> None:
        super().__init__(f"{field}: {code}")
        self.code = code
        self.field = field


def _clean(q: str | None, a: str | None) -> tuple[str, str]:
    q = (q or "").strip()
    a = (a or "").strip()
    if not q:
        raise FaqError("question_required", "q")
    if len(q) > Q_MAX:
        raise FaqError("question_too_long", "q")
    if not a:
        raise FaqError("answer_required", "a")
    if len(a) > A_MAX:
        raise FaqError("answer_too_long", "a")
    return q, a


async def list_faqs(session: AsyncSession, *, archived: bool = False) -> list[BusinessFaq]:
    stmt = sa.select(BusinessFaq).where(BusinessFaq.tenant_id == require_current_tenant())
    if not archived:
        stmt = stmt.where(BusinessFaq.archived_at.is_(None))
    rows = await session.scalars(stmt.order_by(BusinessFaq.position, BusinessFaq.created_at))
    return list(rows.all())


async def create_faq(
    session: AsyncSession,
    *,
    q: str,
    a: str,
    suggested: bool = False,
    actor: Actor,
    expected_revision: int | None = None,
    ctx: writes.WriteContext | None = None,
    faq_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID, writes.SectionWritten | None]:
    q, a = _clean(q, a)
    live = await list_faqs(session)
    if len(live) >= MAX_FAQS:
        raise FaqError("too_many_faqs", "q")
    row = BusinessFaq(
        id=faq_id or uuid.uuid4(),
        tenant_id=require_current_tenant(),
        q=q,
        a=a,
        suggested=suggested,
        position=max((f.position for f in live), default=-1) + 1,
    )

    async def change() -> None:
        session.add(row)

    written = await section_write.guarded_write(
        session,
        "faqs",
        ctx=section_write.context(actor, ctx),
        change=change,
        pointers=[f"/faqs/{row.id}"],
        expected_revision=expected_revision,
    )
    return row.id, written


async def _get(session: AsyncSession, faq_id: uuid.UUID, *, archived: bool = False) -> BusinessFaq:
    row = await session.get(BusinessFaq, faq_id)
    if row is None or row.tenant_id != require_current_tenant():
        raise LookupError("unknown faq")
    if row.archived_at is not None and not archived:
        raise LookupError("archived faq")
    return row


async def update_faq(
    session: AsyncSession,
    faq_id: uuid.UUID,
    changes: Mapping[str, Any],
    *,
    actor: Actor,
    expected_revision: int | None = None,
    ctx: writes.WriteContext | None = None,
) -> writes.SectionWritten | None:
    """``changes``: ``q``, ``a`` o ``suggested`` (confirmar una sugerida es
    ``suggested: false``). ``archived: false`` deshace su archivado."""
    row = await _get(session, faq_id, archived=changes.get("archived") is False)
    q, a = _clean(changes.get("q", row.q), changes.get("a", row.a))

    async def change() -> None:
        row.q, row.a = q, a
        if "suggested" in changes:
            row.suggested = bool(changes["suggested"])
        if changes.get("archived") is False:
            row.archived_at = None

    return await section_write.guarded_write(
        session,
        "faqs",
        ctx=section_write.context(actor, ctx),
        change=change,
        pointers=[f"/faqs/{faq_id}"],
        expected_revision=expected_revision,
    )


async def archive_faq(
    session: AsyncSession,
    faq_id: uuid.UUID,
    *,
    actor: Actor,
    expected_revision: int | None = None,
    ctx: writes.WriteContext | None = None,
) -> writes.SectionWritten | None:
    row = await _get(session, faq_id)

    async def change() -> None:
        row.archived_at = datetime.now(UTC)

    return await section_write.guarded_write(
        session,
        "faqs",
        ctx=section_write.context(actor, ctx),
        change=change,
        pointers=[f"/faqs/{faq_id}"],
        expected_revision=expected_revision,
    )


# ── adaptadores: deshacer y aplicar propuestas o lo leído ──────────────────


def _id(raw: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(raw))
    except (TypeError, ValueError):
        return None


async def _restore(
    session: AsyncSession, view: Mapping[str, Any] | None, ctx: writes.WriteContext
) -> writes.SectionWritten:
    target = list((view or {}).get("faqs") or [])
    wanted = {_id(item.get("id")): item for item in target if _id(item.get("id"))}
    last: writes.SectionWritten | None = None
    for row in await list_faqs(session, archived=True):
        item = wanted.pop(row.id, None)
        if item is None:
            if row.archived_at is None:
                last = await archive_faq(session, row.id, actor=ctx.actor, ctx=ctx) or last
            continue
        changes = {
            "q": item.get("q"),
            "a": item.get("a"),
            "suggested": bool(item.get("suggested")),
            "archived": False,
        }
        last = await update_faq(session, row.id, changes, actor=ctx.actor, ctx=ctx) or last
    for faq_id, item in wanted.items():
        _new, written = await create_faq(
            session,
            q=str(item.get("q") or ""),
            a=str(item.get("a") or ""),
            suggested=bool(item.get("suggested")),
            actor=ctx.actor,
            ctx=ctx,
            faq_id=faq_id,
        )
        last = written or last
    if last is None:
        raise writes.NothingWritten
    return last


async def _apply(
    session: AsyncSession, ops: Sequence[writes.Op], ctx: writes.WriteContext
) -> writes.SectionWritten:
    last: writes.SectionWritten | None = None
    for op in ops:
        parts = op.path.split("/")[1:]
        value = op.value if isinstance(op.value, Mapping) else {}
        if parts[:1] != ["faqs"]:
            raise FaqError("invalid_pointer", "path")
        if op.op == "add" and parts[1:] == ["-"]:
            _new, written = await create_faq(
                session,
                q=str(value.get("q") or ""),
                a=str(value.get("a") or ""),
                suggested=bool(value.get("suggested")),
                actor=ctx.actor,
                ctx=ctx,
            )
            last = written or last
            continue
        faq_id = _id(parts[1]) if len(parts) == 2 else None
        if faq_id is None:
            raise FaqError("invalid_pointer", "path")
        if op.op == "archive":
            last = await archive_faq(session, faq_id, actor=ctx.actor, ctx=ctx) or last
        elif op.op == "replace":
            last = await update_faq(session, faq_id, dict(value), actor=ctx.actor, ctx=ctx) or last
        else:
            raise FaqError("invalid_pointer", "path")
    if last is None:
        raise writes.NothingWritten
    return last


writes.register_section_adapter("faqs", restore=_restore, apply=_apply)


__all__ = ["FaqError", "archive_faq", "create_faq", "list_faqs", "update_faq"]
