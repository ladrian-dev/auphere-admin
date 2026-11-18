"""Spec 063, requisito 4.5 — garantía 5: un borrador no lleva el nombre de otro cliente.

La 063 dejó de contar como ajeno lo que el propio cliente da al constructor. Esta
prueba fija lo que no cambia:

- si el constructor escribe por su cuenta el nombre de otro cliente del partner,
  ese trozo no llega ni al AgentSpec guardado ni a lo que devuelve la API;
- la exención vale para el borrador de quien lo escribió, no para los demás: que
  un cliente nombre a otro en su descripción no exime a un tercero.
"""

from __future__ import annotations

import copy
import uuid
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.builder._builder_world import RECEPTION, FakeBuilder, run_jobs, start_draft
from tests.integration.business._business_world import Biz, new_business

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

OTHER = "Ferretería Olmo"


def _reply() -> dict[str, Any]:
    reply = copy.deepcopy(RECEPTION)
    reply["instructions"] = [
        {"title": "Cómo atiendes", "body": "Pregunta el servicio y el día."},
        {"title": "Proveedor", "body": f"El material lo trae {OTHER}."},
    ]
    return reply


async def _draft(
    client: Any, biz: Biz, fake_redis: Any, *, description: str
) -> tuple[uuid.UUID, str]:
    resp = await start_draft(
        client, f"/console/clients/{biz.ref}", biz.headers(), description=description
    )
    assert resp.status_code == 202, resp.text
    await run_jobs(fake_redis, FakeBuilder(reply=_reply()))
    job = await client.get(f"/console/jobs/{resp.json()['job_id']}", headers=biz.headers())
    assert job.json()["status"] == "done", job.text
    agent_id = uuid.UUID(job.json()["result"]["agent_id"])
    draft = await client.get(
        f"/console/clients/{biz.ref}/agents/{agent_id}/draft", headers=biz.headers()
    )
    assert draft.status_code == 200, draft.text
    return agent_id, job.text + draft.text


async def test_the_builder_never_carries_another_clients_name(
    client: Any, db_session: AsyncSession, console_world: dict[str, Any], fake_redis: Any
) -> None:
    await new_business(client, db_session, console_world, name=OTHER)
    third = await new_business(client, db_session, console_world, name="Bazar Luna")
    rita = await new_business(client, db_session, console_world, name="Salón Rita")

    # Un tercero que sí nombra a «Ferretería Olmo» en lo que escribe: para él no es ajeno.
    _, said = await _draft(
        client,
        third,
        fake_redis,
        description=f"Atiende el WhatsApp del bazar. Vendemos material de {OTHER}.",
    )
    assert OTHER in said

    # Salón Rita no lo nombra: lo que el constructor escriba con ese nombre no llega.
    _, said = await _draft(
        client,
        rita,
        fake_redis,
        description="Atiende las citas del salón por WhatsApp y responde precios.",
    )
    assert OTHER not in said
    assert "Pregunta el servicio y el día." in said
