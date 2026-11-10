"""Spec 047, enmienda del 2026-10-29, T201 — la evaluación del constructor con
sectores con y sin guía (requisito 58.7; research D47).

- El banco tiene sectores con guía y sin ella, cada negocio con su nombre y su
  ficha (servicios y horario), no «Negocio».
- Cada borrador recibe la guía de su sector; uno sin guía la recibe generada solo
  con su etiqueta.
- La evaluación mide, además del validador, si el borrador pasa **sus pruebas del
  sector**, y lo dice por separado con guía y sin guía.
"""

from __future__ import annotations

import copy
import json
from collections import Counter
from typing import Any

import pytest

from nexus_api.services.agent_spec.validator import Context, ToolInfo
from nexus_api.services.builder.evaluation import bank, evaluate
from nexus_api.services.builder.guides.generated import SYSTEM as GUIDE_SYSTEM

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]

DRAFT: dict[str, Any] = {
    "voice": {"tone": "Cercano", "languages": ["es"]},
    "goal": "Atender bien.",
    "instructions": [{"title": "Cómo atiendes", "body": "Con la ficha."}],
    "tools": ["escalate.escalate_to_human"],
    "escalation": {"triggers": ["asks_for_human"], "failed_attempts": 2},
    "questions": [],
    "tests": [],
}


def test_the_bank_has_sectors_with_and_without_guide_and_real_fichas() -> None:
    items = bank()
    assert len(items) == 120
    without = [i for i in items if i["sector"] == "otro"]
    assert len(without) >= 20 and len({i["label"] for i in without}) >= 8
    assert len({i["business"]["name"] for i in items}) == len(items)
    for item in items:
        assert item["business"]["services"] and item["business"]["hours"], item["id"]
    by_sector = Counter(i["sector"] for i in items)
    assert set(by_sector) >= {"barberia_peluqueria", "clinica", "restaurante", "otro"}


async def test_the_eval_gives_each_draft_its_guide_and_measures_sector_tests() -> None:
    items = [i for i in bank() if i["id"] in {"b001", "o001"}]
    seen: list[str] = []
    generations: list[str] = []

    async def model(messages: list[dict[str, str]]) -> str:
        if messages[0]["content"] == GUIDE_SYSTEM:
            generations.append(messages[1]["content"])
            return json.dumps({"guide": {"ask": ["¿Cuota?"]}, "tests": _twelve()})
        seen.append(messages[1]["content"])
        return json.dumps(copy.deepcopy(DRAFT))

    batteries: list[tuple[str, int]] = []

    async def battery(draft: Any, tests: list[dict[str, Any]]) -> bool:
        batteries.append((draft.spec.identity.name, len(tests)))
        return len(tests) == 12

    ctx = Context(tools={"escalate.escalate_to_human": ToolInfo(name="escalate.escalate_to_human")})
    report = await evaluate(
        model, ctx=ctx, items=items, battery=battery, catalog={"barberia_peluqueria": _twelve()}
    )

    barber, gym = seen
    assert "Barbería Cultor" in barber and "Llegar sin cita" in barber
    assert "Gimnasio Titán" in gym and "¿Cuota?" in gym
    (generation,) = generations
    assert "Gimnasio" in generation and "Titán" not in generation
    assert [n for _name, n in batteries] == [12, 12]
    by_id = {r["id"]: r for r in report["results"]}
    assert by_id["b001"]["has_guide"] is True and by_id["o001"]["has_guide"] is False
    assert by_id["o001"]["sector_tests"] == 12
    assert report["sector_pass_unedited_pct"] == 100.0
    assert report["by_guide"]["with"]["items"] == 1
    assert report["by_guide"]["without"]["battery_pct"] == 100.0


def _twelve() -> list[dict[str, Any]]:
    return [
        {
            "key": f"t{n}",
            "name": f"Prueba {n}",
            "first_message": "Hola",
            "criteria": [{"key": "ok", "text": "Bien"}],
        }
        for n in range(12)
    ]
