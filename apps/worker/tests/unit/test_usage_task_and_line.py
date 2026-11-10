"""Spec 047, T023 — el medidor sabe la tarea, la decisión y la partida.

Requisitos 40.1, 40.9 y 46.4.

- Cada llamada a un modelo lleva su **tarea** de la taxonomía v1
  (``contracts/router-and-catalog.md`` §1) y, si la hubo, la **decisión** del
  router que la eligió. Una llamada sin tarea **falla en los tests**
  (``NEXUS_USAGE_REQUIRE_TASK=1``) y en producción se mide igual y se registra
  como anomalía: perder la medición sería regalar el gasto.
- La **partida** (``line``) se deriva de ``source`` al escribir:
  conversaciones, construcción y pruebas, o Companion.
"""

from __future__ import annotations

import importlib.util
import json
import uuid
from pathlib import Path

import pytest
from structlog.testing import capture_logs

from nexus_worker.metering import collector, consumer

pytestmark = pytest.mark.asyncio


class _FakeRedis:
    def __init__(self) -> None:
        self.entries: list[tuple[str, dict]] = []

    async def xadd(self, stream, fields, **kwargs):
        self.entries.append((stream, dict(fields)))
        return b"1-1"


@pytest.fixture
def fake_redis(monkeypatch):
    redis = _FakeRedis()
    monkeypatch.setattr("nexus_api.core.redis_client.get_redis", lambda: redis)
    return redis


def _events(redis: _FakeRedis) -> list[dict]:
    return [e for _s, f in redis.entries for e in json.loads(f["events"])]


USAGE = {"prompt_tokens": 120, "completion_tokens": 30}


async def test_a_call_without_a_task_fails_in_the_tests(monkeypatch, fake_redis) -> None:
    monkeypatch.setenv("NEXUS_USAGE_REQUIRE_TASK", "1")
    async with collector.usage_turn(tenant_id=uuid.uuid4(), turn_id="t1"):
        with pytest.raises(collector.UsageTaskMissing):
            collector.record_llm_usage(
                model="anthropic/claude-haiku-5-5", provider=None, usage=USAGE
            )


async def test_an_unknown_task_fails_in_the_tests(monkeypatch, fake_redis) -> None:
    monkeypatch.setenv("NEXUS_USAGE_REQUIRE_TASK", "1")
    async with collector.usage_turn(tenant_id=uuid.uuid4(), turn_id="t1"):
        with pytest.raises(collector.UsageTaskMissing):
            collector.record_llm_usage(
                model="anthropic/claude-haiku-5-5", provider=None, usage=USAGE, task="respond"
            )


async def test_in_production_it_is_measured_and_flagged(monkeypatch, fake_redis) -> None:
    monkeypatch.delenv("NEXUS_USAGE_REQUIRE_TASK", raising=False)
    tenant_id = uuid.uuid4()
    with capture_logs() as logs:
        async with collector.usage_turn(tenant_id=tenant_id, turn_id="t1"):
            collector.record_llm_usage(
                model="anthropic/claude-haiku-5-5", provider=None, usage=USAGE
            )

    assert len(_events(fake_redis)) == 2, "la medición no se pierde"
    anomalies = [e for e in logs if e.get("event") == "usage.task_missing"]
    assert len(anomalies) == 1
    assert anomalies[0]["tenant_id"] == str(tenant_id)
    assert anomalies[0]["log_level"] == "error"


async def test_the_task_and_the_decision_travel_with_each_event(monkeypatch, fake_redis) -> None:
    monkeypatch.setenv("NEXUS_USAGE_REQUIRE_TASK", "1")
    decision = uuid.uuid4()
    async with collector.usage_turn(tenant_id=uuid.uuid4(), turn_id="t1"):
        collector.record_llm_usage(
            model="anthropic/claude-haiku-5-5",
            provider="anthropic",
            usage=USAGE,
            task="classify",
            route_decision_id=decision,
        )

    events = _events(fake_redis)
    assert {e["task"] for e in events} == {"classify"}
    assert {e["route_decision_id"] for e in events} == {str(decision)}


async def test_voice_minutes_are_a_transcription(monkeypatch, fake_redis) -> None:
    monkeypatch.setenv("NEXUS_USAGE_REQUIRE_TASK", "1")
    async with collector.usage_turn(tenant_id=uuid.uuid4(), turn_id="t1"):
        collector.record_voice_minutes(model="openai/whisper-1", provider="openai", seconds=30)

    [event] = _events(fake_redis)
    assert event["task"] == "transcribe"


def test_the_task_list_is_the_catalog_taxonomy() -> None:
    """Una lista en el código y otra en el catálogo acaban divergiendo: esta
    prueba las ata. Una tarea nueva es una versión nueva de la taxonomía."""
    root = Path(__file__).resolve().parents[3]
    path = root / "api" / "alembic" / "versions" / "0180_model_catalog_and_router.py"
    spec = importlib.util.spec_from_file_location("_mig_0180", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert frozenset(t["code"] for t in module.TAXONOMY_V1) == collector.LLM_TASKS


def _entry(source: str, **event: object) -> dict[str, str]:
    return {
        "tenant_id": str(uuid.uuid4()),
        "turn_id": "t1",
        "source": source,
        "events": json.dumps(
            [
                {
                    "meter": "llm.input_tokens",
                    "quantity": 100,
                    "idempotency_key": "t1:1:llm.input_tokens",
                    "occurred_at": "2026-10-26T10:00:00+00:00",
                    "model": "anthropic/claude-haiku-5-5",
                    **event,
                }
            ]
        ),
    }


@pytest.mark.parametrize(
    ("source", "line"),
    [
        ("channel", "conversations"),
        ("qa", "build"),
        ("builder", "build"),
        ("tests", "build"),
        ("reader", "build"),
        ("indexer", "build"),
        ("suggestions", "build"),
        # Requisito 42.6: las certificaciones que lanza Auphere son suyas,
        # fuera de las partidas del partner.
        ("certification", "platform"),
        ("companion", "companion"),
    ],
)
def test_the_line_comes_from_the_source(source: str, line: str) -> None:
    _tenant, [row] = consumer.rows_from_entry(_entry(source))
    assert row["line"] == line


def test_the_row_keeps_the_task_and_the_decision() -> None:
    decision = str(uuid.uuid4())
    _tenant, [row] = consumer.rows_from_entry(
        _entry("channel", task="tool_turn", route_decision_id=decision)
    )
    assert row["task"] == "tool_turn"
    assert row["route_decision_id"] == uuid.UUID(decision)


def test_an_old_entry_without_a_task_still_lands() -> None:
    """Las entradas publicadas antes del cambio no llevan tarea: entran con NULL."""
    _tenant, [row] = consumer.rows_from_entry(_entry("channel"))
    assert row["task"] is None and row["route_decision_id"] is None
