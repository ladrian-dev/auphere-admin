"""«Corregir esta respuesta» desde la Bandeja — spec 047, T176 (requisitos 52.1 a
52.6; ``contracts/lite-app-api.md`` §3). Solo módulo ``inbox``.

- ``POST /inbox/{conversation_id}/messages/{message_id}/corrections``
  ``{text, scope: business | agent}``: el borrador, con su tipo (``data`` o
  ``behavior``), la paráfrasis propuesta y dónde hay datos de un cliente final
  (``pii``: campo, tipo y posiciones; nunca los datos). Con ``Idempotency-Key``,
  repetirlo devuelve el mismo borrador;
- ``PATCH /corrections/{id}`` ``{lesson?, paraphrase?}`` con ``If-Match``: la
  persona revisa y edita (52.4);
- ``POST /corrections/{id}/send`` con ``If-Match``: un dato se aplica al momento
  y un comportamiento llega al partner como propuesta. Con datos de un cliente
  final dentro, ``422 pii_present`` y no se guarda nada (52.5);
- ``POST /corrections/{id}/undo``: deshacer un dato aplicado.

Lo que hace cada paso vive en ``services/improvement/corrections.py``. Estas
respuestas no repiten el mensaje del cliente: llevan la lección, que escribió la
persona, y la paráfrasis, que no lleva datos personales.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, StringConstraints

from nexus_api.db.models import Agent
from nexus_api.db.models.inbox_correction import LESSON_MAX, PARAPHRASE_MAX, InboxCorrection
from nexus_api.services import inbox_view
from nexus_api.services.improvement import corrections as svc

from ..business import required_revision
from .deps import LiteScope, lite_scope

router = APIRouter()

INBOX = lite_scope("inbox")

Lesson = Annotated[str, StringConstraints(min_length=1, max_length=LESSON_MAX)]


class CorrectionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: Cómo debió responder, o la regla.
    text: Lesson
    #: «Todo el negocio» o «Solo este agente».
    scope: Literal["business", "agent"]


class CorrectionPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lesson: Lesson | None = None
    paraphrase: Annotated[str, StringConstraints(max_length=PARAPHRASE_MAX)] | None = None


class PiiOut(BaseModel):
    """Dónde hay un dato de un cliente final: el campo, el tipo y sus posiciones."""

    field: Literal["lesson", "paraphrase"]
    kind: Literal["email", "document", "phone", "name"]
    start: int
    end: int


class LiteAgentRefOut(BaseModel):
    id: uuid.UUID
    name: str


class CorrectionOut(BaseModel):
    id: uuid.UUID
    revision: int
    status: str
    kind: Literal["data", "behavior"]
    scope: Literal["business", "agent"]
    lesson: str
    paraphrase: str | None
    pii: list[PiiOut]
    agent: LiteAgentRefOut
    applied_change_id: uuid.UUID | None = None
    proposal_id: uuid.UUID | None = None
    created_at: datetime
    sent_at: datetime | None = None
    undone_at: datetime | None = None


def _author(scope: LiteScope) -> svc.Author:
    return svc.Author(
        user_id=scope.principal.user_id,
        origin=scope.origin,
        actor=scope.principal.actor,
        name=scope.person_name,
    )


async def _out(scope: LiteScope, row: InboxCorrection) -> CorrectionOut:
    agent = await scope.session.get(Agent, row.agent_id)
    return CorrectionOut(
        id=row.id,
        revision=row.revision,
        status=row.status,
        kind=row.kind,  # type: ignore[arg-type]
        scope=row.scope,  # type: ignore[arg-type]
        lesson=row.lesson,
        paraphrase=row.paraphrase,
        pii=[PiiOut.model_validate(p) for p in row.pii or []],
        agent=LiteAgentRefOut(id=row.agent_id, name=agent.name if agent is not None else "—"),
        applied_change_id=row.applied_change_id,
        proposal_id=row.proposal_id,
        created_at=row.created_at,
        sent_at=row.sent_at,
        undone_at=row.undone_at,
    )


async def _refused(
    scope: LiteScope, row: InboxCorrection | None, exc: svc.CorrectionError
) -> HTTPException:
    detail: dict[str, object] = {"code": exc.code, **exc.extra}
    if exc.code == "revision_conflict" and row is not None:
        detail["current"] = (await _out(scope, row)).model_dump(mode="json")
    return HTTPException(status_code=exc.status, detail=detail)


async def _correction(scope: LiteScope, correction_id: uuid.UUID) -> InboxCorrection:
    try:
        return await svc.get(scope.session, correction_id)
    except LookupError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail={"code": "unknown_correction"}
        ) from None


@router.post(
    "/inbox/{conversation_id}/messages/{message_id}/corrections",
    response_model=CorrectionOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"description": "The same Idempotency-Key: the draft already made"},
        404: {"description": "Unknown conversation or message"},
        422: {"description": "not_an_agent_reply"},
    },
)
async def create_correction(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    body: CorrectionIn,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=80),
    scope: LiteScope = Depends(INBOX),
) -> CorrectionOut:
    """«Corregir esta respuesta» (52.1, 52.2): el borrador, sin aplicar nada."""
    conversation = await inbox_view.get_conversation(scope.session, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown conversation")
    try:
        row, created = await svc.draft(
            scope.session,
            conversation=conversation,
            message_id=message_id,
            text=body.text,
            scope=body.scope,
            author=_author(scope),
            idempotency_key=idempotency_key or None,
        )
    except LookupError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Unknown message"
        ) from None
    except svc.CorrectionError as exc:
        raise await _refused(scope, None, exc) from None
    if not created:
        response.status_code = status.HTTP_200_OK
    return await _out(scope, row)


@router.patch(
    "/corrections/{correction_id}",
    response_model=CorrectionOut,
    responses={
        409: {"description": "not_a_draft"},
        412: {"description": "revision_conflict"},
        428: {"description": "revision_required"},
    },
)
async def edit_correction(
    correction_id: uuid.UUID,
    body: CorrectionPatchIn,
    if_match: str | None = Header(default=None, alias="If-Match"),
    scope: LiteScope = Depends(INBOX),
) -> CorrectionOut:
    """Editar la lección o la paráfrasis antes de enviar (52.4)."""
    expected = required_revision(if_match)
    row = await _correction(scope, correction_id)
    try:
        await svc.edit(
            scope.session,
            row,
            expected_revision=expected,
            lesson=body.lesson,
            paraphrase=body.paraphrase,
            paraphrase_set="paraphrase" in body.model_fields_set,
        )
    except svc.CorrectionError as exc:
        raise await _refused(scope, row, exc) from None
    return await _out(scope, row)


@router.post(
    "/corrections/{correction_id}/send",
    response_model=CorrectionOut,
    responses={
        409: {"description": "not_a_draft"},
        412: {"description": "revision_conflict"},
        422: {"description": "pii_present · paraphrase_required · rule_too_long"},
        428: {"description": "revision_required"},
    },
)
async def send_correction(
    correction_id: uuid.UUID,
    if_match: str | None = Header(default=None, alias="If-Match"),
    scope: LiteScope = Depends(INBOX),
) -> CorrectionOut:
    """Un dato se aplica al momento; un comportamiento llega al partner (52.2)."""
    expected = required_revision(if_match)
    row = await _correction(scope, correction_id)
    try:
        async with scope.session.begin_nested():
            await svc.send(
                scope.session,
                row,
                expected_revision=expected,
                author=_author(scope),
                after_commit=scope.after_commit,
            )
    except svc.CorrectionError as exc:
        await scope.session.refresh(row)
        raise await _refused(scope, row, exc) from None
    return await _out(scope, row)


@router.post(
    "/corrections/{correction_id}/undo",
    response_model=CorrectionOut,
    responses={409: {"description": "not_applied · undo_not_available"}, 412: {}},
)
async def undo_correction(
    correction_id: uuid.UUID, scope: LiteScope = Depends(INBOX)
) -> CorrectionOut:
    """Deshacer un dato aplicado (13.3)."""
    from nexus_api.services.business.writes import SectionRevisionConflict

    row = await _correction(scope, correction_id)
    try:
        await svc.undo(scope.session, row, author=_author(scope))
    except svc.CorrectionError as exc:
        raise await _refused(scope, row, exc) from None
    except SectionRevisionConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail={"code": "revision_conflict", "changes": exc.changes},
        ) from None
    return await _out(scope, row)


__all__ = ["router"]
