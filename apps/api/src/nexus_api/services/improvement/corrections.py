"""Corregir una respuesta desde la Bandeja — spec 047, T176 (requisitos 52.1 a
52.6; research D35; ``data-model.md`` §9).

Sobre una respuesta del agente, la persona del cliente escribe cómo debió
responder o la regla, y elige el alcance (todo el negocio o solo este agente):

1. **El borrador** (:func:`draft`): el sistema dice si es un **dato** o un
   **comportamiento** (:func:`classify`), propone una paráfrasis sin datos
   personales de lo que preguntó el cliente final (:mod:`.paraphrase`) y señala
   dónde quedan datos de un cliente final (:mod:`.pii`). Nada se aplica todavía.
2. **La revisión** (:func:`edit`): la persona edita la lección o la paráfrasis,
   con ``If-Match`` sobre la revisión del borrador (52.4).
3. **El envío** (:func:`send`). Con datos de un cliente final dentro, nada se
   guarda (``pii_present``, 52.5 y garantía 8). Si no:

   - un dato de **todo el negocio** entra en la ficha como pregunta frecuente
     (la paráfrasis y la lección), por ``faqs.create_faq`` y
     ``writes.write_section``: historial (``correction``), procedencia
     «Corregido por {persona} desde la Bandeja» (``inbox_correction``), auditoría
     (``business.correction_applied``), recompilación (el siguiente mensaje ya
     lo sabe) y el aviso al partner;
   - un dato de **solo este agente** entra en su conocimiento («Enseñar», 37.3);
   - un **comportamiento** llega al partner como propuesta (``proposals``,
     ``author = correction``) con el parche (una regla) y su prueba juntos,
     como una sugerencia, para que las mejoras del agente lo decidan igual. Se
     audita (``correction.proposed``) y se avisa (``agent.correction.proposed``).
4. **Deshacer** un dato (:func:`undo`): el cambio de la ficha por el historial, o
   la fuente del agente, que se quita (10 minutos para restaurarla).

El partner lee la lección y la paráfrasis (:func:`for_partner`); nunca el mensaje,
su id ni el de la conversación (C1).
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import (
    Agent,
    AuditLog,
    Channel,
    Conversation,
    Customer,
    KnowledgeDocument,
    Message,
    MessageDirection,
    NotificationKind,
)
from nexus_api.db.models.inbox_correction import LESSON_MAX, InboxCorrection
from nexus_api.services import inbox_view, proposal_state
from nexus_api.services.improvement import paraphrase as paraphrases
from nexus_api.services.improvement import pii

#: El tope de una regla del AgentSpec: lo que puede ser un comportamiento.
RULE_MAX: Final = 300
#: Los mensajes del cliente que se leen para parafrasear lo que preguntó.
CUSTOMER_MESSAGES: Final = 5
PROPOSED_ACTION: Final = "correction.proposed"

#: Una regla para el agente, no un dato del negocio: empieza por una orden o un
#: «no», o dice lo que debe o no debe hacer.
_BEHAVIOR: Final = re.compile(
    r"^\s*(no|nunca|jam[aá]s|siempre|evita|pregunta|pide|dile|di|deriva|pasa|ofrece|"
    r"ofrezcas|trata|responde|contesta|recuerda|usa|menciona|avisa|insiste)\b"
    r"|\b(no\s+(des|digas|ofrezcas|prometas|hables|aceptes|contestes|respondas|uses|"
    r"env[ií]es|hagas|confirmes|reserves|agendes))\b"
    r"|\b(deber[ií]as|debes|tienes que|hay que|regla|cuando (un|el) cliente)\b",
    re.I,
)


class CorrectionError(Exception):
    """Un «no» con su código (``lite-app-api.md`` §6)."""

    def __init__(self, code: str, status: int = 409, **extra: Any) -> None:
        super().__init__(code)
        self.code = code
        self.status = status
        self.extra = extra


@dataclass(frozen=True)
class Author:
    """La persona del cliente que corrige: quién y desde dónde."""

    user_id: str
    origin: str
    #: ``audit_log.actor`` (``client:<correo>``).
    actor: str
    #: Su nombre, para el aviso al partner.
    name: str


#: Lo que se hace al confirmar (los avisos): lo pone la ruta en su ``after_commit``.
AfterCommit = Callable[[Callable[[], Awaitable[None]]], None]


def classify(lesson: str) -> str:
    """``behavior`` si la lección es una regla para el agente; si no, ``data``."""
    return "behavior" if _BEHAVIOR.search(lesson or "") else "data"


def _clean_lesson(text: str) -> str:
    lesson = (text or "").strip()
    if not lesson:
        raise CorrectionError("lesson_required", 422)
    if len(lesson) > LESSON_MAX:
        raise CorrectionError("lesson_too_long", 422, max=LESSON_MAX)
    return lesson


async def _contact_names(session: AsyncSession, conversation_id: uuid.UUID) -> list[str | None]:
    name = await session.scalar(
        sa.select(Customer.name)
        .join(Conversation, Conversation.customer_id == Customer.id)
        .where(Conversation.id == conversation_id)
    )
    return [name]


def _relocate(row: InboxCorrection, names: list[str | None]) -> None:
    row.pii = pii.locate({"lesson": row.lesson, "paraphrase": row.paraphrase}, names=names)


async def _handling_agent(session: AsyncSession, conversation: Conversation) -> Agent | None:
    """Quién respondió: el agente del número o, sin él, el principal (como la
    Bandeja)."""
    channel = await session.get(Channel, conversation.channel_id)
    if channel is not None and channel.agent_id is not None:
        agent = await session.get(Agent, channel.agent_id)
        if agent is not None and agent.lifecycle != "archived":
            return agent
    agents = await inbox_view.client_agents(session)
    return await session.get(Agent, agents[0][0]) if agents else None


async def _customer_text(session: AsyncSession, reply: Message) -> str:
    """Lo que escribió el cliente antes de esa respuesta, desde la anterior."""
    previous = await session.scalar(
        sa.select(sa.func.max(Message.created_at)).where(
            Message.conversation_id == reply.conversation_id,
            Message.direction == MessageDirection.OUTBOUND,
            Message.created_at < reply.created_at,
        )
    )
    stmt = sa.select(Message.content, Message.media_transcript).where(
        Message.conversation_id == reply.conversation_id,
        Message.direction == MessageDirection.INBOUND,
        Message.created_at < reply.created_at,
        Message.skipped_reason.is_(None),
    )
    if previous is not None:
        stmt = stmt.where(Message.created_at > previous)
    rows = (
        await session.execute(stmt.order_by(Message.created_at.desc()).limit(CUSTOMER_MESSAGES))
    ).all()
    return "\n".join(
        (content or transcript or "").strip() for content, transcript in reversed(rows)
    ).strip()


async def draft(
    session: AsyncSession,
    *,
    conversation: Conversation,
    message_id: uuid.UUID,
    text: str,
    scope: str,
    author: Author,
    idempotency_key: str | None = None,
) -> tuple[InboxCorrection, bool]:
    """El borrador (ver el módulo). ``(fila, nueva)``: la misma
    ``Idempotency-Key`` de la misma persona devuelve el mismo borrador."""
    if idempotency_key:
        same = await session.scalar(
            sa.select(InboxCorrection).where(
                InboxCorrection.author_client_user_id == author.user_id,
                InboxCorrection.idempotency_key == idempotency_key,
            )
        )
        if same is not None:
            return same, False
    reply = await session.scalar(
        sa.select(Message).where(
            Message.id == message_id, Message.conversation_id == conversation.id
        )
    )
    if reply is None:
        raise LookupError("unknown message")
    said_by = inbox_view.author_of(
        reply.direction,
        reply.actor_kind,
        reply.actor_id,
        me="",
        names=inbox_view.Members(),
    )
    if said_by.kind != "agent":
        raise CorrectionError("not_an_agent_reply", 422)
    agent = await _handling_agent(session, conversation)
    if agent is None:
        raise CorrectionError("no_agent", 409)
    lesson = _clean_lesson(text)
    names = await _contact_names(session, conversation.id)
    proposed = await paraphrases.paraphrase(
        await _customer_text(session, reply), tenant_id=conversation.tenant_id, names=names
    )
    row = InboxCorrection(
        id=uuid.uuid4(),
        tenant_id=conversation.tenant_id,
        conversation_id=conversation.id,
        message_id=reply.id,
        agent_id=agent.id,
        author_client_user_id=author.user_id,
        origin=author.origin,
        scope=scope,
        kind=classify(lesson),
        lesson=lesson,
        paraphrase=proposed,
        status="draft",
        revision=1,
        idempotency_key=idempotency_key,
    )
    _relocate(row, names)
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row, True


async def get(session: AsyncSession, correction_id: uuid.UUID) -> InboxCorrection:
    """La corrección del cliente de la sesión (la RLS); la de otro no existe."""
    row = await session.get(InboxCorrection, correction_id, populate_existing=True)
    if row is None:
        raise LookupError("unknown correction")
    return row


def _expect(row: InboxCorrection, revision: int, *, draft_only: bool = True) -> None:
    if draft_only and row.status != "draft":
        raise CorrectionError("not_a_draft", 409, current_status=row.status)
    if row.revision != revision:
        raise CorrectionError("revision_conflict", 412)


async def edit(
    session: AsyncSession,
    row: InboxCorrection,
    *,
    expected_revision: int,
    lesson: str | None = None,
    paraphrase: str | None = None,
    paraphrase_set: bool = False,
) -> InboxCorrection:
    """Editar la lección o la paráfrasis (52.4). Cambiar la lección vuelve a decir
    de qué tipo es; los datos personales se vuelven a buscar en las dos."""
    _expect(row, expected_revision)
    if lesson is not None:
        row.lesson = _clean_lesson(lesson)
        row.kind = classify(row.lesson)
    if paraphrase_set:
        # Lo que escribe la persona se guarda tal cual: si lleva un dato, el
        # detector lo señala y el envío lo para.
        row.paraphrase = " ".join((paraphrase or "").split()) or None
    _relocate(row, await _contact_names(session, row.conversation_id))
    row.revision += 1
    row.updated_at = datetime.now(UTC)
    await session.flush()
    return row


async def send(
    session: AsyncSession,
    row: InboxCorrection,
    *,
    expected_revision: int,
    author: Author,
    after_commit: AfterCommit,
) -> InboxCorrection:
    """Aplicar un dato o proponer un comportamiento (ver el módulo)."""
    _expect(row, expected_revision)
    _relocate(row, await _contact_names(session, row.conversation_id))
    if row.pii:
        raise CorrectionError("pii_present", 422, pii=row.pii)
    if row.kind == "data":
        await _apply_fact(session, row, author)
        row.status = "applied"
    else:
        await _propose_rule(session, row, author, after_commit)
        row.status = "proposed"
    now = datetime.now(UTC)
    row.sent_at = now
    row.updated_at = now
    await session.flush()
    return row


async def _apply_fact(session: AsyncSession, row: InboxCorrection, author: Author) -> None:
    from nexus_api.services.business import faqs
    from nexus_api.services.business.sections import Actor
    from nexus_api.services.business.writes import WriteContext
    from nexus_api.services.knowledge.layers import KnowledgeError
    from nexus_api.services.knowledge.teach import teach

    if row.scope == "agent":
        note = row.lesson if not row.paraphrase else f"{row.paraphrase}\n{row.lesson}"
        try:
            doc = await teach(
                session,
                tenant_id=row.tenant_id,
                agent_id=row.agent_id,
                text=note,
                scope="agent",
                actor=author.actor,
                origin=author.origin,
            )
        except KnowledgeError as exc:
            raise CorrectionError(exc.code, exc.status) from None
        row.knowledge_document_id = doc.id
        return
    if not row.paraphrase:
        # La pregunta frecuente necesita su pregunta: la paráfrasis.
        raise CorrectionError("paraphrase_required", 422)
    actor = Actor(kind="client_user", id=author.user_id, origin=author.origin)
    try:
        _faq_id, written = await faqs.create_faq(
            session,
            q=row.paraphrase,
            a=row.lesson,
            actor=actor,
            ctx=WriteContext(
                actor=actor,
                source="inbox_correction",
                kind="correction",
                audit_actor=author.actor,
            ),
        )
    except faqs.FaqError as exc:
        raise CorrectionError(exc.code, 422, field=exc.field) from None
    row.applied_change_id = written.change_id if written is not None else None


async def _propose_rule(
    session: AsyncSession, row: InboxCorrection, author: Author, after_commit: AfterCommit
) -> None:
    from nexus_api.core.canonical import canonical_hash
    from nexus_api.services.agent_spec.patch import PatchError, apply_ops
    from nexus_api.services.agent_spec.schema import dump
    from nexus_api.services.agent_spec.validator import load_context, problems_out, validate_spec
    from nexus_api.services.builder.copilot import _rule_test
    from nexus_api.services.improvement.suggestions import legacy_chars_of, target_spec

    rule = row.lesson.strip()
    if len(rule) > RULE_MAX:
        raise CorrectionError("rule_too_long", 422, max=RULE_MAX)
    agent = await session.get(Agent, row.agent_id)
    if agent is None or agent.lifecycle == "archived":
        raise CorrectionError("agent_archived", 409)
    spec = await target_spec(session, agent)
    if spec is None:
        raise CorrectionError("no_version", 409)
    ops = [{"op": "add", "path": "/rules/-", "value": rule}]
    try:
        patched = apply_ops(dump(spec), ops)
    except PatchError:
        raise CorrectionError("invalid_proposal", 422) from None
    partner_id = await _partner_of(session, row.tenant_id)
    ctx = await load_context(session, partner_id=partner_id, legacy_chars=legacy_chars_of(spec))
    checked, problems = validate_spec(patched, ctx, author="correction")
    if checked is None or problems:
        raise CorrectionError("invalid_proposal", 422, problems=problems_out(problems))
    proposal = await proposal_state.propose(
        session,
        agent_id=agent.id,
        kind="agent_spec_patch",
        author="correction",
        diff={"ops": ops, "test": _rule_test(rule)},
        state_hash=canonical_hash(dump(spec)),
        summary=f"Añadir la regla «{rule}»",
        created_by=author.actor,
    )
    row.proposal_id = proposal.id
    session.add(
        AuditLog(
            tenant_id=row.tenant_id,
            actor=author.actor,
            action=PROPOSED_ACTION,
            target=f"agent:{agent.id}",
            after_json={
                "correction_id": str(row.id),
                "proposal_id": str(proposal.id),
                "scope": row.scope,
                "origin": author.origin,
            },
        )
    )
    tenant_id, data = (
        row.tenant_id,
        {
            "agent_id": str(agent.id),
            "correction_id": str(row.id),
            "by": author.name,
            "origin": author.origin,
        },
    )

    async def _notify() -> None:
        from nexus_api.services.channel_config import announce

        await announce(
            tenant_id=tenant_id, kind=NotificationKind.AGENT_CORRECTION_PROPOSED.value, data=data
        )

    after_commit(_notify)


async def _partner_of(session: AsyncSession, tenant_id: uuid.UUID) -> uuid.UUID | None:
    from nexus_api.db.models import Tenant

    tenant = await session.get(Tenant, tenant_id)
    return tenant.partner_id if tenant is not None else None


async def undo(session: AsyncSession, row: InboxCorrection, *, author: Author) -> InboxCorrection:
    """Deshacer un dato ya aplicado: el cambio de la ficha por el historial (si
    nadie escribió después; si no, ``412``), o la fuente del agente."""
    from nexus_api.services.business import history
    from nexus_api.services.business.sections import Actor
    from nexus_api.services.business.writes import WriteContext
    from nexus_api.services.knowledge.layers import remove

    if row.status != "applied":
        raise CorrectionError("not_applied", 409, current_status=row.status)
    if row.knowledge_document_id is not None:
        doc = await session.get(KnowledgeDocument, row.knowledge_document_id)
        if doc is not None:
            await remove(session, doc, actor=author.actor)
    elif row.applied_change_id is not None:
        actor = Actor(kind="client_user", id=author.user_id, origin=author.origin)
        try:
            await history.undo(
                session,
                row.applied_change_id,
                ctx=WriteContext(actor=actor, audit_actor=author.actor),
            )
        except history.AlreadyUndone:
            pass
        except history.UndoNotAvailable:
            raise CorrectionError("undo_not_available", 409) from None
    now = datetime.now(UTC)
    row.status = "undone"
    row.undone_at = now
    row.updated_at = now
    await session.flush()
    return row


async def for_partner(session: AsyncSession, *, agent_id: uuid.UUID) -> list[dict[str, Any]]:
    """Las correcciones de comportamiento de un agente tal como las ve el partner
    en sus mejoras (52.3): la lección y la paráfrasis. Nunca el mensaje, su id ni
    el de la conversación (C1)."""
    rows = (
        await session.scalars(
            sa.select(InboxCorrection)
            .where(
                InboxCorrection.agent_id == agent_id,
                InboxCorrection.kind == "behavior",
                InboxCorrection.status.in_(["proposed", "accepted", "rejected"]),
            )
            .order_by(InboxCorrection.sent_at.desc(), InboxCorrection.id)
        )
    ).all()
    return [
        {
            "id": str(r.id),
            "scope": r.scope,
            "status": r.status,
            "lesson": r.lesson,
            "paraphrase": r.paraphrase,
            "proposal_id": str(r.proposal_id) if r.proposal_id else None,
            "origin": r.origin,
            "sent_at": r.sent_at.isoformat() if r.sent_at else None,
        }
        for r in rows
    ]


__all__ = [
    "Author",
    "CorrectionError",
    "classify",
    "draft",
    "edit",
    "for_partner",
    "get",
    "send",
    "undo",
]
