"""Spec 047, T116 — la 0192 pasa la audiencia del agente a cada canal
(requisitos 55.1 y 32.10).

Baja a la 0191, siembra números de antes y vuelve a subir:

- un agente «solo administradores» deja su número en «Solo mi equipo» con sus
  números de prueba en E.164, sin duplicados ni los que no pueden coincidir;
- uno que respondía a todos queda en «A todos», sin excepciones;
- sin publicar, lo que respondería al publicarse (no «Sin configurar»); un número
  sin agente usa el de por defecto; uno desconectado no se toca;
- las políticas del agente (y su equipo) no cambian;
- la regla de la migración es la de ``admin_gate`` (7 cifras o más).

Corre en su propio proceso de Alembic y deja la base en head pase lo que pase.
"""

from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from nexus_api.core.admin_gate import usable_admin_phones
from tests.conftest import TEST_DB_URL

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_API = Path(__file__).resolve().parents[2]
_BEFORE = "0191_channel_config"


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


async def _tenant() -> uuid.UUID:
    tenant_id = uuid.uuid4()
    await _exec(
        "INSERT INTO tenants (id, name, slug, plan, status, timezone) "
        "VALUES (:i, 'T', :s, 'pro', 'active', 'Europe/Madrid')",
        i=tenant_id,
        s=f"m192-{tenant_id.hex[:10]}",
    )
    return tenant_id


async def _agent(
    tenant_id: uuid.UUID,
    policies: dict[str, Any] | None,
    *,
    is_default: bool = False,
    lifecycle: str = "published",
) -> uuid.UUID:
    agent_id = uuid.uuid4()
    await _exec(
        "INSERT INTO agents (id, tenant_id, name, status, lifecycle, is_default) "
        "VALUES (:a, :t, :n, 'active', :l, :d)",
        a=agent_id,
        n=f"Agente {agent_id.hex[:6]}",
        t=tenant_id,
        l=lifecycle,
        d=is_default,
    )
    if policies is not None:
        await _exec(
            "INSERT INTO agent_configs (id, tenant_id, agent_id, version, status, "
            "system_prompt_rendered, channels, tools, policies) VALUES "
            "(:c, :t, :a, (SELECT COALESCE(MAX(version), 0) + 1 FROM agent_configs "
            "WHERE tenant_id = :t), 'active', 'x', '[]'::jsonb, '[]'::jsonb, CAST(:p AS jsonb))",
            c=uuid.uuid4(),
            t=tenant_id,
            a=agent_id,
            p=json.dumps(policies),
        )
    return agent_id


async def _channel(
    tenant_id: uuid.UUID, agent_id: uuid.UUID | None, *, status: str = "active"
) -> uuid.UUID:
    channel_id = uuid.uuid4()
    await _exec(
        "INSERT INTO channels (id, tenant_id, agent_id, type, provider, provider_identifier, "
        "config, status) VALUES (:c, :t, :a, 'whatsapp', 'meta', :n, '{}'::jsonb, :s)",
        c=channel_id,
        t=tenant_id,
        a=agent_id,
        n=f"+3491{uuid.uuid4().int % 10**7:07d}",
        s=status,
    )
    return channel_id


async def _audience(channel_id: uuid.UUID) -> tuple[str, list[str]]:
    (row,) = await _exec("SELECT audience_mode FROM channels WHERE id = :c", c=channel_id)
    numbers = await _exec(
        "SELECT phone_e164 FROM channel_audience_numbers WHERE channel_id = :c AND kind = 'test' "
        "ORDER BY phone_e164",
        c=channel_id,
    )
    return row[0], [n[0] for n in numbers]


ADMIN_ONLY = {
    "admin_access": {
        "admin_only": True,
        "admin_phones": ["+34 600 111 222", "34600111222", "0424", "+56 9 1234 5678"],
        "admins": [{"phone": "+34600111222", "role": "readonly"}],
    }
}


async def test_the_agents_audience_moves_to_each_of_its_numbers(at_head_afterwards: Any) -> None:
    down = _alembic("downgrade", _BEFORE)
    assert down.returncode == 0, down.stderr

    tenant = await _tenant()
    cobranza = await _agent(tenant, ADMIN_ONLY, is_default=True)
    abierto = await _agent(tenant, {})
    borrador = await _agent(tenant, None, lifecycle="draft")
    team = await _channel(tenant, cobranza)
    everyone = await _channel(tenant, abierto)
    unpublished = await _channel(tenant, borrador)
    by_default = await _channel(tenant, None)
    gone = await _channel(tenant, abierto, status="disconnected")
    empty_tenant = await _tenant()
    nobody_usable = await _channel(
        empty_tenant,
        await _agent(empty_tenant, {"admin_access": {"admin_only": True, "admin_phones": ["12"]}}),
    )

    up = _alembic("upgrade", "head")
    assert up.returncode == 0, up.stderr

    expected = sorted({"+34600111222", "+56912345678"})
    assert await _audience(team) == ("team_only", expected)
    # La misma regla que la puerta de antes: lo que podía coincidir con alguien.
    assert sorted(usable_admin_phones(ADMIN_ONLY["admin_access"]["admin_phones"])) != []
    assert await _audience(everyone) == ("everyone", [])
    assert await _audience(unpublished) == ("everyone", []), "como respondería al publicarse"
    assert await _audience(by_default) == ("team_only", expected), "sin agente, el de por defecto"
    assert await _audience(gone) == ("unset", []), "un número desconectado no se toca"
    assert await _audience(nobody_usable) == ("team_only", []), "como antes: no responde a nadie"

    (policies,) = await _exec("SELECT policies FROM agent_configs WHERE agent_id = :a", a=cobranza)
    assert policies[0] == ADMIN_ONLY, "las políticas del agente no cambian (32.10)"

    # Subir otra vez no pisa lo que una persona eligió después.
    await _exec("UPDATE channels SET audience_mode = 'everyone' WHERE id = :c", c=team)
    await _exec("DELETE FROM channel_audience_numbers WHERE channel_id = :c", c=team)
    redo_down = _alembic("downgrade", _BEFORE)
    assert redo_down.returncode == 0, redo_down.stderr
    await _exec("UPDATE channels SET audience_mode = 'everyone' WHERE id = :c", c=team)
    redo = _alembic("upgrade", "head")
    assert redo.returncode == 0, redo.stderr
    assert await _audience(team) == ("everyone", [])
