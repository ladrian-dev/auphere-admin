"""Spec 065, T034 (requisito 12.4): el modelo por cliente se retira; un solo sitio, el agente.

- ``PUT /console/clients/{ref}/model`` responde ``410 client_model_retired`` y el ``GET`` ya no
  existe: el modelo se elige por agente (``…/agents/{id}/model``).
- ``PUT`` y ``DELETE /admin/tenants/{id}/model-bindings/respond`` responden
  ``422 respond_is_per_agent``; los demás roles (``classify``) siguen igual.
- Encoger la lista de un partner ya no toca el rol ``respond`` de sus clientes: los agentes
  se reconcilian por su cuenta (T083).
"""

from __future__ import annotations

import pytest

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

SOL = "openai/gpt-5.6-sol"
LUNA = "openai/gpt-5.6-luna"


async def test_the_console_cannot_set_a_clients_model_any_more(client, console_world) -> None:
    a = console_world["a"]
    put = await client.put(
        f"/console/clients/{a['ref']}/model", headers=a["headers"](), json={"model_id": SOL}
    )
    assert put.status_code == 410, put.text
    assert put.json()["detail"] == {"code": "client_model_retired"}
    get = await client.get(f"/console/clients/{a['ref']}/model", headers=a["headers"]())
    assert get.status_code in {404, 405}, get.text


async def test_the_panel_cannot_bind_respond_but_still_classify(
    client, console_world, admin_headers
) -> None:
    a = console_world["a"]
    url = f"/admin/tenants/{a['tenant_id']}/model-bindings"
    respond = await client.put(f"{url}/respond", headers=admin_headers, json={"model_id": LUNA})
    assert respond.status_code == 422, respond.text
    assert respond.json()["detail"] == {"code": "respond_is_per_agent"}
    gone = await client.delete(f"{url}/respond", headers=admin_headers)
    assert gone.status_code == 422, gone.text
    classify = await client.put(
        f"{url}/classify", headers=admin_headers, json={"model_id": "anthropic/claude-haiku-4-5"}
    )
    assert classify.status_code == 200, classify.text


async def test_shrinking_a_partners_list_leaves_the_respond_binding_alone(
    client, console_world, admin_headers
) -> None:
    import sqlalchemy as sa

    a = console_world["a"]
    async with get_sessionmaker()() as session, tenant_scoped_session(session, a["tenant_id"]):
        await session.execute(
            sa.text(
                "INSERT INTO tenant_model_bindings (tenant_id, role, model_profile_id, "
                "fallback_chain) SELECT :t, 'respond', id, '[]'::jsonb FROM model_profiles "
                "WHERE model_id = :m"
            ),
            {"t": a["tenant_id"], "m": LUNA},
        )
        await session.commit()
    put = await client.put(
        f"/admin/partners/{a['partner_id']}/models",
        headers=admin_headers,
        json={"model_ids": [SOL]},
    )
    assert put.status_code == 200, put.text
    async with get_sessionmaker()() as session, tenant_scoped_session(session, a["tenant_id"]):
        left = await session.scalar(
            sa.text("SELECT count(*) FROM tenant_model_bindings WHERE role = 'respond'")
        )
    assert left == 1, "la fila de antes se queda hasta la migración siguiente"
