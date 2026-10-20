"""«Necesita tu atención» y los números de WhatsApp (producción, 2026-10-20).

El Panel avisaba «Número de WhatsApp desconectado» de Flor y Encanto
mientras Canales mostraba su único número activo: la consulta contaba la
fila ``disconnected`` de un número que el partner ya había desvinculado.
Esa fila es historial (Canales la esconde); solo un número ``degraded`` es
un problema del que avisar.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Channel, ChannelStatus, ChannelType
from nexus_api.services.console_home import tenant_snapshots

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _channel(tenant_id: uuid.UUID, *, identifier: str, status: ChannelStatus) -> None:
    async with get_sessionmaker()() as s, tenant_scoped_session(s, tenant_id):
        s.add(
            Channel(
                tenant_id=tenant_id,
                type=ChannelType.WHATSAPP,
                provider="meta",
                provider_identifier=identifier,
                config={"display_phone_number": identifier},
                status=status,
            )
        )


def _month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def test_a_number_the_partner_unlinked_is_not_an_incident(console_world) -> None:
    tid = console_world["a"]["tenant_id"]
    await _channel(tid, identifier="+56991919125", status=ChannelStatus.ACTIVE)
    await _channel(tid, identifier="+56911111111", status=ChannelStatus.DISCONNECTED)

    now = datetime.now(UTC)
    snap = (await tenant_snapshots([tid], month_start=_month_start(now), now=now)).snapshots[tid]

    assert snap.whatsapp_bad == 0
    assert snap.active_channels == 1
    assert "whatsapp_degraded" not in snap.issues


async def test_a_degraded_number_still_needs_attention(console_world) -> None:
    tid = console_world["a"]["tenant_id"]
    await _channel(tid, identifier="+56991919125", status=ChannelStatus.ACTIVE)
    await _channel(tid, identifier="+56922222222", status=ChannelStatus.DEGRADED)

    now = datetime.now(UTC)
    snap = (await tenant_snapshots([tid], month_start=_month_start(now), now=now)).snapshots[tid]

    assert snap.whatsapp_bad == 1
    assert "whatsapp_degraded" in snap.issues
