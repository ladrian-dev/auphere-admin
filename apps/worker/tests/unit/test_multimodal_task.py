"""El multimedia dice su tarea en cada llamada (spec 047, requisito 40.1).

El procesador de multimedia llama a LiteLLM por su cuenta (visión y
transcripción) y mide cada llamada a mano. Toda llamada a un modelo lleva una
tarea de la taxonomía; aquí se exige **escrita en la llamada**, no heredada de un
valor por defecto del medidor: un valor por defecto se cambia en otro archivo y
la llamada pasa a medirse con otra tarea sin que nadie toque el procesador.

El barrido lee el código con ``ast``: una llamada nueva al medidor sin
``task=`` es roja el mismo día que se escribe.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.unit._router_world import migration_taxonomy

PROCESSOR = (
    Path(__file__).resolve().parents[2] / "src" / "nexus_worker" / "multimodal" / "processor.py"
)
METER_CALLS = frozenset({"record_llm_usage", "record_voice_minutes", "record_usage"})


def _meter_calls() -> list[ast.Call]:
    tree = ast.parse(PROCESSOR.read_text(encoding="utf-8"))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in METER_CALLS
    ]


def test_every_metered_call_of_the_processor_names_its_task() -> None:
    tasks = {str(t["code"]) for t in migration_taxonomy()}
    calls = _meter_calls()
    assert {c.func.id for c in calls if isinstance(c.func, ast.Name)} == {
        "record_llm_usage",
        "record_voice_minutes",
    }, "el barrido no ve las dos medidas del procesador"
    named: dict[str, str] = {}
    for call in calls:
        task = next((kw.value for kw in call.keywords if kw.arg == "task"), None)
        assert isinstance(task, ast.Constant), (
            f"processor.py:{call.lineno} mide sin decir su tarea (task=…)"
        )
        assert task.value in tasks, f"processor.py:{call.lineno}: {task.value!r} no es una tarea"
        assert isinstance(call.func, ast.Name)
        named[call.func.id] = str(task.value)
    assert named == {"record_llm_usage": "vision", "record_voice_minutes": "transcribe"}
