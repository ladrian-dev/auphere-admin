"""Spec 050 (3.2): rotate a WhatsApp number's two-step verification PIN.

Meta never returns the PIN, and a later ``/register`` of the number has to
send the same one, so Auphere keeps it encrypted inside the channel's
:class:`MetaCredentials`. The operator rotates it from the channel's page;
the new PIN is never in a response or a log, only the fact that it changed
(``channel.whatsapp.pin_rotated``).
"""

from __future__ import annotations

import uuid
from dataclasses import replace

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from nexus_channels.whatsapp_meta import MetaAPIError, MetaClient
from nexus_channels.whatsapp_meta.credentials import (
    ChannelCredentialsRepository,
    MetaCredentialsRepository,
)
from nexus_channels.whatsapp_meta.signup import generate_two_step_pin
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import scoped_session_from_path
from nexus_api.config import get_settings
from nexus_api.core.security import require_admin_token
from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import AuditLog, Channel, ChannelType

router = APIRouter()
log = structlog.get_logger()


class PinRotatedOut(BaseModel):
    status: str
    channel_id: uuid.UUID


def build_pin_meta_client() -> MetaClient:
    """FastAPI dependency, so tests swap in a mocked client."""
    settings = get_settings()
    return MetaClient(
        app_secret=settings.meta_app_secret,
        require_appsecret_proof=settings.meta_require_appsecret_proof,
        version=settings.meta_graph_api_version,
    )


@router.post(
    "/tenants/{tenant_id}/channels/{channel_id}/two-step-pin",
    response_model=PinRotatedOut,
)
async def rotate_two_step_pin(
    channel_id: uuid.UUID,
    session: AsyncSession = Depends(scoped_session_from_path),
    client: MetaClient = Depends(build_pin_meta_client),
    actor: str = Depends(require_admin_token),
) -> PinRotatedOut:
    tenant_id = require_current_tenant()
    try:
        channel = await session.get(Channel, channel_id)
        if channel is None or channel.type != ChannelType.WHATSAPP or channel.provider != "meta":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="channel_not_found")
        config = channel.config or {}
        if config.get("mode") == "coexistence":
            # The number lives in the WhatsApp Business app: its PIN is the app's.
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="coexistence_number")

        channels = ChannelCredentialsRepository(session)
        tenant_creds = MetaCredentialsRepository(session)
        creds = await channels.get(channel_id)
        tenant_row = await tenant_creds.get()
        if (
            creds is None
            and tenant_row is not None
            and tenant_row.phone_number_id == config.get("phone_number_id")
        ):
            creds = tenant_row
        if creds is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="no_credentials")

        pin = generate_two_step_pin()
        try:
            await client.set_two_step_pin(
                phone_number_id=creds.phone_number_id, access_token=creds.bisuat, pin=pin
            )
        except MetaAPIError as exc:
            log.warning(
                "whatsapp.pin_rotation_refused",
                channel_id=str(channel_id),
                status=exc.status_code,
                code=exc.code,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail="meta_refused_the_pin"
            ) from exc
    finally:
        await client.close()

    await channels.upsert(channel_id, replace(creds, two_step_pin=pin))
    if tenant_row is not None and tenant_row.phone_number_id == creds.phone_number_id:
        await tenant_creds.upsert(replace(tenant_row, two_step_pin=pin))
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor=f"admin:{actor[:8]}",
            action="channel.whatsapp.pin_rotated",
            target=f"channel:{channel_id}",
            before_json=None,
            after_json={"channel_id": str(channel_id), "phone_number_id": creds.phone_number_id},
        )
    )
    await session.flush()
    log.info("whatsapp.pin_rotated", tenant_id=str(tenant_id), channel_id=str(channel_id))
    return PinRotatedOut(status="rotated", channel_id=channel_id)
