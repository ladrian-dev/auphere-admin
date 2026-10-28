"""La 0204 da la consola nueva a todos los partners (Andrés, 2026-10-29).

Ya no hay activación partner a partner. Para cada partner que seguía en la
consola de antes, la migración hace lo que hacía activarla:

- a sus números que todavía no tienen audiencia en el canal les escribe la de
  antes, con la regla de la 0192 («Solo mi equipo» con sus números de prueba, o
  «A todos»), para que nadie empiece a responder a quien no debía;
- enciende la consola nueva, dice quién y deja una fila de auditoría.

A un partner que ya estaba en la consola nueva no le toca nada: un número suyo
«Sin configurar» lo eligió una persona (32.9). Corre en su propio proceso de
Alembic y deja la base en head pase lo que pase.
"""

from __future__ import annotations

import json
import subprocess
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from tests.conftest import _TRUNCATE_TABLES, TEST_DB_URL

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_API = Path(__file__).resolve().parents[2]
_BEFORE = "0203_audit_vocab_connectors"


def _alembic(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "alembic", *args], cwd=_API, capture_output=True, text=True, check=False
    )


@pytest_asyncio.fixture
async def at_head_afterwards() -> AsyncIterator[None]:
    yield
    _alembic("upgrade", "head")
    # Sin ``db_session`` nadie vacía la base al acabar, y los partners de aquí se
    # quedarían para el siguiente test que los cuenta (la semilla de la fábrica).
    await _exec("TRUNCATE TABLE " + ", ".join(_TRUNCATE_TABLES) + " RESTART IDENTITY CASCADE")


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
        s=f"m204-{tenant_id.hex[:10]}",
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
    "admin_access": {"admin_only": True, "admin_phones": ["+34 600 111 222", "+56 9 1234 5678"]}
}


async def _partner(*, v2: bool) -> uuid.UUID:
    pid = uuid.uuid4()
    await _exec(
        "INSERT INTO partners (id, name, slug, status, console_v2_enabled_at, console_v2_enabled_by) "
        "VALUES (:i, 'P', :s, 'active', CASE WHEN :v THEN now() END, CASE WHEN :v THEN 'operator:ana' END)",
        i=pid,
        s=f"m204-{pid.hex[:10]}",
        v=v2,
    )
    return pid


async def _client_of(partner_id: uuid.UUID) -> uuid.UUID:
    tenant_id = await _tenant()
    await _exec(
        "INSERT INTO partner_tenants (partner_id, external_client_ref, tenant_id) VALUES (:p, :r, :t)",
        p=partner_id,
        r=f"c-{tenant_id.hex[:8]}",
        t=tenant_id,
    )
    return tenant_id


async def test_every_partner_gets_the_new_console_with_its_audiences(
    at_head_afterwards: Any,
) -> None:
    down = _alembic("downgrade", _BEFORE)
    assert down.returncode == 0, down.stderr

    old = await _partner(v2=False)
    old_client = await _client_of(old)
    team = await _channel(old_client, await _agent(old_client, ADMIN_ONLY, is_default=True))
    everyone = await _channel(old_client, await _agent(old_client, {}))

    new = await _partner(v2=True)
    new_client = await _client_of(new)
    chosen_unset = await _channel(new_client, await _agent(new_client, ADMIN_ONLY, is_default=True))
    (before_new,) = await _exec("SELECT console_v2_enabled_at FROM partners WHERE id = :p", p=new)

    up = _alembic("upgrade", "head")
    assert up.returncode == 0, up.stderr

    # La audiencia de antes pasa a cada número, como al activar.
    assert await _audience(team) == ("team_only", ["+34600111222", "+56912345678"])
    assert await _audience(everyone) == ("everyone", [])
    # Un partner que ya estaba en la consola nueva no se toca.
    assert await _audience(chosen_unset) == ("unset", [])
    (after_new,) = await _exec("SELECT console_v2_enabled_at FROM partners WHERE id = :p", p=new)
    assert after_new == before_new

    (row,) = await _exec(
        "SELECT console_v2_enabled_at, console_v2_enabled_by FROM partners WHERE id = :p", p=old
    )
    assert row[0] is not None
    assert row[1] == "auphere:consola-nueva-para-todos"
    audit = await _exec(
        "SELECT actor, before_json, after_json FROM audit_log WHERE action = 'partner.console_v2_enabled' AND target = :t",
        t=f"partner:{old}",
    )
    assert len(audit) == 1
    assert audit[0][1] == {"console_version": "v1"} and audit[0][2]["console_version"] == "v2"
    assert not await _exec(
        "SELECT 1 FROM audit_log WHERE action = 'partner.console_v2_enabled' AND target = :t",
        t=f"partner:{new}",
    )
    (nulls,) = await _exec("SELECT count(*) FROM partners WHERE console_v2_enabled_at IS NULL")
    assert nulls[0] == 0
