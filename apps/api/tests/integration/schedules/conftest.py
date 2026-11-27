"""Lo compartido por las pruebas de rutinas — spec 082.

Un cliente con su agente publicado, y un segundo cliente al lado para que cada
prueba de ámbito tenga a dónde intentar colarse. La fixture vive aquí y no en
un fichero de pruebas porque importarla de otro la dejaba redefinida en cada
sitio que la usa.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession


async def make_agent(
    db_session: AsyncSession, tenant_id: uuid.UUID, *, name: str = "Soporte"
) -> str:
    agent_id = uuid.uuid4()
    await db_session.execute(
        sa.text(
            "INSERT INTO agents (id, tenant_id, name, lifecycle) VALUES (:a, :t, :n, 'published')"
        ),
        {"a": str(agent_id), "t": str(tenant_id), "n": name},
    )
    await db_session.commit()
    return str(agent_id)


def body(agent_id: str, **over: Any) -> dict[str, Any]:
    return {
        "agent_id": agent_id,
        "name": "Altas de ayer en Notion",
        "instruction": "Revisa la vista «Usuarios» y dime quién se dio de alta ayer.",
        "cadence": "daily",
        "local_time": "09:00",
        "email": False,
        **over,
    }


def url(world: dict[str, Any], tail: str = "") -> str:
    return f"/console/clients/{world['ref']}/schedules{tail}"


@pytest.fixture
async def world(db_session: AsyncSession, console_world: dict[str, Any]) -> dict[str, Any]:
    a = console_world["a"]
    return {
        "ref": a["ref"],
        "tenant_id": a["tenant_id"],
        "partner_id": a["partner_id"],
        "headers": a["headers"],
        "agent_id": await make_agent(db_session, a["tenant_id"]),
        "other_ref": console_world["b"]["ref"],
    }
