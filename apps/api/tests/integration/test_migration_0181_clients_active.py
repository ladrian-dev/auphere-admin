"""Spec 047, T046 — la migración de datos 0181: los clientes en ``provisioning`` pasan a ``active``.

Requisito 4.7: el ciclo de vida del cliente (activo, en pausa o archivado) se
separa de su preparación. Un cliente sin agentes está activo y no queda en un
«preparando» que dependa de tener agente y canal.

**Su paso no puede hacer contestar a nadie que hoy no contesta.** El
dispatcher calla a un cliente en ``provisioning`` (``_INACTIVE_STATUSES``) y,
a uno ``active``, lo hace responder si tiene una versión publicada y un número.
Por eso solo pasa a ``active`` quien **no tiene ninguna versión publicada**: ese
no puede responder ni hoy ni después de la migración, tenga o no número. Quien sí
la tiene se queda como está: es el «esperando activación» de la API de partners
(``activation_blocked_reason``, ``docs/partner-integration.md``), que se activa
por su camino de hoy.

Baja a 0180, siembra los casos, sube y comprueba; repetirla no cambia nada, y
bajar devuelve a ``provisioning`` justo a los que pasó. Corre en su propio
proceso de Alembic y deja la base en head pase lo que pase.
"""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from tests.conftest import TEST_DB_URL

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_API = Path(__file__).resolve().parents[2]
_BEFORE = "0180_model_catalog_and_router"
_THIS = "0181_clients_active"
_ACTOR = "system:0181_clients_active"


def _alembic(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "alembic", *args], cwd=_API, capture_output=True, text=True, check=False
    )


@pytest.fixture
def at_head_afterwards() -> Any:
    yield
    _alembic("upgrade", "head")


async def _exec(sql: str, **params: Any) -> list[Any]:
    engine = create_async_engine(TEST_DB_URL)
    try:
        async with engine.begin() as conn:
            result = await conn.execute(sa.text(sql), params)
            return list(result.all()) if result.returns_rows else []
    finally:
        await engine.dispose()


async def _tenant(status: str) -> uuid.UUID:
    tid = uuid.uuid4()
    await _exec(
        "INSERT INTO tenants (id, name, slug, plan, status) "
        "VALUES (:i, 'T', :s, 'pro', CAST(:st AS tenant_status))",
        i=tid,
        s=f"m181-{tid.hex[:10]}",
        st=status,
    )
    return tid


async def _agent(tenant: uuid.UUID, *, version_status: str | None) -> None:
    aid = uuid.uuid4()
    await _exec(
        "INSERT INTO agents (id, tenant_id, name, status) VALUES (:a, :t, 'Recepción', 'active')",
        a=aid,
        t=tenant,
    )
    if version_status is not None:
        await _exec(
            "INSERT INTO agent_configs (tenant_id, agent_id, version, status, "
            "system_prompt_rendered) VALUES (:t, :a, 1, CAST(:s AS agent_config_status), 'Eres X.')",
            t=tenant,
            a=aid,
            s=version_status,
        )


async def _channel(tenant: uuid.UUID, status: str = "active") -> None:
    await _exec(
        "INSERT INTO channels (tenant_id, type, provider, provider_identifier, status) "
        "VALUES (:t, 'whatsapp', 'meta', :i, CAST(:s AS channel_status))",
        t=tenant,
        i=f"wa-{uuid.uuid4().hex[:10]}",
        s=status,
    )


async def _status(tenant: uuid.UUID) -> str:
    (row,) = await _exec("SELECT status::text FROM tenants WHERE id = :t", t=tenant)
    return str(row[0])


async def _marks(tenant: uuid.UUID) -> list[Any]:
    return await _exec(
        "SELECT action, before_json, after_json FROM audit_log WHERE tenant_id = :t AND actor = :a",
        t=tenant,
        a=_ACTOR,
    )


async def test_only_who_cannot_answer_becomes_active(at_head_afterwards: Any) -> None:
    down = _alembic("downgrade", _BEFORE)
    assert down.returncode == 0, down.stderr

    # Pasan: no tienen ninguna versión publicada, así que no responden ni antes ni después.
    no_agent = await _tenant("provisioning")
    draft_only = await _tenant("provisioning")
    await _agent(draft_only, version_status="staged")
    await _channel(draft_only)  # con número, pero el agente está en borrador
    empty_agent = await _tenant("provisioning")
    await _agent(empty_agent, version_status=None)

    # Se quedan: con versión publicada, pasar a ``active`` los haría responder.
    serving_if_moved = await _tenant("provisioning")
    await _agent(serving_if_moved, version_status="active")
    await _channel(serving_if_moved)
    awaiting_number = await _tenant("provisioning")
    await _agent(awaiting_number, version_status="active")

    # Los demás estados no se tocan.
    paused = await _tenant("paused")
    archived = await _tenant("archived")
    active = await _tenant("active")

    up = _alembic("upgrade", _THIS)
    assert up.returncode == 0, up.stderr

    for moved in (no_agent, draft_only, empty_agent):
        assert await _status(moved) == "active"
        (mark,) = await _marks(moved)
        assert mark[0] == "console.client.status"
        assert mark[1] == {"status": "provisioning"}
        assert mark[2] == {"status": "active"}
    for kept in (serving_if_moved, awaiting_number):
        assert await _status(kept) == "provisioning"
        assert await _marks(kept) == []
    assert await _status(paused) == "paused"
    assert await _status(archived) == "archived"
    assert await _status(active) == "active"
    for untouched in (paused, archived, active):
        assert await _marks(untouched) == []

    again_down = _alembic("downgrade", _BEFORE)
    assert again_down.returncode == 0, again_down.stderr
    # Bajar devuelve a ``provisioning`` justo a los que pasó, y borra sus marcas.
    for moved in (no_agent, draft_only, empty_agent):
        assert await _status(moved) == "provisioning"
        assert await _marks(moved) == []
    assert await _status(active) == "active"
    assert await _status(paused) == "paused"
    for kept in (serving_if_moved, awaiting_number):
        assert await _status(kept) == "provisioning"

    up_again = _alembic("upgrade", _THIS)
    assert up_again.returncode == 0, up_again.stderr
    for moved in (no_agent, draft_only, empty_agent):
        assert await _status(moved) == "active"
        assert len(await _marks(moved)) == 1


async def test_a_client_activated_by_hand_is_not_sent_back_on_downgrade(
    at_head_afterwards: Any,
) -> None:
    """Si alguien lo pausó o lo archivó después, bajar no lo pisa."""
    down = _alembic("downgrade", _BEFORE)
    assert down.returncode == 0, down.stderr
    later_paused = await _tenant("provisioning")
    up = _alembic("upgrade", _THIS)
    assert up.returncode == 0, up.stderr
    assert await _status(later_paused) == "active"
    await _exec("UPDATE tenants SET status = 'paused' WHERE id = :t", t=later_paused)

    back = _alembic("downgrade", _BEFORE)
    assert back.returncode == 0, back.stderr
    assert await _status(later_paused) == "paused"
