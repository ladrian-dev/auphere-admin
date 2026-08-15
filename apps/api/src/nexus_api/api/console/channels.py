"""``/console/clients/{ref}/channels`` — channel metadata for a client.

Read-only in this package: type, provider, identifier (the WhatsApp
number the partner already knows), status, role and last health check.
Never ``config`` (may hold provider ids that are effectively
credentials) and never ``config_encrypted``. Connecting a channel is
CP-17 (Embedded Signup) and lives in its own package.
"""

from __future__ import annotations

import sqlalchemy as sa
from fastapi import APIRouter, Depends

from nexus_api.db.models import Channel
from nexus_api.services.channel_routing import channel_role

from .deps import ClientScope, client_scope
from .schemas import ChannelOut

router = APIRouter(prefix="/clients/{ref}/channels")


@router.get("", response_model=list[ChannelOut])
async def list_channels(
    scope: ClientScope = Depends(client_scope("channels:read")),
) -> list[ChannelOut]:
    rows = (
        (await scope.session.execute(sa.select(Channel).order_by(Channel.created_at)))
        .scalars()
        .all()
    )
    return [
        ChannelOut(
            id=ch.id,
            type=ch.type.value,
            provider=ch.provider,
            provider_identifier=ch.provider_identifier,
            status=ch.status.value,
            role=channel_role(ch),
            last_health_check_at=ch.last_health_check_at,
            created_at=ch.created_at,
        )
        for ch in rows
    ]
