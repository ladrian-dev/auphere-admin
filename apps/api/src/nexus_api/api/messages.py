"""``/v1/messages`` — direct outbound sends for tenant-scoped API keys.

The surface a client automates against: one POST per WhatsApp message,
authenticated by a key that already knows which tenant (and therefore
which WhatsApp number) it belongs to. No client identifier in the body,
because there is no choice to make — see ``require_tenant_key``.

Distinct from ``/v1/embed/broadcasts``, which is many recipients behind
a short-lived session JWT minted for an iframe. Same underlying queue.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.partner_auth import TenantKeyContext, require_tenant_key
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import ApiKeyScope, Message
from nexus_api.schemas.messages import (
    MessageStatusOut,
    TemplateMessageAcceptedOut,
    TemplateMessageIn,
)
from nexus_api.services.direct_messages import mask_phone, send_template_message

router = APIRouter(prefix="/messages", tags=["messages"])
log = structlog.get_logger(__name__)


@router.post(
    "/template",
    response_model=TemplateMessageAcceptedOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue one WhatsApp template message",
)
async def post_template_message(
    payload: TemplateMessageIn,
    ctx: TenantKeyContext = Depends(require_tenant_key(ApiKeyScope.MESSAGES_SEND.value)),
    session: AsyncSession = Depends(get_db_session),
) -> TemplateMessageAcceptedOut:
    """202 means queued and durable, not delivered.

    Delivery is asynchronous by design: the outbound dispatcher owns
    retries, backoff and Meta reauth. Poll ``GET /v1/messages/{id}`` for
    the delivery state.
    """
    # Who called, on which key. A campaign that half-sends is almost
    # always one automation looping, and the key prefix is what ties a
    # burst of these lines back to a single n8n run.
    log.info(
        "api.messages.template.request",
        tenant_id=str(ctx.tenant_id),
        partner_id=str(ctx.partner.id),
        api_key_prefix=ctx.api_key.prefix_snippet,
        template=payload.template_name,
        to_masked=mask_phone(payload.to),
        idempotency_key=payload.idempotency_key,
    )
    async with tenant_scoped_session(session, ctx.tenant_id):
        result = await send_template_message(session, tenant_id=ctx.tenant_id, payload=payload)
    log.info(
        "api.messages.template.response",
        tenant_id=str(ctx.tenant_id),
        message_id=str(result.message_id),
        status=result.status,
        duplicate=result.duplicate,
        template=payload.template_name,
        idempotency_key=payload.idempotency_key,
    )
    return result


@router.get(
    "/{message_id}",
    response_model=MessageStatusOut,
    summary="Delivery state of a previously queued message",
)
async def get_message_status(
    message_id: uuid.UUID,
    ctx: TenantKeyContext = Depends(require_tenant_key(ApiKeyScope.MESSAGES_SEND.value)),
    session: AsyncSession = Depends(get_db_session),
) -> MessageStatusOut:
    """404 for both "no such message" and "not yours" — RLS filters the
    row out before this code runs, and distinguishing the two would leak
    the existence of another tenant's message ids."""
    async with tenant_scoped_session(session, ctx.tenant_id):
        message = await session.scalar(sa.select(Message).where(Message.id == message_id))
        if message is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="message not found",
            )
        return MessageStatusOut.model_validate(message)
