"""Fallo ``canal-simulado-primera-pasada``: el canal simulado nace una sola vez.

Un cliente nuevo no tiene canal del playground hasta su primera conversación
simulada, y una pasada de pruebas las abre en paralelo. Comprobar si existe y
luego crearlo dejaba que la segunda chocara con ``uq_channels_live_number``, y el
trabajo de pruebas terminaba en ``failed`` la primera vez de cada cliente.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.jobs.handlers.agent_tests import PARALLEL
from nexus_worker.simulation.runner import open_conversation
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import Channel
from nexus_api.db.models.channel import QA_PLAYGROUND_PROVIDER

from ..business._business_world import new_business

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_first_conversations_at_once_share_one_channel(
    client: Any, db_session: AsyncSession, console_world: dict[str, Any]
) -> None:
    biz = await new_business(client, db_session, console_world, name="Barbería Cultor")

    conversations = await asyncio.gather(
        *(open_conversation(biz.tenant_id) for _ in range(PARALLEL))
    )

    assert len({conv.channel_id for conv in conversations}) == 1
    assert len({conv.conversation_id for conv in conversations}) == PARALLEL
    async with get_sessionmaker()() as session, tenant_scoped_session(session, biz.tenant_id):
        channels = await session.scalar(
            sa.select(sa.func.count())
            .select_from(Channel)
            .where(
                Channel.tenant_id == biz.tenant_id,
                Channel.provider == QA_PLAYGROUND_PROVIDER,
            )
        )
    assert channels == 1
