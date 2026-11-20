"""Spec 065, T035 (requisito 12.5): un agente que la 0240 dejó con un modelo heredado.

Un modelo sin perfil de respuesta (Claude Sonnet 4.6) que un agente recibió de la asignación
de su cliente sigue respondiendo (la resolución lo acepta: no pide nada que no pueda), y la
consola lo enseña tal cual: con su precio, «ya no se ofrece» (``outside_offer: retired``) y
fuera de ``options``. El partner no puede volver a elegirlo, solo cambiarlo a uno de su oferta.
La petición al proveedor, byte a byte como hoy, la fija el test en el cable
(``test_respond_profiles_on_the_wire.py``).
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from tests.integration.models.test_agent_model_console import (  # noqa: F401
    _catalog,
    agent_of,
    choice_of,
    url,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

SONNET46 = "anthropic/claude-sonnet-4-6"
LUNA = "openai/gpt-5.6-luna"


async def _migrated(tenant_id: uuid.UUID, agent_id: uuid.UUID, model_id: str) -> None:
    """Lo que deja la 0240 para un cliente al que Auphere puso el modelo desde el panel."""
    async with get_sessionmaker()() as session, tenant_scoped_session(session, tenant_id):
        await session.execute(
            sa.text(
                "UPDATE agents SET respond_model_profile_id = "
                "(SELECT id FROM model_profiles WHERE model_id = :m), "
                "respond_model_set_by = 'operator', respond_model_set_at = now() WHERE id = :a"
            ),
            {"m": model_id, "a": agent_id},
        )
        await session.commit()


async def test_a_legacy_model_keeps_answering_and_reads_as_no_longer_offered(
    client, console_world
) -> None:
    a = console_world["a"]
    agent = await agent_of(a["tenant_id"])
    await _migrated(a["tenant_id"], agent, SONNET46)

    resp = await client.get(url(a["ref"], agent), headers=a["headers"]())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["choice"]["model_id"] == SONNET46
    assert body["choice"]["set_by"] == "operator"
    effective = body["effective"]
    assert (effective["model_id"], effective["source"]) == (SONNET46, "agent_operator")
    assert effective["outside_offer"] == "retired"
    assert effective["estimate"] is not None, "se enseña con su precio"
    assert effective["estimate"]["amount_micros"] > 0
    assert SONNET46 not in {o["model_id"] for o in body["options"]}
    assert body["notice"] is None


async def test_the_partner_can_only_move_it_to_a_model_on_offer(client, console_world) -> None:
    a = console_world["a"]
    agent = await agent_of(a["tenant_id"])
    await _migrated(a["tenant_id"], agent, SONNET46)

    again = await client.put(
        url(a["ref"], agent), headers=a["headers"](), json={"model_id": SONNET46}
    )
    assert again.status_code == 422, again.text
    assert again.json()["detail"]["code"] == "unknown_model"
    assert (await choice_of(a["tenant_id"], agent))[:2] == (SONNET46, "operator")

    moved = await client.put(url(a["ref"], agent), headers=a["headers"](), json={"model_id": LUNA})
    assert moved.status_code == 200, moved.text
    assert moved.json()["effective"]["outside_offer"] is None
    assert (await choice_of(a["tenant_id"], agent))[:2] == (LUNA, "partner")
