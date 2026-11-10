"""Los valores por defecto del modelo (spec 047, T145 · requisitos 39.1, 39.2 y
39.11; research D24 y D44).

- **Dónde vive** la política de modelo hasta el AgentSpec (bloque D):
  ``agent_configs.policies["model_policy"]``, con la forma del AgentSpec
  (``{"kind": "profile", "profile": "auto"}`` o ``{"kind": "pinned",
  "deployment": …}``). Va con la versión: borrador, puerta, deshacer y restaurar.
- **Un agente nuevo nace en «Automático»** cuando «Automático» puede atenderlo
  —cada tarea del turno tiene un despliegue que pasa el filtro duro del cliente,
  o su reserva lo pasa—. Mientras no (hoy: ninguna fila tiene la retención cero
  comprobada, D44), nace por el camino de hoy, como los agentes de hoy: que la
  consola no ofrezca algo que no puede servir.
- **Los agentes de hoy quedan fijados**: una versión nueva de un agente que ya
  tenía versiones no recibe ``model_policy``.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import AgentConfig
from nexus_api.services.agent_config_service import AgentConfigService

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_PLACES = {"tenant.address": "Calle Mayor 1", "tenant.business_hours_label": "L-V 9-18"}
#: Las reservas de «Automático» en la 0182: Luna clasifica, Haiku responde.
RESERVES = ("openai/gpt-5.6-luna", "anthropic/claude-haiku-4-5")
AUTO = {"kind": "profile", "profile": "auto"}


def _u(a: dict[str, Any], path: str) -> str:
    return f"/console/clients/{a['ref']}{path}"


async def _reserves_serve(serve: bool) -> None:
    """Las reservas de «Automático» pasan (o no) el filtro duro: como si su
    retención cero estuviera comprobada. Solo en la base de pruebas."""
    caps = (
        'capabilities || \'{"strict_structured_outputs": true, "structured_outputs": true}\''
        if serve
        else "capabilities - 'strict_structured_outputs' - 'structured_outputs'"
    )
    async with get_sessionmaker()() as session, session.begin():
        await session.execute(
            sa.text(
                "UPDATE model_profiles SET zero_retention = :z, "
                "retention_how = CASE WHEN :z THEN 'store=false' END, "
                f"capabilities = {caps} WHERE model_id = ANY(:m)"
            ),
            {"z": serve, "m": list(RESERVES)},
        )


@pytest_asyncio.fixture
async def auto_serves() -> AsyncIterator[None]:
    await _reserves_serve(True)
    try:
        yield
    finally:
        await _reserves_serve(False)


async def _create_agent(client, a: dict[str, Any], name: str) -> uuid.UUID:
    r = await client.post(
        _u(a, "/agents"),
        headers=a["headers"](),
        json={"name": name, "seed_template": "generic_v1", "placeholders": _PLACES},
    )
    assert r.status_code == 201, r.text
    return uuid.UUID(r.json()["id"])


async def _policies(tenant_id: uuid.UUID, agent_id: uuid.UUID) -> list[dict[str, Any]]:
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        rows = await session.scalars(
            sa.select(AgentConfig.policies)
            .where(AgentConfig.agent_id == agent_id)
            .order_by(AgentConfig.version)
        )
        return [dict(p or {}) for p in rows.all()]


async def test_a_new_agent_is_born_on_todays_path_while_nothing_serves_auto(
    client, console_world
) -> None:
    a = console_world["a"]
    agent = await _create_agent(client, a, "Ventas")
    [policies] = await _policies(a["tenant_id"], agent)
    assert "model_policy" not in policies, "con el catálogo de hoy «Automático» no atiende (D44)"


async def test_a_new_agent_is_born_in_auto_once_auto_can_serve_it(
    client, console_world, auto_serves
) -> None:
    a = console_world["a"]
    agent = await _create_agent(client, a, "Reservas")
    [policies] = await _policies(a["tenant_id"], agent)
    assert policies["model_policy"] == AUTO


async def test_an_agent_of_today_stays_fixed_on_its_model(client, console_world) -> None:
    """Un agente que ya tenía versión no pasa a «Automático» por sacar otra,
    aunque «Automático» ya atienda: el cambio lo hace una persona (39.11)."""
    a = console_world["a"]
    agent = await _create_agent(client, a, "De hoy")
    [version] = await _versions(client, a, agent)
    publish = await client.post(
        _u(a, f"/agent/versions/{version}/publish?agent={agent}"), headers=a["headers"]()
    )
    assert publish.status_code == 200, publish.text

    await _reserves_serve(True)
    try:
        async with (
            get_sessionmaker()() as session,
            tenant_scoped_session(session, a["tenant_id"]),
        ):
            await AgentConfigService(session).stage_new_version(
                actor="test",
                system_prompt_rendered="Otro prompt",
                channels=[],
                tools=[],
                policies={},
                agent_id=agent,
            )
    finally:
        await _reserves_serve(False)
    assert [("model_policy" in p) for p in await _policies(a["tenant_id"], agent)] == [
        False,
        False,
    ]


async def _versions(client, a: dict[str, Any], agent: uuid.UUID) -> list[int]:
    r = await client.get(_u(a, f"/agent?agent={agent}"), headers=a["headers"]())
    assert r.status_code == 200, r.text
    return [int(v["version"]) for v in r.json()["versions"]]


async def test_a_client_only_in_the_eu_is_born_in_auto_only_if_auto_serves_the_eu(
    client, console_world, auto_serves
) -> None:
    """Las reservas de hoy son de residencia global: para un cliente «Solo UE»
    «Automático» no atiende, y su agente nace por el camino de hoy."""
    a = console_world["a"]
    async with get_sessionmaker()() as session, tenant_scoped_session(session, a["tenant_id"]):
        await session.execute(
            sa.text(
                "INSERT INTO business_profiles (tenant_id, niche, timezone, eu_only) "
                "VALUES (:t, 'Barbería', 'Europe/Madrid', true)"
            ),
            {"t": a["tenant_id"]},
        )
    agent = await _create_agent(client, a, "Solo UE")
    [policies] = await _policies(a["tenant_id"], agent)
    assert "model_policy" not in policies
