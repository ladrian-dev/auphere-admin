"""Spec 047, T095 — la 0189 da a cada versión de antes su AgentSpec sin cambiar
lo que responde (requisitos 16.4 y 55.1; CE-009).

Baja a la 0188, siembra agentes de antes (con y sin bloque de la ficha, con equipo,
con aviso de IA decidido y sin él) y vuelve a subir. Por agente:

- el AgentSpec es el de ``services/agent_spec/legacy.spec_from_version`` (la
  migración lleva una copia congelada de la regla);
- **compila los mismos bytes**: sin ficha, sus instrucciones; con la ficha, el
  prompt entero de hoy;
- ``system_prompt_rendered`` no cambia, y una versión archivada no se toca.

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

from nexus_api.services.agent_spec.compiler import compile_spec
from nexus_api.services.agent_spec.legacy import spec_from_version
from nexus_api.services.agent_spec.schema import AgentSpec, dump
from nexus_api.services.business.compilation import Facts, compile_prompt
from tests.conftest import TEST_DB_URL

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_API = Path(__file__).resolve().parents[2]
_BEFORE = "0188_sector_tests_v1"


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


FACTS = Facts(name="Cultor", hours="De lunes a viernes de 10:00 a 20:00.")
TODAY = "Eres el asistente de Cultor.\n\nResponde siempre de tú."
WITH_FICHA = compile_prompt(TODAY, FACTS)


async def _seed(
    name: str, prompt: str, tools: list[str], policies: dict[str, Any], status: str = "active"
) -> uuid.UUID:
    tenant_id, agent_id, cfg_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await _exec(
        "INSERT INTO tenants (id, name, slug, plan, status, timezone) "
        "VALUES (:i, 'T', :s, 'pro', 'active', 'Europe/Madrid')",
        i=tenant_id,
        s=f"m189-{tenant_id.hex[:10]}",
    )
    await _exec(
        "INSERT INTO agents (id, tenant_id, name, status) VALUES (:a, :t, :n, 'active')",
        a=agent_id,
        t=tenant_id,
        n=name,
    )
    await _exec(
        "INSERT INTO agent_configs (id, tenant_id, agent_id, version, status, "
        "system_prompt_rendered, channels, tools, policies) VALUES "
        "(:c, :t, :a, 1, :st, :p, '[]'::jsonb, CAST(:tools AS jsonb), CAST(:pol AS jsonb))",
        c=cfg_id,
        t=tenant_id,
        a=agent_id,
        st=status,
        p=prompt,
        tools=json.dumps(tools),
        pol=json.dumps(policies),
    )
    return cfg_id


async def _row(cfg_id: uuid.UUID) -> tuple[Any, str]:
    (row,) = await _exec(
        "SELECT spec, system_prompt_rendered FROM agent_configs WHERE id = :c", c=cfg_id
    )
    return row[0], row[1]


async def test_every_version_of_before_gets_its_spec_and_compiles_the_same_bytes(
    at_head_afterwards: Any,
) -> None:
    down = _alembic("downgrade", _BEFORE)
    assert down.returncode == 0, down.stderr
    decided = {
        "console": {"ai_disclosure": {"enabled": True, "disclosure_message": "Soy un asistente."}}
    }
    team = {
        "admin_access": {
            "admin_only": True,
            "admin_phones": ["+34600111222"],
            "admins": [{"phone": "+34600111222", "name": "Marta"}],
        }
    }
    plain = await _seed("Asistente", TODAY, ["reservas.create", "Old Tool"], {})
    ficha = await _seed("Recepción", WITH_FICHA, [], decided)
    staff = await _seed("Equipo", TODAY, ["billing.find_client"], team)
    archived = await _seed("Viejo", TODAY, [], {}, status="archived")

    up = _alembic("upgrade", "head")
    assert up.returncode == 0, up.stderr

    for cfg_id, name, prompt, tools, policies in (
        (plain, "Asistente", TODAY, ["reservas.create", "Old Tool"], {}),
        (ficha, "Recepción", WITH_FICHA, [], decided),
        (staff, "Equipo", TODAY, ["billing.find_client"], team),
    ):
        spec_doc, stored_prompt = await _row(cfg_id)
        assert stored_prompt == prompt, "la migración no toca el prompt"
        expected = spec_from_version(
            agent_name=name, system_prompt_rendered=prompt, tools=tools, policies=policies
        )
        assert spec_doc == dump(expected)
        spec = AgentSpec.model_validate(spec_doc)
        # Los mismos bytes: el prompt de hoy, con la ficha si la llevaba.
        assert compile_spec(spec, FACTS if prompt == WITH_FICHA else None) == prompt

    ficha_spec = AgentSpec.model_validate((await _row(ficha))[0])
    assert (
        ficha_spec.ai_disclosure.decided is True
        and ficha_spec.ai_disclosure.text == "Soy un asistente."
    )
    staff_spec = AgentSpec.model_validate((await _row(staff))[0])
    assert [m.label for m in staff_spec.team_access or []] == ["Marta"]
    assert (await _row(archived))[0] is None

    # Y se deshace: bajarla quita los AgentSpec que puso.
    again = _alembic("downgrade", "0188_sector_tests_v1")
    assert again.returncode == 0, again.stderr
    assert (await _row(plain))[0] is None
