"""El Resumen del cliente lee el medidor; nunca lo alimenta (spec 018).

Puerta del medidor del plan: esta spec **no mide nada nuevo**. El bloque de
consumo del Resumen enseña unidades que el medidor de la spec 004 ya
registró, y por eso hay que poder afirmar que componer la pantalla no
escribe ni una fila.

No es una preocupación teórica: la pantalla se pinta en cada visita a la
ficha, y un `UsageRecord` por visita facturaría al partner por mirar.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from nexus_api.db.models import AgentConfig, AgentConfigStatus, UsageRecord

pytestmark = pytest.mark.asyncio


async def _seed(db_session, tenant_id: uuid.UUID) -> None:
    db_session.add(
        AgentConfig(
            tenant_id=tenant_id,
            version=1,
            status=AgentConfigStatus.ACTIVE,
            system_prompt_rendered="Atiende a los clientes.",
            channels=[],
            tools=[],
            policies={},
        )
    )
    await db_session.commit()


async def test_composing_the_summary_writes_no_usage_record(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    await _seed(db_session, a["tenant_id"])

    async def filas() -> int:
        return int(
            await db_session.scalar(sa.select(sa.func.count()).select_from(UsageRecord)) or 0
        )

    antes = await filas()

    # Las cuatro lecturas que la pantalla compone, tal cual las pide.
    for path in (
        f"/console/clients/{a['ref']}",
        f"/console/usage?client={a['ref']}&days=30",
        f"/console/clients/{a['ref']}/conversations/stats",
        f"/console/clients/{a['ref']}/channels",
        f"/console/clients/{a['ref']}/connectors",
    ):
        r = await client.get(path, headers=a["headers"]())
        assert r.status_code == 200, f"{path} → {r.status_code} {r.text}"

    assert await filas() == antes, "mirar la ficha no puede costar una unidad"
