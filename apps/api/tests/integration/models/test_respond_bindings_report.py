"""Spec 065, T031 (requisito 12.3): la comprobación previa de la 0240, solo lectura.

Antes de desplegar se lee qué clientes tienen asignación ``respond``, con qué modelo, cuántos
agentes la recibirían y qué deja de usarse (``fallback_chain`` y tope). Los totales tienen que
ser los que la 0240 deja escritos en su ``RAISE NOTICE``: asignaciones encontradas y agentes
activos sin elección propia.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from tests.conftest import TEST_DB_URL

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "respond_bindings_report.py"
TERRA = "openai/gpt-5.6-terra"
LUNA = "openai/gpt-5.6-luna"


def _module() -> Any:
    spec = importlib.util.spec_from_file_location("respond_bindings_report", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Las dataclasses buscan su módulo en sys.modules al crearse.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


async def _exec(sql: str, **params: Any) -> None:
    engine = create_async_engine(TEST_DB_URL)
    try:
        async with engine.begin() as conn:
            await conn.execute(sa.text("SET LOCAL row_security = off"))
            await conn.execute(sa.text(sql), params)
    finally:
        await engine.dispose()


async def _seed() -> tuple[uuid.UUID, uuid.UUID]:
    jemma, plain = uuid.uuid4(), uuid.uuid4()
    for t in (jemma, plain):
        await _exec(
            "INSERT INTO tenants (id, name, slug, plan, status, timezone) "
            "VALUES (:i, 'T', :s, 'pro', 'active', 'Europe/Madrid')",
            i=t,
            s=f"r031-{t.hex[:10]}",
        )
    for n, status in enumerate(("active", "active", "archived")):
        await _exec(
            "INSERT INTO agents (id, tenant_id, name, status) VALUES (:i, :t, :n, :s)",
            i=uuid.uuid4(),
            t=jemma,
            n=f"A{n}",
            s=status,
        )
    await _exec(
        "INSERT INTO agents (id, tenant_id, name, status, respond_model_profile_id, "
        "respond_model_set_by, respond_model_set_at) SELECT :i, :t, 'B', 'active', id, "
        "'partner', now() FROM model_profiles WHERE model_id = :m",
        i=uuid.uuid4(),
        t=jemma,
        m=LUNA,
    )
    await _exec(
        "INSERT INTO tenant_model_bindings (tenant_id, role, model_profile_id, fallback_chain, "
        "max_cost_per_turn_usd) SELECT :t, 'respond', id, CAST(:c AS jsonb), 0.50 "
        "FROM model_profiles WHERE model_id = :m",
        t=jemma,
        m=TERRA,
        c=json.dumps([LUNA]),
    )
    await _exec(
        "INSERT INTO tenant_model_bindings (tenant_id, role, model_profile_id, fallback_chain) "
        "SELECT :t, 'classify', id, '[]'::jsonb FROM model_profiles WHERE model_id = :m",
        t=plain,
        m=LUNA,
    )
    return jemma, plain


async def test_the_report_counts_what_0240_will_write() -> None:
    jemma, plain = await _seed()
    report = await _module().read_report(TEST_DB_URL)

    mine = [r for r in report.rows if r.tenant_id == jemma]
    assert len(mine) == 1
    (row,) = mine
    assert row.model_id == TERRA
    assert row.agents_to_write == 2, "activos sin elección propia"
    assert row.agents_with_choice == 1
    assert row.agents_not_active == 1
    assert row.fallback_chain == [LUNA]
    assert row.max_cost_per_turn_usd is not None
    assert row.drops == ["fallback_chain", "max_cost_per_turn_usd"]
    assert not [r for r in report.rows if r.tenant_id == plain], "solo el rol respond"
    assert report.bindings_found == len(report.rows)
    assert report.agents_to_write == sum(r.agents_to_write for r in report.rows)


async def test_the_report_does_not_write() -> None:
    await _seed()
    text = _module().render(await _module().read_report(TEST_DB_URL))
    assert "asignaciones de respuesta" in text and "agentes escritos" in text
    with pytest.raises(sa.exc.DBAPIError, match="read-only"):
        await _module().read_report(TEST_DB_URL, probe_write=True)
