"""Clientes de solo envío en el panel — spec 077, requisitos 1, 2 y 10.

- ``PATCH /admin/tenants/{id}/send-only``: marca o desmarca un cliente. Al
  marcarlo, sus números de WhatsApp quedan sin agente y, si no tenían papel,
  como línea de avisos (la puerta del entrante ya los trata así por la marca).
- ``GET /admin/tenants/{id}/send-readiness``: la puesta en marcha calculada en
  el servidor, cada paso con su estado real (constitución §V).
- ``GET /admin/tenants/{id}/template-messages``: los últimos envíos de
  plantillas, con el destinatario enmascarado y nunca un código.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict

from nexus_api.api.admin.operator import operator_actor, require_enabled_operator
from nexus_api.core.security import require_admin_token
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AuditLog,
    Channel,
    ChannelStatus,
    ChannelType,
    Conversation,
    Customer,
    Message,
    MessageDirection,
    OperatorAccount,
    PartnerApiKey,
    Tenant,
)
from nexus_api.schemas.tenant import TenantOut
from nexus_api.services.direct_messages import mask_phone
from nexus_api.services.membership_gate import is_active, live_membership

router = APIRouter(prefix="/tenants", dependencies=[Depends(require_admin_token)])
log = structlog.get_logger(__name__)


class SendOnlyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    send_only: bool


class StepChannel(BaseModel):
    ok: bool
    active_numbers: int


class StepTemplate(BaseModel):
    ok: bool
    approved: int
    pending: int
    #: Meta did not answer: the panel says «no se pudo comprobar».
    unknown: bool


class StepMembership(BaseModel):
    ok: bool
    status: str


class StepKeys(BaseModel):
    ok: bool
    active: int


class SendReadinessOut(BaseModel):
    channel: StepChannel
    template: StepTemplate
    #: ``None`` when the client has no membership: the step does not exist.
    membership: StepMembership | None
    keys: StepKeys


class TemplateMessageRowOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    to_masked: str
    template: str | None
    status: str
    failure_code: str | None


@router.patch("/{tenant_id}/send-only", response_model=TenantOut)
async def set_send_only(
    tenant_id: uuid.UUID,
    body: SendOnlyIn,
    operator: OperatorAccount = Depends(require_enabled_operator),
) -> TenantOut:
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tenant_not_found")
        before = bool(tenant.send_only)
        tenant.send_only = body.send_only
        changed_numbers: list[str] = []
        if body.send_only and not before:
            channels = (
                await session.scalars(
                    sa.select(Channel).where(
                        Channel.tenant_id == tenant_id, Channel.type == ChannelType.WHATSAPP
                    )
                )
            ).all()
            for channel in channels:
                config = dict(channel.config or {})
                config["agent_enabled"] = False
                config.setdefault("role", "notifications")
                # A new dict: JSONB is not tracked in place.
                channel.config = config
                changed_numbers.append(str(channel.id))
        if before != body.send_only:
            session.add(
                AuditLog(
                    tenant_id=tenant_id,
                    actor=operator_actor(operator),
                    action="tenant.send_only_changed",
                    target=f"tenant:{tenant_id}",
                    before_json={"send_only": before},
                    after_json={"send_only": body.send_only, "numbers": changed_numbers},
                )
            )
        await session.flush()
        await session.refresh(tenant)
        log.info("tenant.send_only", tenant_id=str(tenant_id), send_only=body.send_only)
        return TenantOut.model_validate(tenant)


@router.get("/{tenant_id}/send-readiness", response_model=SendReadinessOut)
async def send_readiness(tenant_id: uuid.UUID) -> SendReadinessOut:
    """Each step from what is stored, except the template, which Meta owns:
    approved AUTHENTICATION templates, or «unknown» when Meta does not answer
    instead of a guess (constitution §V)."""
    from nexus_api.services.whatsapp_templates import fetch_templates

    now = datetime.now(UTC)
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        if await session.get(Tenant, tenant_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tenant_not_found")
        active_numbers = int(
            await session.scalar(
                sa.select(sa.func.count())
                .select_from(Channel)
                .where(
                    Channel.type == ChannelType.WHATSAPP,
                    Channel.status == ChannelStatus.ACTIVE,
                )
            )
            or 0
        )
        membership = await live_membership(session)
        membership_step = (
            None
            if membership is None
            else StepMembership(ok=is_active(membership, now=now), status=membership.status)
        )
        template_step = StepTemplate(ok=False, approved=0, pending=0, unknown=False)
        if active_numbers:
            try:
                templates, _waba = await fetch_templates(session)
            except Exception:
                template_step = StepTemplate(ok=False, approved=0, pending=0, unknown=True)
            else:
                auth = [t for t in templates if (t.category or "").upper() == "AUTHENTICATION"]
                approved = sum(1 for t in auth if (t.status or "").upper() == "APPROVED")
                pending = sum(1 for t in auth if (t.status or "").upper() == "PENDING")
                template_step = StepTemplate(
                    ok=approved > 0, approved=approved, pending=pending, unknown=False
                )
    async with get_sessionmaker()() as session, session.begin():
        keys = (
            await session.scalars(
                sa.select(PartnerApiKey).where(PartnerApiKey.tenant_id == tenant_id)
            )
        ).all()
        active_keys = sum(
            1
            for k in keys
            if (k.expires_at is None or k.expires_at > now)
            and (
                k.revoked_at is None
                or (k.grace_expires_at is not None and k.grace_expires_at > now)
            )
        )
    return SendReadinessOut(
        channel=StepChannel(ok=active_numbers > 0, active_numbers=active_numbers),
        template=template_step,
        membership=membership_step,
        keys=StepKeys(ok=active_keys > 0, active=active_keys),
    )


@router.get("/{tenant_id}/template-messages", response_model=list[TemplateMessageRowOut])
async def template_messages(
    tenant_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[TemplateMessageRowOut]:
    """The client's latest template sends. The recipient is masked and the
    payload is never returned: a code must not reach the panel either."""
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        rows = (
            await session.execute(
                sa.select(
                    Message.id,
                    Message.created_at,
                    Message.status,
                    Message.failure_code,
                    Message.template_payload["name"].astext,
                    Customer.identifier,
                    Customer.phone,
                )
                .join(Conversation, Conversation.id == Message.conversation_id)
                .join(Customer, Customer.id == Conversation.customer_id)
                .where(
                    Message.direction == MessageDirection.OUTBOUND,
                    Message.template_payload.is_not(None),
                )
                .order_by(Message.created_at.desc())
                .limit(limit)
            )
        ).all()
    return [
        TemplateMessageRowOut(
            id=row[0],
            created_at=row[1],
            to_masked=mask_phone("+" + str(row[6] or row[5] or "").lstrip("+")),
            template=row[4],
            status=row[2].value if hasattr(row[2], "value") else str(row[2]),
            failure_code=row[3],
        )
        for row in rows
    ]
