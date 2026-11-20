"""Spec 065, T012 (requisitos 2.1 y 10.1): el bundle del agente trae su elección de modelo.

``bundle_of`` corre dentro de la sesión ya acotada al cliente; la elección de modelo se lee
ahí, por el id del agente y **sin un ``WHERE tenant_id`` propio**: la RLS forzada de
``agents`` es la que aísla, como con el resto del bundle. Un agente sin elección deja
``respond_model = None`` y el turno resuelve con el modelo por defecto de Auphere.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql

from nexus_worker.runtime import agent_loader

pytestmark = pytest.mark.asyncio


class _Result:
    def __init__(self, row: tuple[Any, ...] | None) -> None:
        self._row = row

    def one_or_none(self) -> tuple[Any, ...] | None:
        return self._row


class _Session:
    """Una sesión acotada de mentira que guarda lo que se le pide."""

    def __init__(self, choice: tuple[str, str] | None) -> None:
        self.choice = choice
        self.statements: list[str] = []

    async def scalar(self, stmt: Any) -> Any:
        return "Europe/Madrid"

    async def execute(self, stmt: Any) -> _Result:
        sql = str(stmt.compile(dialect=postgresql.dialect()))
        self.statements.append(sql)
        return _Result(self.choice)


def _cfg(agent_id: uuid.UUID) -> SimpleNamespace:
    return SimpleNamespace(
        agent_id=agent_id,
        version=3,
        id=uuid.uuid4(),
        system_prompt_rendered="Eres la recepción.",
        tools=["reservas.slots"],
        policies={},
        spec={},
        runtime_skills=[{"skill_id": "pdf"}],
        runtime_mcp_servers=[],
        runtime_memory_tool=False,
        runtime_outcome_grader=False,
        runtime_mcp_connector=False,
        grader_mode="sampled",
        grader_sample_rate=0.1,
    )


@pytest.fixture(autouse=True)
def _quiet_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_bindings(*a: Any, **k: Any) -> dict[str, Any]:
        return {}

    async def no_hours(*a: Any, **k: Any) -> dict[str, Any]:
        return {}

    async def no_targets(*a: Any, **k: Any) -> tuple[Any, ...]:
        return ()

    monkeypatch.setattr(agent_loader, "load_bindings", no_bindings)
    monkeypatch.setattr(agent_loader, "runtime_snapshot", no_hours)
    monkeypatch.setattr(agent_loader, "_reception_targets", no_targets)


async def test_the_bundle_carries_the_agents_choice_read_in_the_scoped_session() -> None:
    agent_id = uuid.uuid4()
    session = _Session(("openai/gpt-5.6-terra", "operator"))
    bundle = await agent_loader.bundle_of(session, uuid.uuid4(), _cfg(agent_id))

    assert bundle.respond_model == "openai/gpt-5.6-terra"
    assert bundle.respond_model_set_by == "operator"
    (sql,) = [s for s in session.statements if "respond_model_profile_id" in s]
    where = sql.split("WHERE", 1)[1]
    assert "agents.id" in where
    assert "tenant_id" not in where, "la RLS de la sesión acotada es la que aísla"


async def test_an_agent_without_a_choice_leaves_it_empty() -> None:
    session = _Session(None)
    bundle = await agent_loader.bundle_of(session, uuid.uuid4(), _cfg(uuid.uuid4()))
    assert bundle.respond_model is None
    assert bundle.respond_model_set_by is None


async def test_the_bundle_says_what_the_agent_needs_to_run() -> None:
    """Requisito 4.8: Skills de Anthropic y su conector MCP solo los ejecuta Claude."""
    session = _Session(None)
    bundle = await agent_loader.bundle_of(session, uuid.uuid4(), _cfg(uuid.uuid4()))
    assert bundle.agent_needs == frozenset({"anthropic_skills"})
