"""Spec 047, T061 — la migración 0186 pasa el horario a la ficha (requisitos 8.2 y 55.1).

Baja a la 0185, siembra las tres copias del horario de hoy y vuelve a subir.
Fija:

- los **cuatro formatos** de ``tenants.business_hours`` (el canónico de la 0170,
  el del asistente del admin, el de la semilla y el de la disponibilidad del
  agente) llegan a la ficha con sus turnos, «Migrado»;
- el horario de la consola (``policies.console.schedule``) llega si Reservas no
  tenía uno; si los dos tenían y no coinciden, gana Reservas y el de la consola
  queda como sugerencia;
- la frase del prompt sola (``label``) queda como sugerencia «Migrado ·
  revísalo», con la sección pendiente de revisar;
- ningún prompt ni ninguna versión cambia (research D4);
- un cliente que ya tiene el horario en la ficha no se toca, uno sin nada no
  recibe ficha, y repetirla no cambia nada.

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

from tests.conftest import TEST_DB_URL

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_API = Path(__file__).resolve().parents[2]
_BEFORE = "0185_bedrock_scaleway_drafts"


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


async def _tenant(hours: Any, *, market: str | None = "CL") -> uuid.UUID:
    tid = uuid.uuid4()
    await _exec(
        "INSERT INTO tenants (id, name, slug, plan, status, timezone, market, business_hours) "
        "VALUES (:i, 'H', :s, 'pro', 'active', 'America/Santiago', :m, CAST(:h AS jsonb))",
        i=tid,
        s=f"h-{tid.hex[:10]}",
        m=market,
        h=json.dumps(hours) if hours is not None else None,
    )
    return tid


async def _agent(tenant_id: uuid.UUID, *, prompt: str, policies: dict[str, Any]) -> None:
    agent_id = uuid.uuid4()
    await _exec(
        "INSERT INTO agents (id, tenant_id, name, status) VALUES (:a, :t, 'Principal', 'active')",
        a=agent_id,
        t=tenant_id,
    )
    await _exec(
        "INSERT INTO agent_configs (id, tenant_id, agent_id, version, status, "
        "system_prompt_rendered, channels, tools, policies, seed_template_ref) VALUES "
        "(:c, :t, :a, 1, 'active', :p, '[]'::jsonb, '[]'::jsonb, CAST(:pol AS jsonb), "
        "'barbershop_v1')",
        c=uuid.uuid4(),
        t=tenant_id,
        a=agent_id,
        p=prompt,
        pol=json.dumps(policies),
    )


async def _shifts(tenant_id: uuid.UUID) -> dict[int, list[tuple[int, int]]]:
    rows = await _exec(
        "SELECT sh.weekday, sh.open_min, sh.close_min FROM business_shifts sh "
        "JOIN business_schedules s ON s.id = sh.schedule_id "
        "WHERE s.tenant_id = :t AND s.location_id IS NULL ORDER BY sh.weekday, sh.open_min",
        t=tenant_id,
    )
    out: dict[int, list[tuple[int, int]]] = {}
    for weekday, a, b in rows:
        out.setdefault(int(weekday), []).append((int(a), int(b)))
    return out


async def _one(sql: str, **params: Any) -> Any:
    rows = await _exec(sql, **params)
    return rows[0] if rows else None


NINE_TO_SIX = (9 * 60, 18 * 60)
CANONICAL = {
    **{d: [{"from": "09:00", "to": "18:00"}] for d in ("monday", "tuesday", "wednesday")},
    "thursday": [{"from": "09:00", "to": "18:00"}],
    "friday": [{"from": "09:00", "to": "18:00"}],
    "saturday": [{"from": "10:00", "to": "14:00"}],
    "sunday": [],
}
ADMIN = {
    **{d: "09:00-18:00" for d in ("monday", "tuesday", "wednesday", "thursday", "friday")},
    "saturday": "10:00-14:00",
    "sunday": "closed",
}
SEED = {"monday": {"open": "09:00", "close": "18:00"}, "sunday": None}
AGENT = {
    "monday": {"start": "09:00", "end": "18:00"},
    "tuesday": {"start": "10:00", "end": "13:00"},
}
CONSOLE = {
    "console": {
        "schedule": {
            "timezone": "America/Santiago",
            "weekly": [
                {"day": "mon", "open": "11:00", "close": "15:00"},
                {"day": "mon", "open": "17:00", "close": "21:00"},
            ],
        }
    }
}


async def test_0186_moves_the_three_copies_into_the_ficha(at_head_afterwards: Any) -> None:
    down = _alembic("downgrade", _BEFORE)
    assert down.returncode == 0, down.stderr

    canonical = await _tenant({**CANONICAL, "label": "Lun-Vie 9-18"})
    admin = await _tenant(ADMIN)
    seed = await _tenant(SEED)
    agent = await _tenant(AGENT, market="ES")
    console_only = await _tenant(None)
    await _agent(console_only, prompt="Eres Sofía.", policies=CONSOLE)
    both = await _tenant(ADMIN)
    await _agent(both, prompt="Eres Leo. Horario: 11 a 21.", policies=CONSOLE)
    label_only = await _tenant({"label": "Lun-Sáb 10-19"})
    nothing = await _tenant(None)

    up = _alembic("upgrade", "head")
    assert up.returncode == 0, up.stderr

    # Los cuatro formatos de ``tenants.business_hours``.
    for tid in (canonical, admin):
        days = await _shifts(tid)
        assert [days.get(i) for i in range(5)] == [[NINE_TO_SIX]] * 5
        assert days.get(5) == [(600, 840)] and 6 not in days
        layout = await _one(
            "SELECT layout FROM business_schedules WHERE tenant_id = :t AND location_id IS NULL",
            t=tid,
        )
        assert layout == ("blocks",)
    assert await _shifts(seed) == {0: [NINE_TO_SIX]}
    assert await _shifts(agent) == {0: [NINE_TO_SIX], 1: [(600, 780)]}
    assert await _one(
        "SELECT layout FROM business_schedules WHERE tenant_id = :t AND location_id IS NULL",
        t=agent,
    ) == ("daily",)
    for tid in (canonical, admin, seed, agent):
        prov = await _one(
            "SELECT source, review FROM business_field_provenance "
            "WHERE tenant_id = :t AND pointer = '/hours'",
            t=tid,
        )
        assert prov == ("migrated", "confirmed")
        state = await _one(
            "SELECT state, revision FROM business_sections WHERE tenant_id = :t AND section = 'hours'",
            t=tid,
        )
        assert state == ("complete", 1)
        change = await _one(
            "SELECT kind FROM business_changes WHERE tenant_id = :t AND section = 'hours'",
            t=tid,
        )
        assert change == ("migration",)

    # La ficha de un cliente de antes nace con lo que se sabe de él.
    assert await _one(
        "SELECT niche, timezone, country, price_currency, eu_only FROM business_profiles "
        "WHERE tenant_id = :t",
        t=agent,
    ) == ("Negocio", "America/Santiago", "ES", "EUR", True)
    assert await _one(
        "SELECT niche FROM business_profiles WHERE tenant_id = :t", t=console_only
    ) == ("Barbería",)
    sections = await _exec(
        "SELECT count(*) FROM business_sections WHERE tenant_id = :t", t=console_only
    )
    assert sections == [(9,)]

    # El horario de la consola, cuando Reservas no tenía.
    assert await _shifts(console_only) == {0: [(660, 900), (1020, 1260)]}
    # Los dos, distintos: gana Reservas y el de la consola queda al lado.
    assert (await _shifts(both))[0] == [NINE_TO_SIX]
    (suggestion,) = await _exec(
        "SELECT proposed_value, source FROM business_suggestions "
        "WHERE tenant_id = :t AND pointer = '/hours'",
        t=both,
    )
    assert suggestion[1] == "migrated"
    assert suggestion[0]["days"]["mon"] == [
        {"open": "11:00", "close": "15:00"},
        {"open": "17:00", "close": "21:00"},
    ]

    # Solo la frase del prompt: «Migrado · revísalo», sin inventar turnos.
    assert await _shifts(label_only) == {}
    (label,) = await _exec(
        "SELECT proposed_value FROM business_suggestions WHERE tenant_id = :t", t=label_only
    )
    assert label[0] == {"label": "Lun-Sáb 10-19"}
    assert await _one(
        "SELECT review FROM business_field_provenance WHERE tenant_id = :t AND pointer = '/hours'",
        t=label_only,
    ) == ("pending",)
    assert await _one(
        "SELECT state FROM business_sections WHERE tenant_id = :t AND section = 'hours'",
        t=label_only,
    ) == ("read_pending",)

    # Sin nada que mover, nada nace.
    assert await _exec("SELECT 1 FROM business_profiles WHERE tenant_id = :t", t=nothing) == []

    # Ningún prompt ni ninguna versión cambió (D4), ni la proyección.
    prompt = await _one(
        "SELECT system_prompt_rendered, policies FROM agent_configs WHERE tenant_id = :t", t=both
    )
    assert prompt[0] == "Eres Leo. Horario: 11 a 21."
    assert prompt[1] == CONSOLE
    assert (
        await _exec(
            "SELECT 1 FROM agent_version_compilations WHERE tenant_id IN (:a, :b)",
            a=both,
            b=console_only,
        )
        == []
    )
    assert (await _one("SELECT business_hours FROM tenants WHERE id = :t", t=canonical))[0] == {
        **CANONICAL,
        "label": "Lun-Vie 9-18",
    }

    # Idempotente, y lo que ya estaba en la ficha no se toca.
    shifts_before = await _shifts(admin)
    assert _alembic("downgrade", _BEFORE).returncode == 0
    assert await _shifts(admin) == {}, "the downgrade takes back what it moved"
    assert _alembic("upgrade", "head").returncode == 0
    assert await _shifts(admin) == shifts_before
    await _exec(
        "UPDATE business_field_provenance SET source = 'person' "
        "WHERE tenant_id = :t AND pointer = '/hours'",
        t=seed,
    )
    assert _alembic("downgrade", _BEFORE).returncode == 0
    assert _alembic("upgrade", "head").returncode == 0
    assert await _shifts(seed) == {0: [NINE_TO_SIX]}
    rows = await _exec(
        "SELECT count(*) FROM business_schedules WHERE tenant_id = :t AND location_id IS NULL",
        t=seed,
    )
    assert rows == [(1,)]
