"""Admin F3 — conocimiento y packs del partner del path (solo lectura).

El ``partner_id`` del path es la fuente de verdad. Se fija el GUC
``app.partner_id`` igual que F1/F2. El ref de cliente se resuelve en
``partner_tenants``. Sin PUT/DELETE/apply. Sin ``content_text``.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin.partners import _get_partner_or_404
from nexus_api.api.console.deps import ClientRef, unknown_client
from nexus_api.api.console.knowledge import PROMPT_CHAR_CAP
from nexus_api.api.console.schemas_agent_tools import KnowledgeDocumentOut, KnowledgeListOut
from nexus_api.api.console.schemas_workflow import WorkflowPackOut, WorkflowRunOut, WorkflowRunsOut
from nexus_api.api.console.workflow import _out as _workflow_out
from nexus_api.api.deps import get_db_session
from nexus_api.core.partner_context import apply_partner_to_session
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import KnowledgeDocumentStatus, PartnerKnowledgeDocument, PartnerTenant
from nexus_api.db.models.workflow import WorkflowPack, WorkflowRun
from nexus_api.repositories.partner import PartnerTenantRepository

router = APIRouter(prefix="/partners", dependencies=[Depends(require_admin_token)])


def _knowledge_item(row: PartnerKnowledgeDocument) -> KnowledgeDocumentOut:
    """Metadata only. Copy declared Out fields so ``content_text`` cannot leak."""
    payload = {
        name: getattr(row, name)
        for name in KnowledgeDocumentOut.model_fields
        if name != "content_text"
    }
    return KnowledgeDocumentOut.model_validate(payload)


async def _mapping_or_404(session: AsyncSession, partner_id: uuid.UUID, ref: str) -> PartnerTenant:
    mapping = await PartnerTenantRepository(session).get_mapping(partner_id, ref)
    if mapping is None:
        raise unknown_client()
    return mapping


@router.get(
    "/{partner_id}/knowledge",
    response_model=KnowledgeListOut,
    responses={404: {"description": "Partner not found."}},
)
async def get_partner_knowledge(
    partner_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> KnowledgeListOut:
    """Playbook del partner del path. Misma Out que ``GET /console/knowledge``."""
    async with session.begin():
        await _get_partner_or_404(session, partner_id)
        await apply_partner_to_session(session, partner_id)
        rows = (
            await session.scalars(
                sa.select(PartnerKnowledgeDocument).order_by(
                    PartnerKnowledgeDocument.created_at.desc()
                )
            )
        ).all()
        indexed_chars = await session.scalar(
            sa.select(
                sa.func.coalesce(
                    sa.func.sum(sa.func.length(PartnerKnowledgeDocument.content_text)), 0
                )
            ).where(PartnerKnowledgeDocument.status == KnowledgeDocumentStatus.INDEXED.value)
        )
        out = KnowledgeListOut(
            items=[_knowledge_item(row) for row in rows],
            total=len(rows),
            indexed_chars=int(indexed_chars or 0),
            prompt_char_cap=PROMPT_CHAR_CAP,
        )
    return out


@router.get(
    "/{partner_id}/clients/{ref}/workflow",
    response_model=WorkflowPackOut,
    responses={404: {"description": "Partner or client reference not found."}},
)
async def get_partner_client_workflow(
    partner_id: uuid.UUID,
    ref: str = ClientRef,
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowPackOut:
    """Pack v1 del cliente del path. Misma Out que el GET de consola."""
    async with session.begin():
        await _get_partner_or_404(session, partner_id)
        await apply_partner_to_session(session, partner_id)
        mapping = await _mapping_or_404(session, partner_id, ref)
        pack = (
            await session.scalars(
                sa.select(WorkflowPack).where(
                    WorkflowPack.partner_id == partner_id,
                    WorkflowPack.client_ref == mapping.external_client_ref,
                )
            )
        ).first()
        out = _workflow_out(ref, pack)
    return out


@router.get(
    "/{partner_id}/clients/{ref}/workflow/runs",
    response_model=WorkflowRunsOut,
    responses={404: {"description": "Partner or client reference not found."}},
)
async def get_partner_client_workflow_runs(
    partner_id: uuid.UUID,
    ref: str = ClientRef,
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowRunsOut:
    """Runs del pack del cliente del path. Misma Out que el GET de consola."""
    async with session.begin():
        await _get_partner_or_404(session, partner_id)
        await apply_partner_to_session(session, partner_id)
        mapping = await _mapping_or_404(session, partner_id, ref)
        pack = (
            await session.scalars(
                sa.select(WorkflowPack).where(
                    WorkflowPack.partner_id == partner_id,
                    WorkflowPack.client_ref == mapping.external_client_ref,
                )
            )
        ).first()
        if pack is None:
            out = WorkflowRunsOut(items=[])
        else:
            rows = (
                await session.scalars(
                    sa.select(WorkflowRun)
                    .where(WorkflowRun.pack_id == pack.id)
                    .order_by(WorkflowRun.created_at.desc())
                    .limit(100)
                )
            ).all()
            out = WorkflowRunsOut(
                items=[WorkflowRunOut(thread_id=r.thread_id, status=r.status) for r in rows]
            )
    return out
